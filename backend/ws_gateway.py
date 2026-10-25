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

from engine.api_bridge import STAT_LABELS
from engine.bootstrap import init_engine
from engine.script_runner import ScriptAbortedError, UIOutput

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


# 商店回收价 = 基准价 × 该比例
SELL_RATIO = 0.5

# 一天内的时段顺序（dawn 是剧本专用时刻，不参与日常推进）
TIME_ORDER = ["morning", "afternoon", "evening", "night"]


def _spend_time(bundle: Any) -> str:
    """执行一次 Hub 行动消耗一个时段，返回推进后的时段。

    已到 night 就不再推进（夜里可以继续行动，但时间停住），
    由「睡觉」推进到第二天。
    """
    cur = bundle.ctx.get_time_of_day().value
    idx = TIME_ORDER.index(cur) if cur in TIME_ORDER else 0
    if idx < len(TIME_ORDER) - 1:
        nxt = TIME_ORDER[idx + 1]
        bundle.ctx.set_time_of_day(nxt)
        bundle.api._push_status()
        return nxt
    return cur

# 关系阶段门槛（与 v1 设计文档一致：敌视 → 伴侣）
_RELATION_STAGES = [
    (-100, -50, "敌视", "hostile"),
    (-49, -10, "疏远", "distant"),
    (-9, 9, "中立", "neutral"),
    (10, 29, "友人", "friendly"),
    (30, 59, "亲密", "close"),
    (60, 79, "恋爱", "love"),
    (80, 100, "伴侣", "soulmate"),
]


def _relation_stage(relation: int) -> Dict[str, str]:
    for lo, hi, label, key in _RELATION_STAGES:
        if lo <= relation <= hi:
            return {"label": label, "key": key}
    return {"label": "中立", "key": "neutral"}


def _characters_payload(bundle: Any) -> Dict[str, Any]:
    """角色一览 / 详情共用的数据（角色数量少，一次给全前端算排序）。

    关系阶段：剧本用 data.set_stage 显式设置过就以它为准（突破事件推进），
    否则回退到按好感度推算，兼容还没做突破事件的角色。
    """
    items = []
    for cid, ch in bundle.ctx.get_all_characters().items():
        auto_stage = _relation_stage(ch.relation)
        stage = ch.stage or auto_stage["key"]
        stage_label = next(
            (label for _lo, _hi, label, key in _RELATION_STAGES if key == stage),
            auto_stage["label"],
        )
        items.append({
            "char_id": cid,
            "name": ch.name,
            "title": ch.title,
            "tags": list(ch.tags),
            "relation": ch.relation,
            "relation_stage": {
                "key": stage,
                "label": stage_label,
                # 是否由突破事件显式设定（前端可据此显示"已突破"）
                "explicit": bool(ch.stage),
                "auto_label": auto_stage["label"],
            },
            "location": ch.location,
            "stats": ch.stats.to_dict(),
            "flags": ch.flags.to_dict(),
            "extra": dict(ch.extra),
            "extra_labels": dict(ch.extra_labels),
            "history": list(ch.history),
        })
    return {"characters": items}


def _action_used(bundle: Any, action_key: str) -> int:
    """当天某行动已用次数（键里带天数，跨天自动归零）。"""
    day = bundle.ctx.get_day()
    return int(bundle.ctx.get_global_flag("_action", f"{action_key}:{day}", 0))


def _mark_action_used(bundle: Any, action_key: str) -> None:
    day = bundle.ctx.get_day()
    key = f"{action_key}:{day}"
    cur = int(bundle.ctx.get_global_flag("_action", key, 0))
    bundle.ctx.set_global_flag("_action", key, cur + 1)


def _find_button(bundle: Any, event_name: str) -> Any:
    for btn in getattr(bundle, "hub_buttons", None) or []:
        if btn.event == event_name:
            return btn
    return None


