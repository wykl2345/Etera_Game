"""WebSocket 网关 —— 前后端桥梁（ADR-0001 / 协议见 docs/architecture.md §四）。

- 单连接单会话（无断线恢复，断线即结束本局）
- 引擎 → 前端：scheduler.output 经 asyncio.Queue 串行推送（脚本线程安全）
- 前端 → 引擎：game.start / choice.made / input.submit（requestId 匹配）
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
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


class DialogueRecorder(UIOutput):
    """记录显示类消息，供存档写入对话快照。

    包装真实 output：所有消息照常转发，只旁路保存"画面类"消息
    （文本/背景/立绘/图片/清屏）。控制类消息（save.result 等）不记录。

    生命周期：每次触发事件前调用 begin() 清空 —— 因此快照内容 = 最近一个
    事件产生的完整对话，与"存档点在事件边界"的约束一致。
    """

    KEEP_TYPES = frozenset({
        "ui.text", "ui.clear",
        "ui.background_set",
        "ui.character_show", "ui.character_hide",
        "ui.image_show", "ui.image_hide",
    })

    def __init__(self, inner: UIOutput) -> None:
        self._inner = inner
        self._entries: list = []
        self._lock = threading.Lock()

    def send(self, msg: Dict[str, Any]) -> None:
        self._inner.send(msg)
        if msg.get("type") in self.KEEP_TYPES:
            with self._lock:
                self._entries.append(msg)

    def begin(self) -> None:
        """新事件开始：清空快照。"""
        with self._lock:
            self._entries.clear()

    def snapshot(self) -> list:
        with self._lock:
            return list(self._entries)


async def _sender(websocket: Any, queue: asyncio.Queue) -> None:
    """单一发送任务：串行取队列消息发送，避免并发 send。"""
    while True:
        msg = await queue.get()
        try:
            await websocket.send(json.dumps(msg, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001 - 连接关闭即结束
            logger.debug("发送失败（连接已关闭）: %s", exc)
            return


def _send_saves_list(bundle: Any, output: UIOutput) -> None:
    """推送存档槽位列表（saves.list）。"""
    slots = []
    for s in bundle.save_manager.get_save_slots():
        meta = None
        if s.metadata is not None:
            meta = {
                "version": s.metadata.version,
                "save_time": s.metadata.save_time,
                "day": s.metadata.day,
                "location": s.metadata.location,
                "description": s.metadata.description,
                "playtime": s.metadata.playtime,
            }
        slots.append({"slot_id": s.slot_id, "exists": s.exists, "metadata": meta})
    output.send({"type": "saves.list", "payload": {"slots": slots}})


def _persist_blocked(bundle: Any) -> Optional[str]:
    """对话/交互进行中禁止存读档。

    原因：存档只序列化 GameContext（world/player/characters/flags），而对话
    文本、立绘、选项全在前端 store 里，后端不知道。此时存档会存出"数据在新
    位置、画面在半截"的不一致档，读回来也无法对齐。所以要求脚本空闲时才能
    存读档 —— 即"在触发对话前使用"。
    """
    if bundle.scheduler.is_waiting():
        return "对话进行中（等待选择/输入），请先完成当前对话"
    return None


async def handle_connection(
    websocket: Any,
    scripts_dir: str,
    characters_dir: str,
    saves_dir: str = "saves",
    debug_mode: bool = False,
) -> None:
    """单个 WS 连接的会话生命周期。"""
    loop = asyncio.get_running_loop()
    output = WSOutput()
    queue: asyncio.Queue = asyncio.Queue()
    output.attach(loop, queue)
    sender_task = asyncio.create_task(_sender(websocket, queue))

    # 对话快照记录器（包装 output；控制类消息不进快照）
    recorder = DialogueRecorder(output)

    # 每连接独立引擎实例（会话隔离）
    bundle = init_engine(recorder, scripts_dir=scripts_dir,
                         characters_dir=characters_dir, saves_dir=saves_dir,
                         debug_mode=debug_mode)

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
            # 总是硬重置：reset_game 内部 stop_all 中止上一局挂起脚本
            from engine.bootstrap import reset_game

            def start_new() -> None:
                reset_game(bundle)
                recorder.begin()
                bundle.bus.emit("on_game_start")

            active_game = loop.run_in_executor(executor, start_new)
        elif mtype == "game.abort":
            # 返回主菜单：中止挂起脚本，释放单 worker executor（否则下次 game.start 排队卡死）
            bundle.scheduler.stop_all()
            bundle.scheduler.reset_abort()
        elif mtype == "game.day_advance":
            # 日循环：day+1 → on_day_end → on_day_begin（日常事件触发点）
            blocked = _persist_blocked(bundle)
            if blocked:
                output.send({"type": "day.result",
                             "payload": {"ok": False, "reason": blocked}})
            else:
                def advance() -> None:
                    recorder.begin()
                    bundle.ctx.set_day(bundle.ctx.get_day() + 1)
                    bundle.api._push_status()
                    # 回执先发：日常剧本可能阻塞在 ask_choice，不能等它跑完
                    output.send({"type": "day.result",
                                 "payload": {"ok": True, "day": bundle.ctx.get_day()}})
                    bundle.bus.emit("on_day_end")
                    bundle.bus.emit("on_day_begin")

                loop.run_in_executor(executor, advance)
        elif mtype == "game.emit_event":
            # 前端主动触发自定义事件（如工具条「自检」→ custom:run_selftest）。
            # 与 game.start 同理不 await：剧本可能阻塞在 ask_choice。
            event_name = str(payload.get("event", "")).strip()
            blocked = _persist_blocked(bundle)
            if not event_name:
                output.send({"type": "event.result",
                             "payload": {"ok": False, "reason": "缺少 event 名"}})
            elif blocked:
                output.send({"type": "event.result",
                             "payload": {"ok": False, "event": event_name, "reason": blocked}})
            else:
                recorder.begin()
                loop.run_in_executor(executor, bundle.bus.emit, event_name)
                output.send({"type": "event.result",
                             "payload": {"ok": True, "event": event_name}})
        elif mtype == "game.save":
            slot_id = int(payload.get("slot_id", 0))
            blocked = _persist_blocked(bundle)
            if blocked:
                output.send({"type": "save.result",
                             "payload": {"ok": False, "slot_id": slot_id, "reason": blocked}})
            else:
                ok = bundle.save_manager.save(
                    slot_id, description=str(payload.get("description", "")),
                    dialogue=recorder.snapshot(),
                )
                output.send({"type": "save.result",
                             "payload": {"ok": ok, "slot_id": slot_id,
                                         "reason": None if ok else "写入存档失败"}})
                _send_saves_list(bundle, output)
        elif mtype == "game.load":
            slot_id = int(payload.get("slot_id", 0))
            blocked = _persist_blocked(bundle)
            if blocked:
                output.send({"type": "load.result",
                             "payload": {"ok": False, "slot_id": slot_id, "reason": blocked}})
            else:
                ok = bundle.save_manager.load(slot_id)
                output.send({"type": "load.result",
                             "payload": {"ok": ok, "slot_id": slot_id,
                                         "reason": None if ok else "读取存档失败",
                                         "dialogue": bundle.save_manager._last_dialogue}})
                if ok:
                    bundle.api._push_status()
                    # 触发 on_load 系统事件：剧本可监听恢复剧情
                    loop.run_in_executor(executor, bundle.bus.emit, "on_load")
        elif mtype == "game.quick_save":
            blocked = _persist_blocked(bundle)
            if blocked:
                output.send({"type": "save.result",
                             "payload": {"ok": False, "slot_id": 0, "quick": True, "reason": blocked}})
            else:
                ok = bundle.save_manager.quick_save(dialogue=recorder.snapshot())
                output.send({"type": "save.result",
                             "payload": {"ok": ok, "slot_id": 0, "quick": True,
                                         "reason": None if ok else "写入存档失败"}})
                _send_saves_list(bundle, output)
        elif mtype == "game.quick_load":
            blocked = _persist_blocked(bundle)
            if blocked:
                output.send({"type": "load.result",
                             "payload": {"ok": False, "slot_id": 0, "quick": True, "reason": blocked}})
            else:
                ok = bundle.save_manager.quick_load()
                output.send({"type": "load.result",
                             "payload": {"ok": ok, "slot_id": 0, "quick": True,
                                         "reason": None if ok else "读取存档失败",
                                         "dialogue": bundle.save_manager._last_dialogue}})
                if ok:
                    bundle.api._push_status()
        elif mtype == "game.list_saves":
            _send_saves_list(bundle, output)
        elif mtype == "game.delete_save":
            slot_id = int(payload.get("slot_id", 0))
            ok = bundle.save_manager.delete(slot_id)
            output.send({"type": "delete.result", "payload": {"ok": ok, "slot_id": slot_id}})
            _send_saves_list(bundle, output)
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
        elif mtype == "minigame.result":
            # 小游戏结果回传：恢复挂起的 minigame.start 协程
            bundle.scheduler.resolve_wait(
                str(msg.get("requestId", "")),
                result=payload.get("result") if isinstance(payload.get("result"), dict) else {},
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
    saves_dir: str = "saves",
    debug_mode: bool = False,
) -> None:
    """启动 WS 服务（websockets>=14 新版 asyncio API）。"""
    from websockets.asyncio.server import serve as ws_serve

    async def handler(websocket: Any) -> None:
        await handle_connection(
            websocket, scripts_dir=scripts_dir,
            characters_dir=characters_dir, saves_dir=saves_dir,
            debug_mode=debug_mode,
        )

    async with ws_serve(handler, host, port) as server:
        logger.info("WS 服务启动: ws://%s:%s", host, port)
        await asyncio.Future()  # 永久运行
