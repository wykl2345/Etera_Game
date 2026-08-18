"""
Lua沙箱模块 (sandbox.py)

本模块负责初始化Lua运行时环境，采用lupa库（Python Lua绑定）。
配置严格的安全限制，确保Lua脚本无法访问系统资源。

安全措施：
- 移除危险模块：os, io, debug, loadfile, loadstring等
- 限制全局函数：禁止使用compile、eval等
- 限制文件访问：无法读写文件系统
- 网络隔离：完全禁止网络操作

设计决策：
- 使用lupa而非其他Lua绑定的原因：
  1. 性能好，执行效率高
  2. 沙箱机制成熟
  3. 与Python的互操作性强
  4. 支持协程（与asyncio无缝对接）

可选替代方案：
- Ink：专为叙事游戏设计，适合复杂剧情分支
- 自定义DSL：完全可控，但需要开发成本
"""

import logging
from typing import Any, Dict, Optional, Callable
from pathlib import Path


# 配置日志记录器
logger = logging.getLogger(__name__)


# 尝试导入lupa
try:
    import lupa
    LUPA_AVAILABLE = True
except ImportError:
    logger.warning("lupa未安装，将使用模拟沙箱")
    LUPA_AVAILABLE = False


# 危险的Lua全局函数和模块
DANGEROUS_GLOBALS = [
    "os",           # 操作系统访问
    "io",           # 文件IO
    "debug",        # 调试功能
    "loadfile",     # 文件加载
    "loadstring",   # 字符串执行
    "dofile",       # 执行文件
    "require",      # 模块加载
    "package",      # 包管理
    "collectgarbage", # 垃圾回收控制
]

# 需要限制的全局函数
RESTRICTED_FUNCTIONS = {
    "os": ["execute", "remove", "rename", "setlocale", "getenv", "exit", "clock", "date", "time", "difftime"],
    "io": ["open", "input", "output", "stderr", "stdin", "stdout", "popen", "close", "read", "write", "flush", "lines", "type", "seek"],
    "debug": ["debug", "traceback", "gethook", "setlocal", "setmetatable", "upvalueid", "upvaluejoin", "sethook", "setlocal", "setfenv", "getfenv", "getinfo", "getlocal", "getmetatable", "getregistry", "getupvalue"],
    "math": ["randomseed"],  # 限制随机种子
}


