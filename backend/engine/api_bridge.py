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


# 互动历史里显示的属性中文名
STAT_LABELS: Dict[str, str] = {
    "hp": "生命", "mp": "法力", "stamina": "体力",
    "money": "金钱", "exp": "经验", "level": "等级",
    "relation": "好感度",
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
        sandbox: Any = None,
    ) -> None:
        self._scheduler = scheduler
        self._ctx = context
        self._bus = event_bus
        self._rm = resource_manager
        self._debug_mode = debug_mode
        self._sandbox = sandbox
        # 互动历史记录上下文（data.log_start 开启，log_commit 提交）
        self._log_ctx: Optional[Dict[str, Any]] = None

    # ── Lua 值转换 ────────────────────────────────────────────
    def _lua_table(self, seq: Any) -> Any:
        """Python 序列 → 真 Lua table（1-based）。

        直接把 Python list 交给 Lua，得到的是 userdata：`#ids` 会报
        "attempt to get length of a POBJECT value"，下标还是 0-based。
        Mod 作者需要 `#` / `ipairs` / 1-based 下标，所以必须走 table_from。
        MockLuaRuntime 无 runtime 时降级返回 list。
        """
        items = list(seq)
        runtime = getattr(self._sandbox, "runtime", None)
        if runtime is not None and hasattr(runtime, "table_from"):
            try:
                return runtime.table_from(items)
            except Exception:  # noqa: BLE001 - 转换失败降级
                pass
        return items

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
                "modify_stat": self._data_modify_stat,
                "get_stat": self._data_get_stat,
                "get_relation": self._data_get_relation,
                "get_stage": self._data_get_stage,
                "set_stage": self._data_set_stage,
                "log_start": self._data_log_start,
                "log_commit": self._data_log_commit,
                "define_stat": self._data_define_stat,
                "get_extra": self._data_get_extra,
                "set_extra": self._data_set_extra,
                "modify_extra": self._data_modify_extra,
                "buy_item": self._data_buy_item,
                "sell_item": self._data_sell_item,
                "set_relation": self._data_set_relation,
                "modify_relation": self._data_modify_relation,
                "get_flag": self._data_get_flag,
                "set_flag": self._data_set_flag,
                "has_flag": self._data_has_flag,
                "list_characters": self._data_list_characters,
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

    def _data_list_characters(self) -> Any:
        """返回全部已加载角色的 ID 列表（Lua table，1-based）。

        用于"随机挑一个角色"这类通用逻辑，避免剧本里把角色 ID 写死。
        """
        return self._lua_table(self._ctx.get_all_characters().keys())

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

    def _data_modify_stat(self, target: str, stat_name: str, delta: Any) -> int:
        """按增量修改属性，返回新值（与 modify_relation 对称）。

        剧本里"扣 30 元""加 10 点经验"必须用它 —— set_stat 是设绝对值，
        拿它当增量会把原本数值覆盖掉（例如把钱设成 -30 而不是扣 30）。
        """
        target, stat_name, delta = str(target), str(stat_name), int(delta)
        if target == "player":
            if stat_name == "relation":
                return 0  # 玩家没有好感度
            new_value = self._ctx.modify_player_stat(stat_name, delta)
        else:
            if not self._ctx.has_character(target):
                return 0
            if stat_name == "relation":
                # 转发到 modify_relation（其内部已 emit + push，直接返回）
                return self._data_modify_relation(target, delta)
            new_value = self._ctx.modify_character_stat(target, stat_name, delta)
        self._log_add_stat(target, stat_name, delta)
        self._bus.emit("on_character_stat_changed", target=target, stat=stat_name, value=new_value)
        self._push_status()
        return new_value

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
        old_value = self._ctx.get_character_relation(target)
        new_value = self._ctx.modify_character_relation(target, int(delta))
        self._log_add_relation(target, new_value - old_value)
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

    # ── 关系阶段（突破由事件显式调用，不随好感度自动变化）────────
    def _data_get_stage(self, target: str) -> str:
        """取角色当前关系阶段 key；未设置过返回空串（展示层按好感度推算）。"""
        target = str(target)
        if target == "player":
            return ""
        return self._ctx.get_character_stage(target)

    def _data_set_stage(self, target: str, stage: str) -> bool:
        """设置关系阶段 —— 关系突破事件里调用。

        好感度满了只是数值满，阶段必须靠事件推进，所以这里不做数值校验。
        """
        target, stage = str(target), str(stage)
        if target == "player":
            return False
        ok = self._ctx.set_character_stage(target, stage)
        if ok:
            self._bus.emit("on_character_relation_changed", target=target, value=stage)
            self._push_status()
        return ok

    # ── 互动历史 ──────────────────────────────────────────────────
    def _data_log_start(self, target: str, title: str) -> bool:
        """开始记录一次互动：之后的 modify_* / 物品增减会自动累积。"""
        self._log_ctx = {
            "char": str(target),
            "title": str(title),
            "relation": 0,
            "stats": {},
            "items": {},
        }
        return True

    def _data_log_commit(self) -> bool:
        """提交记录 → 角色历史里多一条 [标题 -> 数值变化]。"""
        ctx = self._log_ctx
        self._log_ctx = None
        if not ctx:
            return False
        parts: List[str] = []
        if ctx["relation"]:
            parts.append(f"{STAT_LABELS['relation']}{ctx['relation']:+d}")
        for key, delta in ctx["stats"].items():
            if delta:
                parts.append(f"{STAT_LABELS.get(key, key)}{delta:+d}")
        for item_id, cnt in ctx["items"].items():
            if cnt > 0:
                parts.append(f"获得{item_id}×{cnt}")
            elif cnt < 0:
                parts.append(f"失去{item_id}×{-cnt}")
        changes = "，".join(parts) if parts else "无变化"
        self._ctx.add_character_history(ctx["char"], {
            "day": self._ctx.get_day(),
            "title": ctx["title"],
            "changes": changes,
        })
        return True

    def _log_add_relation(self, target: str, delta: int) -> None:
        ctx = self._log_ctx
        if ctx and ctx["char"] == target:
            ctx["relation"] += int(delta)

    def _log_add_stat(self, target: str, stat_name: str, delta: int) -> None:
        ctx = self._log_ctx
        if not ctx:
            return
        if ctx["char"] == target or target == "player":
            ctx["stats"][stat_name] = ctx["stats"].get(stat_name, 0) + int(delta)

    def _log_add_item(self, item_id: str, count: int) -> None:
        ctx = self._log_ctx
        if ctx:
            ctx["items"][item_id] = ctx["items"].get(item_id, 0) + int(count)

    # ── 自定义能力（剧本可注册，展示层按 extra_labels 显示中文名）──
    def _data_define_stat(self, target: str, key: str, label: str, initial: Any = 0) -> bool:
        target, key = str(target), str(key)
        if target == "player":
            return False
        return self._ctx.define_character_extra(target, key, str(label), initial)

    def _data_get_extra(self, target: str, key: str, default: Any = None) -> Any:
        target, key = str(target), str(key)
        if target == "player":
            return default
        return self._ctx.get_character_extra(target, key, default)

    def _data_set_extra(self, target: str, key: str, value: Any) -> bool:
        target, key = str(target), str(key)
        if target == "player":
            return False
        ok = self._ctx.set_character_extra(target, key, value)
        if ok:
            self._push_status()
        return ok

    def _data_modify_extra(self, target: str, key: str, delta: Any) -> Any:
        """按增量改自定义能力，返回新值（未注册时以 0 为基准）。"""
        if str(target) == "player":
            return 0
        current = self._ctx.get_character_extra(str(target), str(key), 0)
        try:
            new_value = int(current) + int(delta)
        except (TypeError, ValueError):
            return current
        self._ctx.set_character_extra(str(target), str(key), new_value)
        self._push_status()
        return new_value

    # ── 金币交易 ──────────────────────────────────────────────────
    def _data_buy_item(self, item_id: str, price: Any, count: int = 1) -> bool:
        """购买：金额 = price × count；钱不够返回 false（不扣款、不给货）。"""
        item_id = str(item_id)
        count = max(1, int(count))
        total = int(price) * count
        if self._ctx.get_player_stat("money", 0) < total:
            return False
        self._ctx.modify_player_stat("money", -total)
        self._ctx.add_item(item_id, count)
        self._log_add_stat("player", "money", -total)
        self._log_add_item(item_id, count)
        self._bus.emit("on_inventory_changed")
        self._push_status()
        return True

    def _data_sell_item(self, item_id: str, price: Any, count: int = 1) -> bool:
        """出售：持有不足返回 false（不移除、不加钱）。"""
        item_id = str(item_id)
        count = max(1, int(count))
        if self._ctx.get_item_count(item_id) < count:
            return False
        total = int(price) * count
        self._ctx.remove_item(item_id, count)
        self._ctx.modify_player_stat("money", total)
        self._log_add_stat("player", "money", total)
        self._log_add_item(item_id, -count)
        self._bus.emit("on_inventory_changed")
        self._push_status()
        return True

    def _data_get_inventory(self) -> Dict[str, int]:
        return self._ctx.get_inventory().to_dict()

    def _data_add_item(self, item_id: str, count: int = 1) -> bool:
        ok = self._ctx.add_item(str(item_id), int(count))
        if ok:
            self._log_add_item(str(item_id), int(count))
            self._push_status()
        return ok

    def _data_remove_item(self, item_id: str, count: int = 1) -> bool:
        ok = self._ctx.remove_item(str(item_id), int(count))
        if ok:
            self._log_add_item(str(item_id), -int(count))
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