def _hub_payload(bundle: Any) -> Dict[str, Any]:
    """Hub 数据：当前场景 + 该场景下的角色 + 可用行动按钮。

    过滤规则（与玩家约定一致）：
      - **条件不满足 → 隐藏**：好感门槛、前置 flag、hide_flag、角色不在本场景
      - **暂时不可用 → 变灰**：体力不足、当天次数用完
    """
    scenes = getattr(bundle, "scenes", None)
    catalog = getattr(bundle, "catalog", None)
    scene_id = bundle.ctx.get_location()
    scene = scenes.get(scene_id) if scenes else None
    scene_info = {
        "id": scene_id,
        "name": scenes.name_of(scene_id) if scenes else (scene_id or "未知地点"),
        "region_name": scenes.region_name(scene.region) if scene else "",
        "desc": scene.desc if scene else "",
        "can_sleep": scenes.can_sleep(scene_id) if scenes else False,
        # 有商店的地点才有值，前端据此显示「购物」
        "shop": {"id": scene.shop, "name": catalog.shop(scene.shop).name}
        if (scene and scene.shop and catalog and catalog.shop(scene.shop)) else None,
        # 可达地点（带 same_region 标记，前端分「本区域内 / 前往其他区域」）
        "adjacent": scenes.reachable(scene_id) if scenes else [],
    }

    # 只显示与玩家同场景的角色
    chars = [
        {"char_id": cid, "name": ch.name, "relation": ch.relation,
         "location": ch.location}
        for cid, ch in bundle.ctx.get_all_characters().items()
        if ch.location == scene_id
    ]

    stamina = bundle.ctx.get_player_stat("stamina", 0)
    items = []
    for btn in getattr(bundle, "hub_buttons", None) or []:
        # ── 隐藏类条件 ──
        hide_flag = getattr(btn, "hide_flag", None)
        if hide_flag:
            hns, _, hkey = str(hide_flag).partition(".")
            if bundle.ctx.get_global_flag(hns, hkey, False):
                continue
        if btn.require_flag:
            ns, _, key = str(btn.require_flag).partition(".")
            if not bundle.ctx.get_global_flag(ns, key, False):
                continue
        if btn.require_relation is not None:
            if bundle.ctx.get_character_relation(btn.char) < btn.require_relation:
                continue
        # 时段 / 天数条件（不满足同样隐藏）
        req_time = getattr(btn, "require_time", "")
        if req_time and bundle.ctx.get_time_of_day().value != req_time:
            continue
        req_day = getattr(btn, "require_day_min", 0) or 0
        if req_day and bundle.ctx.get_day() < req_day:
            continue

        # 角色必须在当前场景
        char_state = bundle.ctx.get_character(btn.char)
        if char_state is None or char_state.location != scene_id:
            continue

        # ── 变灰类条件 ──
        available, reason = True, None
        daily_limit = getattr(btn, "daily_limit", 0) or 0
        if daily_limit > 0:
            used = _action_used(bundle, btn.event)
            if used >= daily_limit:
                available, reason = False, f"今天已用 {used}/{daily_limit} 次"
        stamina_cost = getattr(btn, "stamina_cost", 0) or 0
        if available and stamina_cost > 0 and stamina < stamina_cost:
            available, reason = False, f"体力不足（需要 {stamina_cost}）"

        d = btn.to_dict()
        d["available"] = available
        d["reason"] = reason
        d["used_today"] = _action_used(bundle, btn.event) if daily_limit else None
        items.append(d)

    items.sort(key=lambda b: (b["char"], b["order"]))
    chars.sort(key=lambda c: c["char_id"])
    return {"scene": scene_info, "characters": chars, "buttons": items}


def _send_characters(bundle: Any, output: UIOutput) -> None:
    output.send({"type": "characters.list", "payload": _characters_payload(bundle)})


def _send_hub(bundle: Any, output: UIOutput) -> None:
    output.send({"type": "hub.buttons", "payload": _hub_payload(bundle)})


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


