"""
协程调度器模块 (script_runner.py)

本模块是整个引擎的核心，负责Lua脚本的执行和暂停/恢复管理。
采用 QEventLoop 嵌套实现等待，确保在 Qt 主线程中暂停脚本执行时，
Qt 事件循环仍能正常处理用户输入（按钮点击等）。

设计模式：嵌套事件循环

脚本执行流程：
  [Lua脚本]          [调度器]            [GUI]
     │                  │                  │
     │── show_text() ──►│── emit信号 ──────►│ 显示文字
     │                  │                  │
     │── ask_choice() ──►│── 嵌套QEventLoop─►│ 生成按钮
     │                  │◄── 用户点击 ───────│
     │◄── resume(选择) ──│←─ loop.quit() ──│
     │                  │                  │
     │── end_event() ──►│── 通知EventBus ──►│ 触发下一事件

核心机制：
- 使用 QEventLoop.exec() 创建嵌套事件循环
- Lua脚本调用 ask_choice() 时，进入嵌套循环等待用户输入
- 用户点击按钮后，通过事件总线回调 resolve_wait()
- resolve_wait() 调用 loop.quit() 退出嵌套循环
- 脚本继续执行
"""

import logging
import time
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# Qt 导入
from PySide6.QtCore import QEventLoop, QTimer

# 配置日志记录器
logger = logging.getLogger(__name__)


