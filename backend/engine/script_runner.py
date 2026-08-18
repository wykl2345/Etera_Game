"""脚本调度器 —— 引擎心脏（v2 asyncio 化）。

v1 用 Qt 嵌套 QEventLoop 实现"脚本暂停等玩家输入"，v2 改为：
  - 脚本在独立线程中同步执行（不阻塞 asyncio 主循环 / WS 收发）
  - 阻塞指令（ask_choice/ask_input）经 concurrent.futures.Future 挂起
  - WS 网关（主循环）收到玩家输入后调用 resolve_wait() 恢复

事件流：ui.ask_choice → 发消息+挂起 → 前端 choice.made → resolve_wait → Future.set_result → Lua 继续
"""
from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from engine.sandbox import ScriptValidator

logger = logging.getLogger(__name__)


class ScriptState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class ScriptInfo:
    path: str
    name: str
    state: ScriptState = ScriptState.IDLE
    error: Optional[str] = None
    stack: List[str] = field(default_factory=list)


class ScriptAbortedError(Exception):
    """脚本被引擎中止（如重启）。"""


class UIOutput:
    """UI 输出通道抽象：生产实现为 WS 网关（线程安全），测试用内存实现。

    只要求线程安全的 send（脚本线程调用）。
    """

    def send(self, msg: Dict[str, Any]) -> None:
        raise NotImplementedError