def _drain_future(fut: Any) -> None:
    """取走 executor Future 的异常，避免 asyncio 报 "never retrieved"。

    restart / 断线时 stop_all 会中止挂起脚本，ScriptAbortedError 是预期行为，
    不应当成错误刷日志 —— 其余异常照常记录。
    """
    if fut is None:
        return
    try:
        fut.result()
    except ScriptAbortedError:
        logger.info("脚本已中止（restart / disconnect），属预期行为")
    except Exception:  # noqa: BLE001
        logger.exception("事件执行异常")


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

            def _on_intro_done(_fut: Any) -> None:
                # 序章（on_game_start）播完 → 通知前端回 Hub
                output.send({"type": "event.done", "payload": {"event": "on_game_start"}})
                _send_hub(bundle, output)

            if active_game is not None:
                active_game.add_done_callback(_on_intro_done)
                active_game.add_done_callback(_drain_future)
            # 注意：此处不推 hub —— reset_game 还在 executor 里跑，角色尚未载入，
            # 现在推会得到空角色列表。由 _on_intro_done（序章播完）统一推送。
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
                    # 新的一天从早晨开始（时间系统框架规则，不交给剧本）
                    bundle.ctx.set_time_of_day("morning")
                    bundle.api._push_status()
                    # 回执先发：日常剧本可能阻塞在 ask_choice，不能等它跑完
                    output.send({"type": "day.result",
                                 "payload": {"ok": True, "day": bundle.ctx.get_day()}})
                    bundle.bus.emit("on_day_end")
                    bundle.bus.emit("on_day_begin")
                    # 日常事件全部结束 → 通知前端回 Hub 并刷新
                    output.send({"type": "event.done", "payload": {"event": "day_advance"}})
                    _send_hub(bundle, output)
                    _send_characters(bundle, output)

                adv_fut = loop.run_in_executor(executor, advance)
                adv_fut.add_done_callback(_drain_future)
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
                # Hub 行动：按声明扣体力 / 记次数（剧本不必自己再扣）
                btn = _find_button(bundle, event_name)
                if btn is not None:
                    if getattr(btn, "stamina_cost", 0):
                        bundle.ctx.modify_player_stat("stamina", -btn.stamina_cost)
                    if getattr(btn, "daily_limit", 0):
                        _mark_action_used(bundle, event_name)
                    # 角色行动消耗一个时段（移动/购物/查看信息不耗时）
                    _spend_time(bundle)
                    bundle.api._push_status()
                recorder.begin()

                def run_event() -> None:
                    try:
                        bundle.bus.emit(event_name)
                    finally:
                        # 剧本（含阻塞交互）结束 → 通知前端回 Hub 并刷新按钮可用性
                        output.send({"type": "event.done",
                                     "payload": {"event": event_name}})
                        _send_hub(bundle, output)
                        _send_characters(bundle, output)

                ev_fut = loop.run_in_executor(executor, run_event)
                ev_fut.add_done_callback(_drain_future)
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
                    load_fut = loop.run_in_executor(executor, bundle.bus.emit, "on_load")
                    load_fut.add_done_callback(_drain_future)
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
        elif mtype == "game.hub":
            # 前端进入 Hub 时拉取：角色卡片 + 行动按钮 + 可用性。
            # 同时清空对话快照 —— Hub 是"没有对话"的状态，此时存档不应
            # 记录上一个事件的对话（否则读档会莫名重放旧剧情）。
            recorder.begin()
            _send_hub(bundle, output)
        elif mtype == "game.move":
            target = str(payload.get("scene", ""))
            scenes = getattr(bundle, "scenes", None)
            current = bundle.ctx.get_location()
            if scenes is None or not scenes.exists(target):
                output.send({"type": "move.result",
                             "payload": {"ok": False, "reason": "未知地点"}})
            elif not scenes.can_travel_to(current, target):
                output.send({"type": "move.result",
                             "payload": {"ok": False, "reason": "这里去不了"}})
            else:
                bundle.ctx.set_location(target)
                bundle.api._push_status()
                output.send({"type": "move.result",
                             "payload": {"ok": True, "scene": target,
                                         "name": scenes.name_of(target)}})
                _send_hub(bundle, output)
        elif mtype == "game.home":
            # 主角功能栏的「回家」：无视相邻规则直接回自宅
            scenes = getattr(bundle, "scenes", None)
            home_scene = "home"
            if scenes is not None and scenes.exists(home_scene):
                bundle.ctx.set_location(home_scene)
                bundle.api._push_status()
                output.send({"type": "move.result",
                             "payload": {"ok": True, "scene": home_scene,
                                         "name": scenes.name_of(home_scene)}})
                _send_hub(bundle, output)
            else:
                output.send({"type": "move.result",
                             "payload": {"ok": False, "reason": "没有可回的家"}})
        elif mtype == "game.sleep":
            scenes = getattr(bundle, "scenes", None)
            current = bundle.ctx.get_location()
            if scenes is None or not scenes.can_sleep(current):
                output.send({"type": "sleep.result",
                             "payload": {"ok": False,
                                         "reason": f"{scenes.name_of(current) if scenes else '这里'}睡不着"}})
            else:
                def do_sleep() -> None:
                    recorder.begin()
                    # 睡觉恢复体力（上限封顶）
                    max_stamina = bundle.ctx.get_player_stat("max_stamina", 100)
                    bundle.ctx.set_player_stat("stamina", max_stamina)
                    bundle.api._push_status()
                    # 先回执：前端据此切到叙事界面（下一天可能有早晨事件要播）
                    output.send({"type": "sleep.result", "payload": {"ok": True}})
                    bundle.bus.emit("on_day_end")
                    # 推进一天 + 重置时段
                    bundle.ctx.set_day(bundle.ctx.get_day() + 1)
                    bundle.ctx.set_time_of_day("morning")
                    bundle.api._push_status()

                    # on_day_begin 会同步跑所有日常剧本，其中可能有 ask_choice 阻塞；
                    # 因此 event.done 必须放在后面 —— 玩家答完才会执行到这里，
                    # 前端才知道"这一天的事件播完了，可以返回 Hub"。
                    bundle.bus.emit("on_day_begin")
                    output.send({"type": "event.done",
                                 "payload": {"event": "day_advance"}})
                    # 不在这里推 hub：前端返回 Hub 时会主动拉（此刻数据可能已变）

                sleep_fut = loop.run_in_executor(executor, do_sleep)
                sleep_fut.add_done_callback(_drain_future)
        elif mtype == "game.inventory":
            catalog = getattr(bundle, "catalog", None)
            items = []
            for iid, cnt in bundle.ctx.get_inventory().to_dict().items():
                it = catalog.item(iid) if catalog else None
                items.append({
                    "id": iid,
                    "name": it.name if it else iid,
                    "count": cnt,
                    "gift_value": it.gift_value if it else 0,
                    "desc": it.desc if it else "",
                    "category": it.category if it else "item",
                    "category_label": it.category_label if it else "未定义",
                    "usable": bool(it.usable) if it else False,
                    # 回收价：基准价的 50%（物品未定义时按 0）
                    "sell_price": int(it.price * SELL_RATIO) if it else 0,
                })
            items.sort(key=lambda x: x["id"])
            output.send({"type": "inventory.data", "payload": {"items": items}})
        elif mtype == "game.shop":
            # 当前场景的商店商品（价格已按商店 markup 换算）
            scenes = getattr(bundle, "scenes", None)
            catalog = getattr(bundle, "catalog", None)
            shop_id = (scenes.shop_of(bundle.ctx.get_location()) if scenes else "") or ""
            if not shop_id or catalog is None or catalog.shop(shop_id) is None:
                output.send({"type": "shop.data",
                             "payload": {"ok": False, "reason": "这里没有商店"}})
            else:
                goods = catalog.shop_goods(shop_id)
                money = bundle.ctx.get_player_stat("money", 0)
                for g in goods:
                    g["affordable"] = money >= g["price"]
                output.send({"type": "shop.data", "payload": {
                    "ok": True,
                    "shop": {"id": shop_id, "name": catalog.shop(shop_id).name},
                    "goods": goods,
                    "money": money,
                }})
        elif mtype == "game.sell":
            catalog = getattr(bundle, "catalog", None)
            item_id = str(payload.get("item", ""))
            qty = max(1, int(payload.get("count", 1) or 1))
            if bundle.ctx.get_item_count(item_id) < qty:
                output.send({"type": "sell.result",
                             "payload": {"ok": False, "item": item_id,
                                         "reason": "背包里没有这么多"}})
            else:
                it = catalog.item(item_id) if catalog else None
                income = int((it.price if it else 0) * SELL_RATIO) * qty
                bundle.ctx.remove_item(item_id, qty)
                bundle.ctx.modify_player_stat("money", income)
                bundle.api._push_status()
                output.send({"type": "sell.result",
                             "payload": {"ok": True, "item": item_id, "count": qty,
                                         "income": income,
                                         "money": bundle.ctx.get_player_stat("money", 0)}})
                _send_characters(bundle, output)
        elif mtype == "game.use_item":
            catalog = getattr(bundle, "catalog", None)
            item_id = str(payload.get("item", ""))
            it = catalog.item(item_id) if catalog else None
            if it is None:
                output.send({"type": "use.result",
                             "payload": {"ok": False, "reason": "没有这种物品"}})
            elif not it.usable:
                output.send({"type": "use.result",
                             "payload": {"ok": False, "item": item_id,
                                         "reason": f"{it.name}不能使用"}})
            elif bundle.ctx.get_item_count(item_id) < 1:
                output.send({"type": "use.result",
                             "payload": {"ok": False, "item": item_id,
                                         "reason": "背包里没有这件东西"}})
            else:
                # 应用效果（含概率副作用）
                applied = []
                for eff in it.use_effects:
                    chance = float(eff.get("chance", 1.0))
                    if chance < 1.0 and random.random() > chance:
                        continue
                    stat = eff.get("stat")
                    delta = eff.get("delta")
                    if stat and delta is not None:
                        bundle.ctx.modify_player_stat(str(stat), int(delta))
                        label = STAT_LABELS.get(str(stat), str(stat))
                        applied.append(f"{label}{int(delta):+d}")
                    flag_ns = eff.get("flag")
                    if flag_ns:
                        ns, _, key = str(flag_ns).partition(".")
                        bundle.ctx.set_global_flag(ns, key, eff.get("value", True))
                        applied.append(f"标记 {flag_ns}")

                bundle.ctx.remove_item(item_id, 1)
                bundle.api._push_status()
                output.send({"type": "use.result",
                             "payload": {"ok": True, "item": item_id,
                                         "name": it.name,
                                         "changes": "，".join(applied) if applied else "无特别效果"}})
                _send_characters(bundle, output)
        elif mtype == "game.buy":
            catalog = getattr(bundle, "catalog", None)
            item_id = str(payload.get("item", ""))
            qty = max(1, int(payload.get("count", 1) or 1))
            if catalog is None or catalog.item(item_id) is None:
                output.send({"type": "buy.result",
                             "payload": {"ok": False, "reason": "没有这种商品"}})
            else:
                it = catalog.item(item_id)
                total = it.price * qty
                if bundle.ctx.get_player_stat("money", 0) < total:
                    output.send({"type": "buy.result",
                                 "payload": {"ok": False, "item": item_id,
                                             "reason": f"钱不够（需要 {total}）"}})
                else:
                    bundle.ctx.modify_player_stat("money", -total)
                    bundle.ctx.add_item(item_id, qty)
                    bundle.api._push_status()
                    output.send({"type": "buy.result",
                                 "payload": {"ok": True, "item": item_id, "count": qty,
                                             "cost": total,
                                             "money": bundle.ctx.get_player_stat("money", 0)}})
                    _send_characters(bundle, output)
        elif mtype == "game.gift":
            catalog = getattr(bundle, "catalog", None)
            char_id = str(payload.get("char", ""))
            item_id = str(payload.get("item", ""))
            if bundle.ctx.get_character(char_id) is None:
                output.send({"type": "gift.result",
                             "payload": {"ok": False, "reason": "没有这个角色"}})
            elif bundle.ctx.get_item_count(item_id) < 1:
                output.send({"type": "gift.result",
                             "payload": {"ok": False, "reason": "背包里没有这件东西"}})
            else:
                gain = catalog.gift_value(item_id) if catalog else 0
                item_name = catalog.item_name(item_id) if catalog else item_id
                # 对方喜欢的物品 → 好感加成 50%
                ch_state = bundle.ctx.get_character(char_id)
                liked = bool(ch_state and item_id in ch_state.favorite_items)
                if liked:
                    gain = int(round(gain * 1.5))
                bundle.ctx.remove_item(item_id, 1)
                new_rel = bundle.ctx.modify_character_relation(char_id, gain)
                bundle.ctx.add_character_history(char_id, {
                    "day": bundle.ctx.get_day(),
                    "title": f"收到{item_name}",
                    "changes": f"好感度{gain:+d}",
                })
                bundle.api._push_status()
                output.send({"type": "gift.result",
                             "payload": {"ok": True, "char": char_id, "item": item_id,
                                         "gain": gain, "relation": new_rel,
                                         "liked": liked}})
                _send_characters(bundle, output)
                _send_hub(bundle, output)
        elif mtype == "game.characters":
            # 前端打开角色一览/详情时拉取
            _send_characters(bundle, output)
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