class ScriptState(Enum):
    """脚本执行状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    WAITING_INPUT = "waiting"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class ScriptInfo:
    """脚本信息"""
    path: str
    name: str
    state: ScriptState = ScriptState.IDLE
    error: Optional[str] = None
    stack: List[str] = field(default_factory=list)


class WaitType(Enum):
    """等待类型枚举"""
    CHOICE = "choice"
    INPUT = "input"
    CLICK = "click"


class ScriptScheduler:
    """
    脚本调度器

    这是引擎的心脏，负责协调Lua脚本的执行、暂停和恢复。
    通过 QEventLoop 嵌套实现非阻塞的脚本控制。

    使用示例：
        scheduler = ScriptScheduler(event_bus, sandbox)

        # 处理用户选择（从事件总线回调中）
        scheduler.resolve_wait(choice_index=1)

        # 暂停/恢复
        scheduler.pause_all()
        scheduler.resume_all()
    """

    def __init__(
        self,
        event_bus: Any,
        sandbox: Any,
        game_context: Any
    ):
        self.event_bus = event_bus
        self.sandbox = sandbox
        self.context = game_context

        # 当前脚本信息
        self._current_script: Optional[ScriptInfo] = None
        self._state: ScriptState = ScriptState.IDLE

        # 等待控制 —— 嵌套 QEventLoop
        self._active_loop: Optional[QEventLoop] = None
        self._wait_result: Any = None
        self._wait_type: Optional[WaitType] = None

        # 脚本历史记录
        self._script_history: List[ScriptInfo] = []
        self._max_history: int = 50

        # 事件监听器清理函数
        self._listeners: List[Callable] = []

        # 注册事件监听
        self._register_event_listeners()

        logger.info("脚本调度器初始化完成 (QEventLoop模式)")

    def _register_event_listeners(self) -> None:
        """注册事件监听器"""
        def on_choice_made(choice_index: int, **kwargs):
            self.resolve_wait(choice_index=choice_index)

        def on_input_received(text: str, **kwargs):
            self.resolve_wait(input_text=text)

        def on_ui_click(**kwargs):
            self.resolve_wait()

        self._listeners.extend([
            self.event_bus.subscribe("ui.choice_made", on_choice_made),
            self.event_bus.subscribe("ui.input_received", on_input_received),
            self.event_bus.subscribe("ui.clicked", on_ui_click),
        ])

    @property
    def state(self) -> ScriptState:
        return self._state

    @property
    def current_script(self) -> Optional[ScriptInfo]:
        return self._current_script

    # ─── 等待 API（供 api_bridge 调用）─────────────────────────

    def wait_for_choice(self) -> int:
        """
        等待玩家选择 —— 嵌套 QEventLoop

        Qt 主线程在此处进入嵌套事件循环，用户点击选项后
        resolve_wait() 调用 loop.quit() 退出并返回结果。
        """
        self._begin_wait(WaitType.CHOICE)

        loop = QEventLoop()
        self._active_loop = loop
        loop.exec()  # ← 嵌套事件循环，Qt 仍能处理点击

        self._end_wait()
        result = self._wait_result
        return result if result is not None else 1

    def wait_for_input(self) -> str:
        """
        等待玩家输入文本 —— 嵌套 QEventLoop
        """
        self._begin_wait(WaitType.INPUT)

        loop = QEventLoop()
        self._active_loop = loop
        loop.exec()

        self._end_wait()
        result = self._wait_result
        return result if result else ""

    def wait_for_click(self, timeout: Optional[float] = None) -> bool:
        """
        等待玩家点击 —— 嵌套 QEventLoop（可选超时）

        如果提供 timeout，超时后自动退出返回 False。
        """
        self._begin_wait(WaitType.CLICK)

        loop = QEventLoop()
        self._active_loop = loop

        timer = None
        if timeout and timeout > 0:
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(int(timeout * 1000))

        loop.exec()

        if timer:
            timer.stop()

        timed_out = (self._wait_result is None)
        self._end_wait()
        return not timed_out

    def resolve_wait(
        self,
        choice_index: Optional[int] = None,
        input_text: Optional[str] = None
    ) -> bool:
        """
        解决等待 —— 由事件总线回调触发

        存储结果并退出嵌套 QEventLoop，让 wait_for_* 返回。
        """
        if not self._active_loop or not self._active_loop.isRunning():
            logger.warning("resolve_wait: 没有活动的等待循环")
            return False

        # 存储结果
        if self._wait_type == WaitType.CHOICE:
            self._wait_result = choice_index if choice_index is not None else 1
        elif self._wait_type == WaitType.INPUT:
            self._wait_result = input_text if input_text is not None else ""
        else:
            self._wait_result = True

        # 恢复状态
        self._state = ScriptState.RUNNING
        if self._current_script:
            self._current_script.state = ScriptState.RUNNING

        # 退出嵌套循环
        self._active_loop.quit()
        logger.debug(f"等待已解决: {self._wait_type.value} = {self._wait_result}")
        return True

    # ─── 内部辅助 ────────────────────────────────────────────

    def _begin_wait(self, wait_type: WaitType):
        """开始等待"""
        self._wait_type = wait_type
        self._wait_result = None
        self._state = ScriptState.WAITING_INPUT
        if self._current_script:
            self._current_script.state = ScriptState.WAITING_INPUT

    def _end_wait(self):
        """结束等待"""
        self._active_loop = None
        self._wait_type = None

    # ─── 脚本执行 API ────────────────────────────────────────

    def run_script_sync(self, script_path: str, **kwargs) -> bool:
        """
        同步执行脚本（在事件总线回调中调用）

        Args:
            script_path: 脚本文件路径（相对于 data/events）
            **kwargs: 传递给脚本的全局变量

        Returns:
            bool: 是否成功
        """
        full_path = self._resolve_script_path(script_path)
        logger.info(f"执行脚本: {full_path}")

        script_info = ScriptInfo(path=full_path, name=Path(script_path).stem)
        self._current_script = script_info
        self._script_history.append(script_info)

        if len(self._script_history) > self._max_history:
            self._script_history = self._script_history[-self._max_history:]

        try:
            self._state = ScriptState.RUNNING
            script_info.state = ScriptState.RUNNING

            lua = self.sandbox.get_runtime()
            with open(full_path, 'r', encoding='utf-8') as f:
                code = f.read()

            # 设置全局参数
            for key, value in kwargs.items():
                try:
                    lua.globals()[key] = value
                except Exception:
                    pass

            lua.execute(code)

            script_info.state = ScriptState.COMPLETED
            self._state = ScriptState.IDLE
            self.event_bus.emit("script.completed", script=script_info.name)
            logger.info(f"脚本完成: {script_info.name}")
            return True

        except Exception as e:
            script_info.state = ScriptState.ERROR
            script_info.error = str(e)
            self._state = ScriptState.ERROR
            self.event_bus.emit("script.error", script=script_info.name, error=str(e))
            logger.error(f"脚本错误: {e}", exc_info=True)
            return False

        finally:
            self._current_script = None

    def _resolve_script_path(self, relative_path: str) -> str:
        """解析脚本路径（含安全检查）"""
        base_dir = Path("data/events")
        full_path = base_dir / relative_path
        resolved = full_path.resolve()
        if not str(resolved).startswith(str(base_dir.resolve())):
            raise SecurityError(f"禁止的脚本路径: {relative_path}")
        return str(resolved)

    # ─── 调度控制 ────────────────────────────────────────────

    def pause_all(self) -> None:
        """暂停所有脚本执行"""
        self._state = ScriptState.PAUSED
        if self._current_script:
            self._current_script.state = ScriptState.PAUSED
        logger.info("脚本已暂停")

    def resume_all(self) -> None:
        """恢复暂停的脚本"""
        self._state = ScriptState.RUNNING
        if self._current_script:
            self._current_script.state = ScriptState.RUNNING
        logger.info("脚本已恢复")

    def stop_all(self) -> None:
        """停止所有脚本"""
        if self._active_loop and self._active_loop.isRunning():
            self._active_loop.exit(1)
        self._current_script = None
        self._state = ScriptState.IDLE
        logger.info("所有脚本已停止")

    # ─── 查询与清理 ──────────────────────────────────────────

    def get_script_history(self) -> List[ScriptInfo]:
        return self._script_history.copy()

    def is_waiting(self) -> bool:
        """是否正在等待用户输入"""
        return self._active_loop is not None and self._active_loop.isRunning()

    def cleanup(self) -> None:
        """清理资源"""
        self.stop_all()
        for unsubscribe in self._listeners:
            try:
                unsubscribe()
            except Exception as e:
                logger.warning(f"移除监听器失败: {e}")
        self._listeners.clear()
        logger.info("脚本调度器已清理")

    def __del__(self):
        try:
            self.cleanup()
        except Exception:
            pass


class SecurityError(Exception):
    """安全错误异常"""
    pass