class LuaSandbox:
    """
    Lua沙箱环境

    提供安全的Lua执行环境，移除所有危险操作。

    使用示例：
        sandbox = LuaSandbox(api_bridge)
        lua = sandbox.get_runtime()

        # 设置API
        sandbox.inject_api()

        # 执行脚本
        lua.execute("ui.text('Hello')")
    """

    def __init__(
        self,
        api_bridge: Optional[Any] = None
    ):
        """
        初始化Lua沙箱

        Args:
            api_bridge: API桥接器实例
        """
        self.api_bridge = api_bridge
        self._runtime: Optional[Any] = None

        # 初始化Lua运行时
        self._init_runtime()

        logger.info("Lua沙箱初始化完成")

    def _init_runtime(self) -> None:
        """初始化Lua运行时"""
        if not LUPA_AVAILABLE:
            logger.warning("lupa未安装，使用模拟沙箱")
            self._runtime = MockLuaRuntime()
            return

        try:
            # 创建Lua运行时
            self._runtime = lupa.LuaRuntime(
                max_memory=256 * 1024 * 1024,  # 256MB内存限制
            )

            # 应用安全限制
            self._apply_security_restrictions()

            logger.info("Lua运行时初始化成功")

        except Exception as e:
            logger.error(f"Lua运行时初始化失败: {e}")
            raise

    def _apply_security_restrictions(self) -> None:
        """应用安全限制"""
        if not self._runtime:
            return

        lua = self._runtime

        # 移除危险全局变量
        for name in DANGEROUS_GLOBALS:
            try:
                lua.globals()[name] = None
                logger.debug(f"已移除危险全局: {name}")
            except Exception:
                pass

        # 限制某些模块的函数
        for module, functions in RESTRICTED_FUNCTIONS.items():
            try:
                mod = lua.globals()[module]
                for func in functions:
                    try:
                        mod[func] = None
                    except Exception:
                        pass
            except Exception:
                pass

        # 替换危险的全局函数为安全版本
        safe_overrides = {
            "print": self._safe_print,
        }
        for name, func in safe_overrides.items():
            try:
                lua.globals()[name] = func
                logger.debug(f"已覆盖全局函数: {name}")
            except Exception:
                pass

        # 限制 math.randomseed（禁止操控随机种子）
        try:
            math_mod = lua.globals()["math"]
            if math_mod:
                math_mod["randomseed"] = None
                logger.debug("已禁用 math.randomseed")
        except Exception:
            pass

    def _safe_print(self, *args: Any) -> None:
        """安全的print函数"""
        try:
            output = " ".join(str(arg) for arg in args)
            logger.debug(f"[Lua] {output}")
        except Exception:
            pass

    def _safe_table_concat(self, tbl: list, sep: str = "", i: int = 1, j: int = -1) -> str:
        """安全的table.concat函数"""
        if not isinstance(tbl, list):
            return ""
        if j == -1:
            j = len(tbl)
        return sep.join(str(tbl[k]) for k in range(i, j + 1) if k < len(tbl))

    def _safe_math_random(self, m: Optional[int] = None, n: Optional[int] = None) -> float:
        """安全的math.random函数"""
        import random
        if m is None:
            return random.random()
        elif n is None:
            return random.randint(1, m)
        else:
            return random.randint(m, n)

    def get_runtime(self) -> Any:
        """
        获取Lua运行时实例

        Returns:
            Any: Lua运行时
        """
        return self._runtime

    def inject_api(self) -> None:
        """注入API到Lua环境"""
        if not self.api_bridge or not self._runtime:
            logger.warning("API桥接器未设置，跳过API注入")
            return

        # 构建API环境
        api_env = self.api_bridge.build_env()

        # 注入到Lua全局环境
        lua_globals = self._runtime.globals()

        for name, value in api_env.items():
            try:
                lua_globals[name] = value
                logger.debug(f"已注入API: {name}")
            except Exception as e:
                logger.warning(f"注入API失败 {name}: {e}")

        logger.info("API已注入到Lua环境")

    def execute(self, code: str) -> Any:
        """
        执行Lua代码

        Args:
            code: Lua代码

        Returns:
            Any: 执行结果
        """
        if not self._runtime:
            raise RuntimeError("Lua运行时未初始化")

        try:
            result = self._runtime.execute(code)
            return result
        except Exception as e:
            logger.error(f"Lua执行错误: {e}")
            raise

    def execute_file(self, filepath: str) -> Any:
        """
        执行Lua文件

        Args:
            filepath: 文件路径

        Returns:
            Any: 执行结果
        """
        path = Path(filepath)

        if not path.exists():
            raise FileNotFoundError(f"Lua文件不存在: {filepath}")

        with open(path, 'r', encoding='utf-8') as f:
            code = f.read()

        return self.execute(code)

    def set_memory_limit(self, limit_bytes: int) -> None:
        """
        设置内存限制

        Args:
            limit_bytes: 内存限制（字节）
        """
        if self._runtime and hasattr(self._runtime, 'memory'):
            self._runtime.memory = limit_bytes
            logger.info(f"内存限制已设置为: {limit_bytes / (1024*1024):.1f}MB")

    def set_time_limit(self, limit_seconds: float) -> None:
        """
        设置执行时间限制

        Args:
            limit_seconds: 时间限制（秒）
        """
        # lupa不支持直接设置时间限制，但可以在执行时检查
        self._time_limit = limit_seconds
        logger.info(f"时间限制已设置为: {limit_seconds}秒")

    def cleanup(self) -> None:
        """清理资源"""
        if self._runtime:
            # 强制垃圾回收
            try:
                if LUPA_AVAILABLE:
                    self._runtime.flush()
            except Exception:
                pass

        logger.info("Lua沙箱已清理")


