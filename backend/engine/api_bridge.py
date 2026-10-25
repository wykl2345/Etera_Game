"""API 白名单（API Bridge）—— Lua 沙箱中唯一可调用的受限指令集。

指令集共 **41 个** API（13 ui + 13 data + 3 event + 5 util + 6 world + 1 minigame）。
阻塞指令（ask_choice/ask_input）经 scheduler 挂起/恢复（asyncio Future，见 script_runner）。
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 文本颜色白名单（非法颜色忽略）
TEXT_COLORS = {
    "white", "red", "green", "blue", "yellow",
    "pink", "gray", "cyan", "orange", "purple",
}


def _to_list(value: Any) -> List[Any]:
    """LuaTable / list / tuple → list。lupa LuaTable 迭代产出键，须用 values()。"""
    if isinstance(value, (list, tuple)):
        return list(value)
    values = getattr(value, "values", None)
    if callable(values):
        return list(values())
    try:
        return list(value)
    except TypeError:
        return [value]


def _to_dict(value: Any) -> Dict[str, Any]:
    """LuaTable / dict → dict。lupa LuaTable 键值经 keys()/values() 取。"""
    if isinstance(value, dict):
        return dict(value)
    keys = getattr(value, "keys", None)
    values = getattr(value, "values", None)
    if callable(keys) and callable(values):
        return {str(k): v for k, v in zip(list(keys()), list(values()))}
    return {}


class LuaAPI:
    """构建注入 Lua 全局的五组 API 表：{ui, data, event, util, world}。"""

    def __init__(
        self,
        scheduler: Any,
        context: Any,
        event_bus: Any,
        resource_manager: Any = None,
        debug_mode: bool = False,
    ) -> None:
        self._scheduler = scheduler
        self._ctx = context
        self._bus = event_bus
        self._rm = resource_manager
        self._debug_mode = debug_mode

    # ── 组装 ──────────────────────────────────────────────────
    def build_env(self) -> Dict[str, Dict[str, Callable]]:
        return {
            "ui": {
                "text": self._ui_text,
                "clear": self._ui_clear,
                "show_image": self._ui_show_image,
                "hide_image": self._ui_hide_image,
                "play_sound": self._ui_play_sound,
                "stop_sound": self._ui_stop_sound,
                "play_music": self._ui_play_music,
                "stop_music": self._ui_stop_music,
                "set_background": self._ui_set_background,
                "show_character": self._ui_show_character,
                "hide_character": self._ui_hide_character,
                "ask_choice": self._ui_ask_choice,
                "ask_input": self._ui_ask_input,
            },
            "data": {
                "get_chara": self._data_get_chara,
                "set_stat": self._data_set_stat,
                "get_stat": self._data_get_stat,
                "get_relation": self._data_get_relation,
                "set_relation": self._data_set_relation,
                "modify_relation": self._data_modify_relation,
                "get_flag": self._data_get_flag,
                "set_flag": self._data_set_flag,
                "has_flag": self._data_has_flag,
                "get_inventory": self._data_get_inventory,
                "add_item": self._data_add_item,
                "remove_item": self._data_remove_item,
                "get_item_count": self._data_get_item_count,
            },
            "event": {
                "emit": self._event_emit,
                "after_days": self._event_after_days,
                "listen": self._event_listen,
            },
            "minigame": {
                "start": self._minigame_start,
            },
            "util": {
                "random": self._util_random,
                "random_range": self._util_random_range,
                "log": self._util_log,
                "debug": self._util_debug,
                "sleep": self._util_sleep,
            },
            "world": {
                "get_day": self._world_get_day,
                "set_day": self._world_set_day,
                "get_time": self._world_get_time,
                "set_time": self._world_set_time,
                "get_location": self._world_get_location,
                "set_location": self._world_set_location,
            },
        }

    # ── 状态推送（写操作后调用，前端 StatusBar 订阅）────────────
    def _push_status(self) -> None:
        try:
            stats = self._ctx.get_player("stats")
            status = {
                "day": self._ctx.get_day(),
                "time_of_day": self._ctx.get_time_of_day().value,
                "location": self._ctx.get_location(),
                "player": {
                    "hp": stats.hp, "max_hp": stats.max_hp,
                    "mp": stats.mp, "max_mp": stats.max_mp,
                    "stamina": stats.stamina, "max_stamina": stats.max_stamina,
                    "money": stats.money, "level": stats.level,
                },
                "characters": {
                    cid: {"name": ch.name, "relation": ch.relation}
                    for cid, ch in self._ctx.get_all_characters().items()
                },
            }
            self._scheduler.output.send({"type": "status.sync", "payload": status})
        except Exception:  # noqa: BLE001 - 状态推送失败不影响游戏逻辑
            logger.debug("status.sync 推送失败", exc_info=True)

    # ══════════════════ ui.（13）══════════════════════
    def _ui_text(self, text: str, color: Optional[str] = None, bold: bool = False) -> None:
        if color is not None and color not in TEXT_COLORS:
            color = None
        self._scheduler.output.send(
            {"type": "ui.text", "payload": {"text": str(text), "color": color, "bold": bool(bold)}}
        )

    def _ui_clear(self) -> None:
        self._scheduler.output.send({"type": "ui.clear", "payload": {}})

    def _ui_show_image(self, name: str, position: str = "center", fade: bool = True) -> None:
        self._scheduler.output.send(
            {"type": "ui.image_show", "payload": {"name": str(name), "position": position, "fade": bool(fade)}}
        )

    def _ui_hide_image(self, name: str, fade: bool = True) -> None:
        self._scheduler.output.send(
            {"type": "ui.image_hide", "payload": {"name": str(name), "fade": bool(fade)}}
        )

    def _ui_play_sound(self, name: str, volume: float = 1.0) -> None:
        volume = max(0.0, min(1.0, float(volume)))
        self._scheduler.output.send(
            {"type": "audio.sound_play", "payload": {"name": str(name), "volume": volume}}
        )

    def _ui_stop_sound(self, name: str) -> None:
        self._scheduler.output.send(
            {"type": "audio.sound_stop", "payload": {"name": str(name)}}
        )

    def _ui_play_music(self, name: str, volume: float = 0.8, loop: bool = True) -> None:
        volume = max(0.0, min(1.0, float(volume)))
        self._scheduler.output.send(
            {"type": "audio.music_play", "payload": {"name": str(name), "volume": volume, "loop": bool(loop)}}
        )

    def _ui_stop_music(self, fade_out: bool = True) -> None:
        self._scheduler.output.send(
            {"type": "audio.music_stop", "payload": {"fade_out": bool(fade_out)}}
        )

    def _ui_set_background(self, name: str, transition: str = "fade") -> None:
        self._scheduler.output.send(
            {"type": "ui.background_set", "payload": {"name": str(name), "transition": transition}}
        )

    def _ui_show_character(self, char_id: str, expression: str = "normal", position: str = "center") -> None:
        self._scheduler.output.send(
            {"type": "ui.character_show",
             "payload": {"char_id": str(char_id), "expression": expression, "position": position}}
        )

    def _ui_hide_character(self, char_id: str) -> None:
        self._scheduler.output.send(
            {"type": "ui.character_hide", "payload": {"char_id": str(char_id)}}
        )

    def _ui_ask_choice(self, options: Any) -> int:
        opts = [str(o) for o in _to_list(options)]
        if not opts:
            return 0
        return self._scheduler.ask_choice(opts)

    def _ui_ask_input(self, prompt: str, default: str = "", max_length: int = 100) -> str:
        return self._scheduler.ask_input(str(prompt), str(default), int(max_length))

    # ══════════════════ data.（13）══════════════════════
    def _data_get_chara(self, char_id: str) -> Optional[Dict[str, Any]]:
        ch = self._ctx.get_character(str(char_id))
        if ch is None:
            return None
        return {
            "id": ch.id, "name": ch.name,
            "stats": ch.stats.to_dict(),
            "relation": ch.relation, "location": ch.location,
        }

    def _data_set_stat(self, target: str, stat_name: str, value: Any) -> bool:
        target, stat_name, value = str(target), str(stat_name), int(value)
        if target == "player":
            if stat_name == "relation":
                return False
            self._ctx.set_player_stat(stat_name, value)
        else:
            if not self._ctx.has_character(target):
                return False
            if stat_name == "relation":
                self._ctx.set_character_relation(target, value)
            else:
                self._ctx.set_character_stat(target, stat_name, value)
        self._bus.emit("on_character_stat_changed", target=target, stat=stat_name, value=value)
        self._push_status()
        return True

    def _data_get_stat(self, target: str, stat_name: str, default: int = 0) -> int:
        target, stat_name = str(target), str(stat_name)
        if target == "player":
            return self._ctx.get_player_stat(stat_name, default)
        return self._ctx.get_character_stat(target, stat_name, default)

    def _data_get_relation(self, target: str) -> int:
        target = str(target)
        if target == "player":
            return 0
        return self._ctx.get_character_relation(target)

    def _data_set_relation(self, target: str, value: int) -> bool:
        target = str(target)
        if target == "player" or not self._ctx.has_character(target):
            return False
        self._ctx.set_character_relation(target, int(value))
        self._bus.emit("on_character_relation_changed", target=target, value=int(value))
        self._push_status()
        return True

    def _data_modify_relation(self, target: str, delta: int) -> int:
        target = str(target)
        if target == "player":
            return 0
        new_value = self._ctx.modify_character_relation(target, int(delta))
        self._bus.emit("on_character_relation_changed", target=target, value=new_value)
        self._push_status()
        return new_value

    def _data_get_flag(self, namespace: str, key: str, default: Any = None) -> Any:
        namespace, key = str(namespace), str(key)
        if namespace.startswith("char:"):
            return self._ctx.get_character_flag(namespace[5:], key, default)
        return self._ctx.get_global_flag(namespace, key, default)

    def _data_set_flag(self, namespace: str, key: str, value: Any) -> bool:
        namespace, key = str(namespace), str(key)
        # 第二层保护：core 命名空间拒绝（第一层在 GameContext）
        if namespace == "core":
            return False
        if namespace.startswith("char:"):
            self._ctx.set_character_flag(namespace[5:], key, value)
        else:
            self._ctx.set_global_flag(namespace, key, value)
        return True

    def _data_has_flag(self, namespace: str, key: str) -> bool:
        namespace, key = str(namespace), str(key)
        if namespace.startswith("char:"):
            ch = self._ctx.get_character(namespace[5:])
            return ch is not None and bool(self._ctx.get_character_flag(namespace[5:], key))
        return self._ctx.has_global_flag(namespace, key)

    def _data_get_inventory(self) -> Dict[str, int]:
        return self._ctx.get_inventory().to_dict()

    def _data_add_item(self, item_id: str, count: int = 1) -> bool:
        ok = self._ctx.add_item(str(item_id), int(count))
        if ok:
            self._push_status()
        return ok

    def _data_remove_item(self, item_id: str, count: int = 1) -> bool:
        ok = self._ctx.remove_item(str(item_id), int(count))
        if ok:
            self._push_status()
        return ok

    def _data_get_item_count(self, item_id: str) -> int:
        return self._ctx.get_item_count(str(item_id))

    # ══════════════════ event.（3）══════════════════════
    def _event_emit(self, event_name: str, payload: Optional[Dict[str, Any]] = None) -> None:
        kwargs = _to_dict(payload) if payload is not None else {}
        self._bus.emit(str(event_name), **kwargs)

    def _event_after_days(self, days: int, callback: Callable) -> None:
        """惰性实现：存 temp，触发逻辑 Phase 3（对齐 v1 占位）。"""
        key = f"delayed_event_{time.monotonic_ns()}"
        self._ctx.set_temp(key, {"callback": callback, "trigger_day": self._ctx.get_day() + int(days)})

    def _event_listen(self, event_name: str, handler: Callable) -> None:
        self._bus.subscribe(str(event_name), handler)

    # ══════════════════ minigame.（1）══════════════════════
    def _minigame_start(self, game_id: str, options: Any = None) -> Dict[str, Any]:
        """触发小游戏（阻塞）：脚本挂起，等前端回传结果后恢复。

        返回 Lua table：{ won, score, ... }（由小游戏实现决定）。
        """
        opts = _to_dict(options)
        return self._scheduler.ask_minigame(str(game_id), opts)

    # ══════════════════ util.（5）══════════════════════
    def _util_random(self) -> float:
        return random.random()

    def _util_random_range(self, min_val: int, max_val: int) -> int:
        lo, hi = int(min_val), int(max_val)
        if lo > hi:
            lo, hi = hi, lo
        return random.randint(lo, hi)

    def _util_log(self, message: str) -> None:
        logger.info("[Lua] %s", message)

    def _util_debug(self, message: str) -> None:
        if self._debug_mode:
            logger.info("[Lua-debug] %s", message)

    def _util_sleep(self, seconds: float) -> None:
        # 脚本运行在独立线程，time.sleep 不阻塞 asyncio 主循环（等效 v1 非阻塞语义）
        time.sleep(max(0.0, float(seconds)))

    # ══════════════════ world.（6）══════════════════════
    def _world_get_day(self) -> int:
        return self._ctx.get_day()

    def _world_set_day(self, day: int) -> None:
        if int(day) >= 1:
            self._ctx.set_day(int(day))
            self._push_status()

    def _world_get_time(self) -> str:
        return self._ctx.get_time_of_day().value

    def _world_set_time(self, time_str: str) -> None:
        self._ctx.set_time_of_day(str(time_str))
        self._push_status()

    def _world_get_location(self) -> str:
        return self._ctx.get_location()

    def _world_set_location(self, location: str) -> None:
        self._ctx.set_location(str(location))
        self._push_status()
