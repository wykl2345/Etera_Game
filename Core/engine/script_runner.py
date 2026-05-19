"""
协程调度器模块 (script_runner.py)

本模块是整个引擎的核心，负责Lua脚本的执行和暂停/恢复管理。
采用asyncio实现协程调度，解决"等待玩家输入时暂停脚本"的问题。

设计模式：生产者-消费者 + 协程

脚本执行流程：
  [Lua脚本]          [调度器]            [GUI]
     │                  │                  │
     │── show_text() ──►│── emit信号 ──────►│ 显示文字
     │                  │                  │
     │── ask_choice() ──►│── 暂停脚本 ──────►│ 生成按钮
     │                  │◄── 用户点击 ───────│
     │◄── resume(选择) ──│                  │
     │                  │                  │
     │── end_event() ──►│── 通知EventBus ──►│ 触发下一事件

核心机制：
- 使用asyncio.Future作为脚本暂停的信号量
- Lua脚本调用ask_choice()时，会yield一个特殊对象回Python
- Python捕获这个yield，暂停协程并等待用户输入
- 用户输入后，resolve Future恢复协程执行

关键设计决策：
- Lua协程(coroutine.yield)天然支持这个模式
- 和Python的asyncio可以无缝对接
- 这是选择Lua而非其他脚本语言的重要原因
"""

import asyncio
import logging
import traceback
from typing import Any, Dict, List, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import uuid


# 配置日志记录器
logger = logging.getLogger(__name__)


class ScriptState(Enum):
    """脚本执行状态枚举"""
    IDLE = "idle"             # 空闲
    RUNNING = "running"       # 运行中
    WAITING_INPUT = "waiting"  # 等待输入
    PAUSED = "paused"         # 暂停
    COMPLETED = "completed"   # 完成
    ERROR = "error"           # 错误


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
    CHOICE = "choice"         # 等待选择
    INPUT = "input"           # 等待文本输入
    CLICK = "click"           # 等待点击
    TIMER = "timer"           # 等待计时器


@dataclass
class WaitRequest:
    """等待请求"""
    wait_type: WaitType
    future: asyncio.Future
    options: Optional[List[str]] = None
    prompt: Optional[str] = None
    timeout: Optional[float] = None
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())


