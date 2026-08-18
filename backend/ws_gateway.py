"""WebSocket 网关 —— 前后端桥梁（ADR-0001 / 协议见 docs/architecture.md §四）。

- 单连接单会话（无断线恢复，断线即结束本局）
- 引擎 → 前端：scheduler.output 经 asyncio.Queue 串行推送（脚本线程安全）
- 前端 → 引擎：game.start / choice.made / input.submit（requestId 匹配）
"""
from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from engine.bootstrap import init_engine
from engine.script_runner import UIOutput

logger = logging.getLogger(__name__)


class WSOutput(UIOutput):
    """线程安全的 UI 输出通道：脚本线程 put 队列，asyncio 主循环串行发送。"""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[asyncio.Queue] = None

    def attach(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        self._loop = loop
        self._queue = queue

    def send(self, msg: Dict[str, Any]) -> None:
        if self._queue is None or self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._queue.put(msg), self._loop)


async def _sender(websocket: Any, queue: asyncio.Queue) -> None:
    """单一发送任务：串行取队列消息发送，避免并发 send。"""
    while True:
        msg = await queue.get()
        try:
            await websocket.send(json.dumps(msg, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001 - 连接关闭即结束
            logger.debug("发送失败（连接已关闭）: %s", exc)
            return


async def handle_connection(
    websocket: Any,
    scripts_dir: str,
    characters_dir: str,
    debug_mode: bool = False,
) -> None:
    """单个 WS 连接的会话生命周期。"""
    loop = asyncio.get_running_loop()
    output = WSOutput()
    queue: asyncio.Queue = asyncio.Queue()
    output.attach(loop, queue)
    sender_task = asyncio.create_task(_sender(websocket, queue))

    # 每连接独立引擎实例（会话隔离）
    bundle = init_engine(output, scripts_dir=scripts_dir,
                         characters_dir=characters_dir, debug_mode=debug_mode)

    # 每连接专属游戏线程池（单 worker）：脚本执行不可阻塞消息循环。
    # 关键：不 await —— 脚本会在 ask_choice 挂起等待输入，主循环必须继续
    # 接收 choice.made 才能 resolve_wait 恢复脚本。
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="game")
    active_game: Optional[Any] = None

    async for raw in websocket:
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("非法消息: %r", raw)
            continue
        mtype = msg.get("type", "")
        payload = msg.get("payload") or {}

        if mtype == "game.start":
            if active_game is not None and not active_game.done():
                logger.warning("已有进行中的游戏会话，忽略重复 game.start")
                continue
            active_game = loop.run_in_executor(
                executor, bundle.bus.emit, "on_game_start"
            )
        elif mtype == "game.day_advance":
            # 日循环：day+1 → on_day_end → on_day_begin（日常事件触发点）
            def advance() -> None:
                bundle.ctx.set_day(bundle.ctx.get_day() + 1)
                bundle.bus.emit("on_day_end")
                bundle.bus.emit("on_day_begin")

            loop.run_in_executor(executor, advance)
        elif mtype == "choice.made":
            bundle.scheduler.resolve_wait(
                str(msg.get("requestId", "")),
                choice_index=payload.get("index"),
            )
        elif mtype == "input.submit":
            bundle.scheduler.resolve_wait(
                str(msg.get("requestId", "")),
                input_text=payload.get("text"),
            )
        else:
            logger.debug("未处理消息类型: %s", mtype)

    # 连接关闭：中止挂起的脚本，结束 sender
    bundle.scheduler.stop_all()
    executor.shutdown(wait=False)
    sender_task.cancel()
    try:
        await sender_task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass


async def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    scripts_dir: str = "data/scenarios",
    characters_dir: str = "data/characters",
    debug_mode: bool = False,
) -> None:
    """启动 WS 服务（websockets>=14 新版 asyncio API）。"""
    from websockets.asyncio.server import serve as ws_serve

    async def handler(websocket: Any) -> None:
        await handle_connection(
            websocket, scripts_dir=scripts_dir,
            characters_dir=characters_dir, debug_mode=debug_mode,
        )

    async with ws_serve(handler, host, port) as server:
        logger.info("WS 服务启动: ws://%s:%s", host, port)
        await asyncio.Future()  # 永久运行
