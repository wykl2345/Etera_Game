"""Lua 安全沙箱 —— Mod 脚本的执行边界（ADR-0004: 固定 lupa.lua54）。

安全策略（对齐 v1）：
  - 删除危险全局：os/io/debug/loadfile/loadstring/dofile/require/package/collectgarbage
  - 限制 os/io/debug 模块内函数
  - 禁用 math.randomseed
  - print 重定向到引擎日志
  - 内存上限 256MB
  - lupa 不可用时降级 MockLuaRuntime（API 走真 Python 逻辑）
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from lupa.lua54 import LuaRuntime as _LuaRuntime  # type: ignore[attr-defined]

    LUPA_AVAILABLE = True
except ImportError:  # pragma: no cover - 降级路径
    LUPA_AVAILABLE = False
    _LuaRuntime = None  # type: ignore[assignment]

MAX_MEMORY = 256 * 1024 * 1024  # 256 MB

# 危险全局：整个删除
DANGEROUS_GLOBALS = [
    "os", "io", "debug", "loadfile", "loadstring", "dofile",
    "require", "package", "collectgarbage",
]

# 模块内限制函数：置 None（os/io/debug 已整体删除，此为纵深防御）
RESTRICTED_FUNCTIONS = {
    "os": ["execute", "remove", "rename", "tmpname", "getenv", "exit"],
    "io": ["open", "popen", "lines", "input", "output", "read", "write"],
    "debug": ["getinfo", "sethook", "getlocal", "setlocal", "traceback"],
}


class ScriptSecurityError(Exception):
    """脚本触犯安全边界。"""


class ScriptValidator:
    """执行前正则扫描危险模式（纵深防御，非唯一防线）。"""

    _DANGEROUS_PATTERNS = [
        (re.compile(r"\bos\.execute\s*\(", re.IGNORECASE), "os.execute"),
        (re.compile(r"\bio\.open\s*\(", re.IGNORECASE), "io.open"),
        (re.compile(r"\b(loadfile|loadstring|dofile)\s*\(", re.IGNORECASE), "动态加载"),
        (re.compile(r"\brequire\s*\(", re.IGNORECASE), "require"),
        (re.compile(r"\bos\.remove\s*\(", re.IGNORECASE), "os.remove"),
    ]

    @classmethod
    def validate(cls, code: str) -> Tuple[bool, Optional[str]]:
        if not code or not code.strip():
            return False, "空脚本"
        for pattern, label in cls._DANGEROUS_PATTERNS:
            if pattern.search(code):
                return False, f"检测到危险模式: {label}"
        return True, None


class LuaSandbox:
    """lupa.lua54 运行时封装：构造安全环境 + API 注入。"""

    def __init__(self, max_memory: int = MAX_MEMORY) -> None:
        if not LUPA_AVAILABLE:
            logger.warning("lupa 不可用，降级为 MockLuaRuntime")
            self._runtime: Any = MockLuaRuntime(max_memory=max_memory)
        else:
            self._runtime = _LuaRuntime(max_memory=max_memory)
        self._api_bridge: Any = None
        self._apply_security()

    # ── 安全基线 ──────────────────────────────────────────────
    def _apply_security(self) -> None:
        globals_ = self._runtime.globals()
        if LUPA_AVAILABLE:
            for name in DANGEROUS_GLOBALS:
                try:
                    globals_[name] = None
                except Exception:  # noqa: BLE001
                    pass
            for mod_name, funcs in RESTRICTED_FUNCTIONS.items():
                try:
                    mod = globals_[mod_name]
                    if mod is not None:
                        for fn in funcs:
                            try:
                                mod[fn] = None
                            except Exception:  # noqa: BLE001
                                pass
                except Exception:  # noqa: BLE001
                    pass
            try:
                math_mod = globals_["math"]
                math_mod["randomseed"] = None
            except Exception:  # noqa: BLE001
                pass
        # print 重定向（沙箱与 Mock 通用）
        try:
            globals_["print"] = self._safe_print
        except Exception:  # noqa: BLE001
            pass

    def _safe_print(self, *args: Any) -> None:
        logger.info("[Lua print] %s", " ".join(str(a) for a in args))

    # ── API 注入 ──────────────────────────────────────────────
    def inject_api(self, api_env: Dict[str, Callable]) -> None:
        """把 build_env() 的五组 API 注入到 Lua 全局。"""
        globals_ = self._runtime.globals()
        for group_name, api_table in api_env.items():
            globals_[group_name] = api_table

    # ── 执行 ──────────────────────────────────────────────────
    def execute(self, code: str) -> Any:
        return self._runtime.execute(code)

    def compile(self, code: str) -> Any:
        """预编译（供多次执行优化）。"""
        return self._runtime.compile(code)

    def execute_compiled(self, compiled: Any) -> Any:
        return self._runtime.execute(compiled)

    @property
    def runtime(self) -> Any:
        return self._runtime


# ── Mock 降级 ──────────────────────────────────────────────────────────────────
class MockLuaGlobals:
    """兼容 lua.globals() 的访问方式：属性/调用/下标。"""

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}
        self._api_calls: list = []

    def __call__(self) -> "MockLuaGlobals":
        return self

    def __getitem__(self, key: str) -> Any:
        return self._store.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self._store[key] = value

    def __getattr__(self, key: str) -> Any:
        if key.startswith("_"):
            raise AttributeError(key)
        return self._store.get(key)

    def __setattr__(self, key: str, value: Any) -> None:
        if key.startswith("_"):
            super().__setattr__(key, value)
        else:
            self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)


class MockLuaRuntime:
    """lupa 不可用时的降级运行时：API 调用走真 Python 逻辑。"""

    def __init__(self, max_memory: int = MAX_MEMORY) -> None:
        self.max_memory = max_memory
        self._globals = MockLuaGlobals()

    def globals(self) -> MockLuaGlobals:
        return self._globals

    def execute(self, code: str) -> Any:
        logger.warning("[MockLua] 跳过脚本执行（lupa 不可用）")
        return None

    def compile(self, code: str) -> Any:
        return code


def create_lua_environment(
    event_bus: Any,
    api_bridge: Any,
    resource_manager: Any = None,
) -> LuaSandbox:
    """工厂：构建带安全基线与 API 注入的沙箱（对齐 v1 语义）。"""
    sandbox = LuaSandbox(max_memory=MAX_MEMORY)
    sandbox.inject_api(api_bridge.build_env())
    return sandbox
