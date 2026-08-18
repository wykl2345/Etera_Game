"""事件总线 —— 引擎模块间解耦的核心机制。

v2 版保留 v1 的同步 emit 语义（脚本在线程中同步执行），去除 PySide6/Qt 依赖。
事件分两类：
  - 系统事件：引擎自动触发（on_game_start、on_day_begin ...）
  - 游戏事件：Lua 脚本通过 event.emit 主动触发（custom:*）
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

# ── 事件优先级 ────────────────────────────────────────────────────────────────
class EventPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


# ── 事件上下文 ────────────────────────────────────────────────────────────────
@dataclass
class EventContext:
    """一次事件发射的上下文，随事件传给所有订阅者。"""

    event_name: str
    source: Optional[str] = None
    timestamp: float = field(default_factory=lambda: time.monotonic())
    data: Dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL
    _stopped: bool = False

    def stop_propagation(self) -> None:
        self._stopped = True

    @property
    def is_stopped(self) -> bool:
        return self._stopped


@dataclass
class EventSubscription:
    callback: Callable
    priority: EventPriority = EventPriority.NORMAL
    once: bool = False
    filter_fn: Optional[Callable[[EventContext], bool]] = None


# ── 系统事件常量 ──────────────────────────────────────────────────────────────
_SYSTEM_EVENTS: List[str] = [
    "on_game_start", "on_game_end",
    "on_day_begin", "on_day_end",
    "on_save", "on_load",
    "on_scene_change",
    "on_character_stat_changed", "on_inventory_changed",
    "on_dialogue_start", "on_dialogue_end", "on_choice_made",
    "on_battle_start", "on_battle_end",
    "on_error",
]

# 额外的预注册事件（v1 EventConstants，不含 _SYSTEM_EVENTS 已覆盖项）
_EXTRA_EVENTS: List[str] = [
    "on_game_pause", "on_game_resume",
    "on_time_change", "on_location_change",
    "on_quick_save", "on_quick_load", "on_scene_loaded",
    "on_character_relation_changed", "on_character_added", "on_character_removed",
    "on_item_added", "on_item_removed",
    "on_dialogue_line", "on_choice_displayed",
    "on_battle_turn", "on_script_error",
    "on_ui_update", "on_ui_refresh",
]

# UI 点分事件（引擎 → 前端，经 WS 网关转发，命名统一）
UI_EVENTS = {
    "text": "ui.text",
    "clear": "ui.clear",
    "image_show": "ui.image_show",
    "image_hide": "ui.image_hide",
    "sound_play": "audio.sound_play",
    "sound_stop": "audio.sound_stop",
    "music_play": "audio.music_play",
    "music_stop": "audio.music_stop",
    "choice_show": "ui.choice_show",
    "choice_made": "ui.choice_made",
    "input_show": "ui.input_show",
    "input_received": "ui.input_received",
    "background_set": "ui.background_set",
    "character_show": "ui.character_show",
    "character_hide": "ui.character_hide",
}

SCRIPT_EVENTS = {
    "completed": "script.completed",
    "aborted": "script.aborted",
    "error": "script.error",
}


class EventBus:
    """发布-订阅事件总线（线程安全，脚本线程/主循环均可 emit）。

    v2 语义：回调同步执行；async 回调会通过 run_coroutine_threadsafe 提交到
    创建时绑定的事件循环（兼容 asyncio 化后的主循环调用）。
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventSubscription]] = {}
        self._global_filters: List[Callable[[EventContext], bool]] = []
        self._history: List[EventContext] = []
        self._history_limit = 100
        self._lock = threading.RLock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # 预注册系统事件（空订阅列表，保证安全 emit）
        for name in _SYSTEM_EVENTS + _EXTRA_EVENTS:
            self._subscribers.setdefault(name, [])

    # ── 事件循环绑定（供异步回调调度）──────────────────────────
    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ── 订阅 ──────────────────────────────────────────────────
    def subscribe(
        self,
        event_name: str,
        callback: Callable,
        priority: EventPriority = EventPriority.NORMAL,
        once: bool = False,
        filter_fn: Optional[Callable[[EventContext], bool]] = None,
    ) -> EventSubscription:
        sub = EventSubscription(
            callback=callback, priority=priority, once=once, filter_fn=filter_fn
        )
        with self._lock:
            subs = self._subscribers.setdefault(event_name, [])
            subs.append(sub)
            # 按优先级降序排序（同优先级保持注册顺序）
            subs.sort(key=lambda s: s.priority.value, reverse=True)
        return sub

    def unsubscribe(self, event_name: str, callback: Callable) -> bool:
        with self._lock:
            subs = self._subscribers.get(event_name, [])
            for i, sub in enumerate(subs):
                if sub.callback is callback:
                    del subs[i]
                    return True
        return False

    def unsubscribe_all(self, event_name: str) -> int:
        with self._lock:
            subs = self._subscribers.pop(event_name, [])
            self._subscribers.setdefault(event_name, [])
        return len(subs)

    # ── 全局过滤器 ─────────────────────────────────────────────
    def add_global_filter(self, filter_fn: Callable[[EventContext], bool]) -> None:
        with self._lock:
            self._global_filters.append(filter_fn)

    def remove_global_filter(self, filter_fn: Callable[[EventContext], bool]) -> bool:
        with self._lock:
            try:
                self._global_filters.remove(filter_fn)
                return True
            except ValueError:
                return False

    # ── 发射 ──────────────────────────────────────────────────
    def emit(self, event_name: str, **kwargs: Any) -> EventContext:
        ctx = EventContext(event_name=event_name, data=kwargs)
        with self._lock:
            filters = list(self._global_filters)
            subs = list(self._subscribers.get(event_name, []))
        # 全局过滤器：任一返回 False 则阻止整个事件
        for f in filters:
            if not f(ctx):
                return ctx
        for sub in subs:
            if ctx.is_stopped:
                break
            if sub.filter_fn is not None and not sub.filter_fn(ctx):
                continue
            result = self._invoke(sub.callback, ctx)
            if sub.once and result is not False:
                with self._lock:
                    subs_list = self._subscribers.get(event_name, [])
                    if sub in subs_list:
                        subs_list.remove(sub)
        self._record(ctx)
        return ctx

    # ── 回调调用（支持 sync + async 混合）──────────────────────
    def _invoke(self, callback: Callable, ctx: EventContext) -> Any:
        try:
            result = callback(ctx)
        except TypeError:
            # 兼容 v1 无参回调（某些 Lua 包装回调不带 ctx）
            try:
                result = callback()
            except TypeError:
                raise
        if asyncio.iscoroutine(result):
            loop = self._loop
            if loop is None or loop.is_closed():
                # 无绑定循环时在当前线程跑（测试场景）
                import asyncio as _a

                try:
                    _a.get_running_loop()
                except RuntimeError:
                    return _a.run(result)
                return None
            fut = asyncio.run_coroutine_threadsafe(result, loop)
            return fut
        return result

    # ── 历史 ──────────────────────────────────────────────────
    def get_event_history(self, event_name: Optional[str] = None, limit: int = 10) -> List[EventContext]:
        with self._lock:
            items = self._history
            if event_name is not None:
                items = [c for c in items if c.event_name == event_name]
            return list(items[-limit:])

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    def _record(self, ctx: EventContext) -> None:
        with self._lock:
            self._history.append(ctx)
            if len(self._history) > self._history_limit:
                del self._history[: len(self._history) - self._history_limit]

    # ── 查询 ──────────────────────────────────────────────────
    def get_subscribers(self, event_name: str) -> List[EventSubscription]:
        with self._lock:
            return list(self._subscribers.get(event_name, []))


# 模块级单例
_instance: Optional[EventBus] = None
_instance_lock = threading.Lock()


def get_event_bus() -> EventBus:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = EventBus()
        return _instance