class ScriptScheduler:
    """
    脚本调度器

    这是引擎的心脏，负责协调Lua脚本的执行、暂停和恢复。
    通过asyncio实现非阻塞的脚本控制。

    使用示例：
        scheduler = ScriptScheduler(event_bus, sandbox)

        # 启动一个事件脚本
        await scheduler.run_script("events/story/intro.lua")

        # 处理用户选择
        scheduler.resolve_wait(choice_index=1)

        # 暂停所有脚本
        scheduler.pause_all()

        # 恢复所有脚本
        scheduler.resume_all()
    """

    def __init__(
        self,
        event_bus: Any,
        sandbox: Any,
        game_context: Any
    ):
        """
        初始化脚本调度器

        Args:
            event_bus: 事件总线实例
            sandbox: Lua沙箱实例
            game_context: 游戏上下文实例
        """
        self.event_bus = event_bus
        self.sandbox = sandbox
        self.context = game_context

        # 当前活动的脚本任务
        self._current_task: Optional[asyncio.Task] = None
        self._current_script: Optional[ScriptInfo] = None

        # 等待队列
        self._pending_waits: Dict[str, WaitRequest] = {}
        self._wait_counter: int = 0

        # 脚本状态
        self._state: ScriptState = ScriptState.IDLE

        # 脚本历史记录
        self._script_history: List[ScriptInfo] = []
        self._max_history: int = 50

        # 事件监听器清理函数
        self._listeners: List[Callable] = []

        # 注册事件监听
        self._register_event_listeners()

        logger.info("脚本调度器初始化完成")

    def _register_event_listeners(self) -> None:
        """注册事件监听器"""

        # UI输入事件处理
        def on_choice_made(choice_index: int, **kwargs):
            self.resolve_wait(choice_index=choice_index)

        def on_input_received(text: str, **kwargs):
            self.resolve_wait(input_text=text)

        def on_ui_click(**kwargs):
            self.resolve_wait()

        # 注册监听器
        self._listeners.extend([
            self.event_bus.subscribe("ui.choice_made", on_choice_made),
            self.event_bus.subscribe("ui.input_received", on_input_received),
            self.event_bus.subscribe("ui.clicked", on_ui_click),
        ])

    @property
    def state(self) -> ScriptState:
        """获取当前调度器状态"""
        return self._state

    @property
    def current_script(self) -> Optional[ScriptInfo]:
        """获取当前执行的脚本信息"""
        return self._current_script

    async def run_script(
        self,
        script_path: str,
        **kwargs: Any
    ) -> bool:
        """
        运行脚本

        Args:
            script_path: 脚本文件路径（相对于data/events目录）
            **kwargs: 传递给脚本的额外参数

        Returns:
            bool: 是否成功执行
        """
        if self._state == ScriptState.RUNNING:
            logger.warning("已有脚本在运行中")
            return False

        full_path = self._resolve_script_path(script_path)
        logger.info(f"开始执行脚本: {full_path}")

        # 创建脚本信息
        script_info = ScriptInfo(
            path=full_path,
            name=Path(script_path).stem
        )
        self._current_script = script_info
        self._script_history.append(script_info)

        # 限制历史记录大小
        if len(self._script_history) > self._max_history:
            self._script_history = self._script_history[-self._max_history:]

        try:
            self._state = ScriptState.RUNNING
            script_info.state = ScriptState.RUNNING

            # 在沙箱中执行脚本
            result = await self._execute_in_sandbox(full_path, **kwargs)

            script_info.state = ScriptState.COMPLETED
            self._state = ScriptState.IDLE
            logger.info(f"脚本执行完成: {script_info.name}")

            # 触发脚本完成事件
            self.event_bus.emit("script.completed", script=script_info.name)

            return True

        except asyncio.CancelledError:
            script_info.state = ScriptState.IDLE
            self._state = ScriptState.IDLE
            logger.info(f"脚本被取消: {script_info.name}")
            raise

        except Exception as e:
            error_msg = f"脚本执行错误: {e}"
            logger.error(error_msg, exc_info=True)
            script_info.state = ScriptState.ERROR
            script_info.error = str(e)
            self._state = ScriptState.ERROR

            # 触发错误事件
            self.event_bus.emit("script.error", script=script_info.name, error=str(e))

            return False

        finally:
            self._current_script = None
            self._clear_pending_waits()

    async def _execute_in_sandbox(
        self,
        script_path: str,
        **kwargs: Any
    ) -> Any:
        """
        在沙箱中执行脚本

        Args:
            script_path: 脚本路径
            **kwargs: 额外参数

        Returns:
            Any: 脚本执行结果
        """
        # 获取Lua运行时
        lua = self.sandbox.get_runtime()

        # 加载脚本文件
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                script_code = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"脚本文件不存在: {script_path}")
        except Exception as e:
            raise RuntimeError(f"读取脚本文件失败: {e}")

        # 执行脚本
        try:
            # 设置全局参数
            for key, value in kwargs.items():
                lua.globals()[key] = value

            # 执行主chunk
            result = lua.execute(script_code)

            return result

        except Exception as e:
            # Lua执行错误
            logger.error(f"Lua执行错误: {e}")
            raise

    def wait_for_choice(self) -> int:
        """
        等待玩家选择

        这是一个阻塞调用，会暂停脚本执行直到玩家做出选择。
        实际上是通过asyncio实现的异步等待。

        Returns:
            int: 玩家选择的索引（从1开始）
        """
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        # 创建等待请求
        wait_request = WaitRequest(
            wait_type=WaitType.CHOICE,
            future=future
        )

        wait_id = self._add_pending_wait(wait_request)

        # 发送选择菜单显示事件
        self.event_bus.emit("ui.choice_wait", wait_id=wait_id)

        # 标记状态
        self._state = ScriptState.WAITING_INPUT
        if self._current_script:
            self._current_script.state = ScriptState.WAITING_INPUT

        # 异步等待结果
        try:
            result = loop.run_until_complete(future)
            return result if result else 1
        except asyncio.CancelledError:
            logger.warning("等待选择被取消")
            return 0

    def wait_for_input(self) -> str:
        """
        等待玩家输入文本

        Returns:
            str: 玩家输入的文本
        """
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        wait_request = WaitRequest(
            wait_type=WaitType.INPUT,
            future=future
        )

        wait_id = self._add_pending_wait(wait_request)

        # 发送输入框显示事件
        self.event_bus.emit("ui.input_wait", wait_id=wait_id)

        self._state = ScriptState.WAITING_INPUT
        if self._current_script:
            self._current_script.state = ScriptState.WAITING_INPUT

        try:
            result = loop.run_until_complete(future)
            return result if result else ""
        except asyncio.CancelledError:
            logger.warning("等待输入被取消")
            return ""

    def wait_for_click(self, timeout: Optional[float] = None) -> bool:
        """
        等待玩家点击

        Args:
            timeout: 超时时间（秒）

        Returns:
            bool: 是否在超时前收到点击
        """
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        wait_request = WaitRequest(
            wait_type=WaitType.CLICK,
            future=future,
            timeout=timeout
        )

        wait_id = self._add_pending_wait(wait_request)

        self.event_bus.emit("ui.click_wait", wait_id=wait_id)

        self._state = ScriptState.WAITING_INPUT
        if self._current_script:
            self._current_script.state = ScriptState.WAITING_INPUT

        try:
            if timeout:
                result = loop.run_until_complete(
                    asyncio.wait_for(future, timeout=timeout)
                )
            else:
                result = loop.run_until_complete(future)
            return True
        except asyncio.TimeoutError:
            logger.debug("等待点击超时")
            self._remove_wait(wait_id)
            return False
        except asyncio.CancelledError:
            logger.warning("等待点击被取消")
            return False

    def resolve_wait(
        self,
        choice_index: Optional[int] = None,
        input_text: Optional[str] = None,
        wait_id: Optional[str] = None
    ) -> bool:
        """
        解决等待状态

        当玩家做出选择或输入时调用，恢复脚本执行。

        Args:
            choice_index: 选择索引
            input_text: 输入文本
            wait_id: 特定的等待ID（可选，默认解决最新的）

        Returns:
            bool: 是否成功解决
        """
        # 如果没有指定wait_id，使用最新的
        if not wait_id:
            if not self._pending_waits:
                logger.warning("没有待解决的等待")
                return False
            wait_id = max(self._pending_waits.keys(), key=lambda k: self._pending_waits[k].created_at)

        if wait_id not in self._pending_waits:
            logger.warning(f"等待ID不存在: {wait_id}")
            return False

        wait_request = self._pending_waits[wait_id]

        # 验证等待类型
        if wait_request.wait_type == WaitType.CHOICE and choice_index is None:
            logger.error("CHOICE类型等待需要choice_index")
            return False

        if wait_request.wait_type == WaitType.INPUT and input_text is None:
            logger.error("INPUT类型等待需要input_text")
            return False

        # 设置结果
        if not wait_request.future.done():
            if choice_index is not None:
                wait_request.future.set_result(choice_index)
            elif input_text is not None:
                wait_request.future.set_result(input_text)
            else:
                wait_request.future.set_result(True)

        # 清理
        self._remove_wait(wait_id)

        # 恢复状态
        self._state = ScriptState.RUNNING
        if self._current_script:
            self._current_script.state = ScriptState.RUNNING

        logger.debug(f"等待已解决: {wait_id}")
        return True

    def cancel_wait(self, wait_id: Optional[str] = None) -> bool:
        """
        取消等待状态

        Args:
            wait_id: 等待ID（可选，默认取消所有）

        Returns:
            bool: 是否成功取消
        """
        if wait_id:
            if wait_id in self._pending_waits:
                self._pending_waits[wait_id].future.cancel()
                self._remove_wait(wait_id)
                return True
            return False
        else:
            # 取消所有等待
            for wait in self._pending_waits.values():
                wait.future.cancel()
            self._pending_waits.clear()
            self._state = ScriptState.IDLE
            return True

    def pause_all(self) -> None:
        """暂停所有脚本执行"""
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            self._state = ScriptState.PAUSED
            if self._current_script:
                self._current_script.state = ScriptState.PAUSED
            logger.info("脚本已暂停")

    async def resume_all(self) -> None:
        """恢复暂停的脚本"""
        # 重新执行当前脚本
        if self._current_script:
            self._state = ScriptState.RUNNING
            if self._current_script:
                self._current_script.state = ScriptState.RUNNING
            logger.info("脚本已恢复")

    def stop_all(self) -> None:
        """停止所有脚本执行"""
        self.cancel_all()
        if self._current_script:
            self._current_script.state = ScriptState.IDLE
        self._current_script = None
        self._state = ScriptState.IDLE
        logger.info("所有脚本已停止")

    def _add_pending_wait(self, wait_request: WaitRequest) -> str:
        """添加待处理的等待请求"""
        self._wait_counter += 1
        wait_id = f"wait_{self._wait_counter}"
        self._pending_waits[wait_id] = wait_request
        return wait_id

    def _remove_wait(self, wait_id: str) -> None:
        """移除等待请求"""
        if wait_id in self._pending_waits:
            del self._pending_waits[wait_id]

    def _clear_pending_waits(self) -> None:
        """清空所有等待请求"""
        for wait in self._pending_waits.values():
            if not wait.future.done():
                wait.future.cancel()
        self._pending_waits.clear()

    def _resolve_script_path(self, relative_path: str) -> str:
        """解析脚本路径"""
        # 可以在这里添加路径验证和安全检查
        base_dir = Path("data/events")
        full_path = base_dir / relative_path

        # 防止路径遍历攻击
        resolved = full_path.resolve()
        if not str(resolved).startswith(str(base_dir.resolve())):
            raise SecurityError(f"禁止的脚本路径: {relative_path}")

        return str(resolved)

    def get_waiting_scripts(self) -> List[Dict[str, Any]]:
        """获取当前等待输入的脚本信息"""
        return [
            {
                "wait_id": wait_id,
                "wait_type": wait.wait_type.value,
                "created_at": wait.created_at,
            }
            for wait_id, wait in self._pending_waits.items()
        ]

    def get_script_history(self) -> List[ScriptInfo]:
        """获取脚本执行历史"""
        return self._script_history.copy()

    def cleanup(self) -> None:
        """清理资源"""
        self.stop_all()

        # 移除事件监听器
        for unsubscribe in self._listeners:
            try:
                unsubscribe()
            except Exception as e:
                logger.warning(f"移除监听器失败: {e}")

        self._listeners.clear()
        logger.info("脚本调度器已清理")

    def __del__(self):
        """析构函数"""
        try:
            self.cleanup()
        except Exception:
            pass


class SecurityError(Exception):
    """安全错误异常"""
    pass