class ScriptScheduler:
    def __init__(
        self,
        event_bus: Any,
        sandbox: Any,
        game_context: Any,
        output: UIOutput,
        scripts_dir: Optional[Path] = None,
    ) -> None:
        self._bus = event_bus
        self._sandbox = sandbox
        self._ctx = game_context
        self.output = output
        self.scripts_dir = Path(scripts_dir) if scripts_dir else Path("data/scenarios")
        self._state = ScriptState.IDLE
        self._current: Optional[ScriptInfo] = None
        self._pending: Dict[str, Future] = {}
        self._lock = threading.RLock()
        self._aborted = False
        self._history: List[ScriptInfo] = []

    # ── 状态 ──────────────────────────────────────────────────
    @property
    def state(self) -> ScriptState:
        with self._lock:
            return self._state

    @property
    def current_script(self) -> Optional[ScriptInfo]:
        with self._lock:
            return self._current

    def is_waiting(self) -> bool:
        return self._state == ScriptState.WAITING_INPUT

    # ── 阻塞指令（脚本线程内调用）─────────────────────────────
    def ask_choice(self, options: List[str]) -> int:
        """发 ui.ask_choice 并阻塞脚本线程，直到 resolve_wait 恢复。"""
        req_id = uuid.uuid4().hex
        fut: Future = Future()
        with self._lock:
            self._pending[req_id] = fut
            self._state = ScriptState.WAITING_INPUT
        self.output.send(
            {"type": "ui.ask_choice", "requestId": req_id, "payload": {"options": options}}
        )
        try:
            result = fut.result()  # 阻塞脚本线程
        finally:
            with self._lock:
                self._pending.pop(req_id, None)
                self._state = ScriptState.RUNNING
        if self._aborted:
            raise ScriptAbortedError("脚本被中止")
        return int(result) if result is not None else 1

    def ask_input(self, prompt: str, default: str = "", max_length: int = 100) -> str:
        req_id = uuid.uuid4().hex
        fut: Future = Future()
        with self._lock:
            self._pending[req_id] = fut
            self._state = ScriptState.WAITING_INPUT
        self.output.send(
            {"type": "ui.ask_input", "requestId": req_id,
             "payload": {"prompt": prompt, "default": default, "max_length": max_length}}
        )
        try:
            result = fut.result()
        finally:
            with self._lock:
                self._pending.pop(req_id, None)
                self._state = ScriptState.RUNNING
        if self._aborted:
            raise ScriptAbortedError("脚本被中止")
        return str(result) if result is not None else default

    def ask_minigame(self, game_id: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """触发小游戏（阻塞）：发 minigame.start 挂起脚本，等前端回传结果。"""
        req_id = uuid.uuid4().hex
        fut: Future = Future()
        with self._lock:
            self._pending[req_id] = fut
            self._state = ScriptState.WAITING_INPUT
        self.output.send(
            {"type": "minigame.start", "requestId": req_id,
             "payload": {"game_id": game_id, "options": options or {}}}
        )
        try:
            result = fut.result()
        finally:
            with self._lock:
                self._pending.pop(req_id, None)
                self._state = ScriptState.RUNNING
        if self._aborted:
            raise ScriptAbortedError("脚本被中止")
        return result if isinstance(result, dict) else {"won": False}

    # ── 恢复（WS 主循环调用，线程安全）────────────────────────
    def resolve_wait(
        self,
        request_id: str,
        choice_index: Optional[int] = None,
        input_text: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        with self._lock:
            fut = self._pending.get(request_id)
        if fut is None:
            return False
        if input_text is not None:
            fut.set_result(input_text)
        elif result is not None:
            fut.set_result(result)
        else:
            fut.set_result(choice_index)
        return True

    # ── 中止/重启 ─────────────────────────────────────────────
    def stop_all(self) -> None:
        """中止所有等待与运行（F5 重启语义）。"""
        with self._lock:
            self._aborted = True
            pending = list(self._pending.items())
            self._pending.clear()
            self._state = ScriptState.IDLE
        for _req_id, fut in pending:
            if not fut.done():
                fut.set_exception(ScriptAbortedError("脚本被中止"))

    def reset_abort(self) -> None:
        with self._lock:
            self._aborted = False

    # ── 脚本执行（脚本线程内调用）─────────────────────────────
    def run_script_sync(self, script_path: str, **kwargs: Any) -> bool:
        """同步执行一个剧本文件。scripts_dir 相对路径；防目录穿越。"""
        full = self._resolve_script_path(script_path)
        if full is None:
            logger.error("剧本路径非法: %s", script_path)
            return False
        info = ScriptInfo(path=str(full), name=full.name)
        with self._lock:
            self._current = info
            self._state = ScriptState.RUNNING
        try:
            code = full.read_text(encoding="utf-8")
        except OSError as exc:
            info.error = str(exc)
            info.state = ScriptState.ERROR
            self._bus.emit("script.error", path=script_path, error=str(exc))
            return False
        ok, err = ScriptValidator.validate(code)
        if not ok:
            info.error = err
            info.state = ScriptState.ERROR
            self._bus.emit("script.error", path=script_path, error=err)
            return False
        try:
            globals_ = self._sandbox.runtime.globals()
            for key, value in kwargs.items():
                globals_[key] = value
            self._sandbox.execute(code)
            info.state = ScriptState.COMPLETED
            self._bus.emit("script.completed", path=script_path)
            return True
        except ScriptAbortedError:
            info.state = ScriptState.IDLE
            self._bus.emit("script.aborted", path=script_path)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.exception("剧本执行失败: %s", script_path)
            info.error = str(exc)
            info.state = ScriptState.ERROR
            self._bus.emit("script.error", path=script_path, error=str(exc))
            return False
        finally:
            with self._lock:
                self._history.append(info)
                if len(self._history) > 100:
                    self._history.pop(0)
                self._current = None
                self._state = ScriptState.IDLE

    def _resolve_script_path(self, script_path: str) -> Optional[Path]:
        p = Path(script_path)
        if not p.is_absolute():
            p = self.scripts_dir / p
        p = p.resolve()
        base = self.scripts_dir.resolve()
        # 目录穿越防护：解析后必须位于 scripts_dir 下
        if not str(p).startswith(str(base)):
            return None
        if not p.is_file():
            return None
        return p

    def get_script_history(self) -> List[ScriptInfo]:
        with self._lock:
            return list(self._history)