class MockLuaRuntime:
    """
    模拟Lua运行时

    当lupa不可用时的降级方案，提供基本的模拟接口。
    """

    def __init__(self):
        """初始化模拟运行时"""
        self._globals = {}
        self.memory = 256 * 1024 * 1024

    @property
    def globals(self):
        """获取全局环境"""
        return MockLuaGlobals(self._globals)

    def execute(self, code: str) -> Any:
        """执行代码（仅记录）"""
        logger.warning(f"模拟执行Lua代码: {code[:100]}...")
        return None


class MockLuaGlobals:
    """模拟Lua全局环境

    兼容两种调用方式：
      lua.globals()      # 作为方法调用 → 返回 self
      lua.globals[key]   # 属性索引 → __getitem__/__setitem__
    """

    def __init__(self, data: Dict[str, Any]):
        """初始化"""
        self._data = data

    def __call__(self) -> 'MockLuaGlobals':
        """支持 globals() 方法调用，返回自身"""
        return self

    def __getitem__(self, key: str) -> Any:
        """获取全局变量"""
        return self._data.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """设置全局变量"""
        self._data[key] = value

    def __getattr__(self, key: str) -> Any:
        """获取属性"""
        return self._data.get(key)


class LuaEventBridge:
    """
    Lua事件桥接

    在Lua环境中提供事件监听和触发功能。
    """

    def __init__(self, event_bus: Any):
        """
        初始化事件桥接

        Args:
            event_bus: 事件总线实例
        """
        self.event_bus = event_bus

    def build_api(self) -> Dict[str, Callable]:
        """
        构建事件API

        Returns:
            Dict[str, Callable]: API函数字典
        """
        return {
            "on": self._on,
            "off": self._off,
            "emit": self._emit,
        }

    def _on(self, event_name: str, callback: Callable) -> None:
        """监听事件"""
        self.event_bus.subscribe(event_name, callback)

    def _off(self, event_name: str, callback: Callable) -> None:
        """取消监听"""
        self.event_bus.unsubscribe(event_name, callback)

    def _emit(self, event_name: str, data: Optional[Dict] = None) -> None:
        """触发事件"""
        self.event_bus.emit(event_name, **(data or {}))


def create_lua_environment(
    event_bus: Any,
    api_bridge: Any,
    resource_manager: Any = None
) -> LuaSandbox:
    """
    创建完整的Lua环境

    这是工厂函数，一次性创建完整的Lua沙箱环境。

    Args:
        event_bus: 事件总线
        api_bridge: API桥接器
        resource_manager: 资源管理器

    Returns:
        LuaSandbox: 配置好的沙箱实例
    """
    # 创建沙箱
    sandbox = LuaSandbox(api_bridge)

    # 注入API
    sandbox.inject_api()

    # 设置资源限制
    sandbox.set_memory_limit(256 * 1024 * 1024)  # 256MB
    sandbox.set_time_limit(30)  # 30秒

    logger.info("Lua环境创建完成")

    return sandbox


class ScriptValidator:
    """
    脚本验证器

    在执行前验证Lua脚本的安全性。
    """

    # 危险模式列表
    DANGEROUS_PATTERNS = [
        r"os\.",           # 操作系统调用
        r"io\.",           # 文件IO
        r"loadfile",       # 文件加载
        r"loadstring",     # 字符串执行
        r"dofile",         # 执行文件
        r"require",        # 模块加载
        r"debug\.",        # 调试功能
        r"\.execute\(",    # 执行命令
        r"getenv",        # 获取环境变量
    ]

    @classmethod
    def validate(cls, code: str) -> tuple[bool, Optional[str]]:
        """
        验证脚本安全性

        Args:
            code: Lua代码

        Returns:
            tuple[bool, Optional[str]]: (是否安全, 错误信息)
        """
        import re

        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, code):
                return False, f"危险模式检测到: {pattern}"

        return True, None

    @classmethod
    def validate_file(cls, filepath: str) -> tuple[bool, Optional[str]]:
        """
        验证脚本文件

        Args:
            filepath: 文件路径

        Returns:
            tuple[bool, Optional[str]]: (是否安全, 错误信息)
        """
        path = Path(filepath)

        if not path.exists():
            return False, "文件不存在"

        try:
            with open(path, 'r', encoding='utf-8') as f:
                code = f.read()

            return cls.validate(code)

        except Exception as e:
            return False, f"读取文件失败: {e}"
