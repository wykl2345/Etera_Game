"""分层命名空间状态管理 —— 游戏运行时状态的唯一事实来源（ADR-0003）。

结构：world / player / characters / global_flags / character_flags / temp(不存档)
core 命名空间受保护：引擎保留区，Lua 脚本不可写入。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TimeOfDay(Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"
    DAWN = "dawn"


class ContextScope(Enum):
    WORLD = "world"
    PLAYER = "player"
    CHARACTER = "character"
    GLOBAL = "global"
    TEMP = "temp"


# ── 属性块 ────────────────────────────────────────────────────────────────────
@dataclass
class StatBlock:
    hp: int = 100
    max_hp: int = 100
    mp: int = 50
    max_mp: int = 50
    stamina: int = 100
    max_stamina: int = 100
    money: int = 0
    exp: int = 0
    level: int = 1

    def to_dict(self) -> Dict[str, int]:
        return {
            "hp": self.hp, "max_hp": self.max_hp,
            "mp": self.mp, "max_mp": self.max_mp,
            "stamina": self.stamina, "max_stamina": self.max_stamina,
            "money": self.money, "exp": self.exp, "level": self.level,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StatBlock":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def clamp_stats(self) -> None:
        self.hp = max(0, min(self.hp, self.max_hp))
        self.mp = max(0, min(self.mp, self.max_mp))
        self.stamina = max(0, min(self.stamina, self.max_stamina))

    def get(self, key: str, default: int = 0) -> int:
        return getattr(self, key, default)

    def set(self, key: str, value: int) -> None:
        if hasattr(self, key):
            setattr(self, key, value)
            self.clamp_stats()


@dataclass
class Inventory:
    items: Dict[str, int] = field(default_factory=dict)
    max_size: int = 100

    def add_item(self, item_id: str, count: int = 1) -> bool:
        if count <= 0:
            return False
        if len(self.items) >= self.max_size and item_id not in self.items:
            return False
        self.items[item_id] = self.items.get(item_id, 0) + count
        return True

    def remove_item(self, item_id: str, count: int = 1) -> bool:
        if item_id not in self.items or count <= 0:
            return False
        remaining = self.items[item_id] - count
        if remaining <= 0:
            del self.items[item_id]
        else:
            self.items[item_id] = remaining
        return True

    def get_count(self, item_id: str) -> int:
        return self.items.get(item_id, 0)

    def to_dict(self) -> Dict[str, int]:
        return dict(self.items)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Inventory":
        return cls(items={k: int(v) for k, v in data.items()})


# ── Flag 命名空间 ─────────────────────────────────────────────────────────────
class FlagStore:
    """带命名空间的开关/值存储，Mod 之间变量隔离的关键。"""

    def __init__(self, namespace: str = "default") -> None:
        self.namespace = namespace
        self._flags: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._flags[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._flags.get(key, default)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._flags:
                del self._flags[key]
                return True
            return False

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._flags

    def clear(self) -> None:
        with self._lock:
            self._flags.clear()

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._flags.keys())

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._flags)

    @classmethod
    def from_dict(cls, namespace: str, data: Dict[str, Any]) -> "FlagStore":
        store = cls(namespace)
        store._flags = dict(data)
        return store


# ── 角色状态 ──────────────────────────────────────────────────────────────────
@dataclass
class CharacterState:
    id: str
    name: str
    # 展示用元数据（来自角色 YAML，不进剧情逻辑）
    title: str = ""
    tags: List[str] = field(default_factory=list)
    stats: StatBlock = field(default_factory=StatBlock)
    flags: FlagStore = field(default_factory=lambda: FlagStore("character"))
    relation: int = 0
    location: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name,
            "title": self.title, "tags": list(self.tags),
            "stats": self.stats.to_dict(),
            "flags": self.flags.to_dict(),
            "relation": self.relation, "location": self.location,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterState":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            # 老存档没有这两个字段 → 空值，向后兼容
            title=data.get("title", ""),
            tags=list(data.get("tags", [])),
            stats=StatBlock.from_dict(data.get("stats", {})),
            flags=FlagStore.from_dict("character", data.get("flags", {})),
            relation=int(data.get("relation", 0)),
            location=data.get("location", ""),
        )


# ── 游戏上下文 ────────────────────────────────────────────────────────────────
class GameContext:
    """分层命名空间状态容器。所有修改方法线程安全（脚本线程/主循环可并发）。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._world: Dict[str, Any] = {
                "day": 1,
                "time_of_day": TimeOfDay.MORNING.value,
                "location": "home",
                "season": "spring",
                "weather": "clear",
            }
            self._player: Dict[str, Any] = {
                "stats": StatBlock(),
                "inventory": Inventory(),
                "name": "",
                "gender": "unknown",
            }
            self._characters: Dict[str, CharacterState] = {}
            self._global_flags: Dict[str, FlagStore] = {"core": FlagStore("core")}
            self._character_flags: Dict[str, FlagStore] = {}
            self._temp: Dict[str, Any] = {}

    # ── 世界 ──────────────────────────────────────────────────
    def get_world(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._world.get(key, default)

    def set_world(self, key: str, value: Any) -> None:
        with self._lock:
            self._world[key] = value

    def get_day(self) -> int:
        return int(self.get_world("day", 1))

    def set_day(self, day: int) -> None:
        self.set_world("day", int(day))

    def get_time_of_day(self) -> TimeOfDay:
        try:
            return TimeOfDay(self.get_world("time_of_day"))
        except ValueError:
            return TimeOfDay.MORNING

    def set_time_of_day(self, value: Any) -> None:
        if isinstance(value, TimeOfDay):
            value = value.value
        self.set_world("time_of_day", str(value))

    def get_location(self) -> str:
        return str(self.get_world("location", ""))

    def set_location(self, location: str) -> None:
        self.set_world("location", location)

    # ── 玩家 ──────────────────────────────────────────────────
    def get_player(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._player.get(key, default)

    def set_player(self, key: str, value: Any) -> None:
        with self._lock:
            self._player[key] = value

    def get_player_stat(self, stat_name: str, default: int = 0) -> int:
        with self._lock:
            return self._player["stats"].get(stat_name, default)

    def set_player_stat(self, stat_name: str, value: int) -> None:
        with self._lock:
            self._player["stats"].set(stat_name, int(value))

    def modify_player_stat(self, stat_name: str, delta: int) -> int:
        with self._lock:
            stats = self._player["stats"]
            current = stats.get(stat_name)
            stats.set(stat_name, current + int(delta))
            return stats.get(stat_name)

    def get_inventory(self) -> Inventory:
        with self._lock:
            return self._player["inventory"]

    def add_item(self, item_id: str, count: int = 1) -> bool:
        return self.get_inventory().add_item(item_id, count)

    def remove_item(self, item_id: str, count: int = 1) -> bool:
        return self.get_inventory().remove_item(item_id, count)

    def get_item_count(self, item_id: str) -> int:
        return self.get_inventory().get_count(item_id)

    # ── 角色 ──────────────────────────────────────────────────
    def add_character(self, char_id: str, name: str) -> CharacterState:
        with self._lock:
            state = CharacterState(id=char_id, name=name)
            self._characters[char_id] = state
            return state

    def remove_character(self, char_id: str) -> bool:
        with self._lock:
            if char_id in self._characters:
                del self._characters[char_id]
                return True
            return False

    def get_character(self, char_id: str) -> Optional[CharacterState]:
        with self._lock:
            return self._characters.get(char_id)

    def get_all_characters(self) -> Dict[str, CharacterState]:
        with self._lock:
            return dict(self._characters)

    def has_character(self, char_id: str) -> bool:
        with self._lock:
            return char_id in self._characters

    def get_character_stat(self, char_id: str, stat_name: str, default: int = 0) -> int:
        with self._lock:
            ch = self._characters.get(char_id)
            if ch is None:
                return default
            return ch.stats.get(stat_name, default)

    def set_character_stat(self, char_id: str, stat_name: str, value: int) -> None:
        with self._lock:
            ch = self._characters.get(char_id)
            if ch is not None:
                ch.stats.set(stat_name, int(value))

    def modify_character_stat(self, char_id: str, stat_name: str, delta: int) -> int:
        with self._lock:
            ch = self._characters.get(char_id)
            if ch is None:
                return 0
            ch.stats.set(stat_name, ch.stats.get(stat_name) + int(delta))
            return ch.stats.get(stat_name)

    def get_character_relation(self, char_id: str) -> int:
        with self._lock:
            ch = self._characters.get(char_id)
            return ch.relation if ch else 0

    def set_character_relation(self, char_id: str, value: int) -> None:
        with self._lock:
            ch = self._characters.get(char_id)
            if ch is not None:
                ch.relation = max(-100, min(100, int(value)))

    def modify_character_relation(self, char_id: str, delta: int) -> int:
        with self._lock:
            ch = self._characters.get(char_id)
            if ch is None:
                return 0
            ch.relation = max(-100, min(100, ch.relation + int(delta)))
            return ch.relation

    def get_character_flag(self, char_id: str, key: str, default: Any = None) -> Any:
        with self._lock:
            store = self._character_flags.get(char_id)
            return store.get(key, default) if store else default

    def set_character_flag(self, char_id: str, key: str, value: Any) -> None:
        with self._lock:
            store = self._character_flags.setdefault(char_id, FlagStore(f"char:{char_id}"))
            store.set(key, value)

    def get_character_location(self, char_id: str) -> str:
        with self._lock:
            ch = self._characters.get(char_id)
            return ch.location if ch else ""

    def set_character_location(self, char_id: str, location: str) -> None:
        with self._lock:
            ch = self._characters.get(char_id)
            if ch is not None:
                ch.location = location

    # ── 全局 Flag（命名空间隔离）──────────────────────────────
    def get_global_flag_namespace(self, namespace: str) -> FlagStore:
        with self._lock:
            store = self._global_flags.get(namespace)
            if store is None:
                store = FlagStore(namespace)
                self._global_flags[namespace] = store
            return store

    def get_global_flag(self, namespace: str, key: str, default: Any = None) -> Any:
        with self._lock:
            store = self._global_flags.get(namespace)
            return store.get(key, default) if store else default

    def set_global_flag(self, namespace: str, key: str, value: Any) -> None:
        # 第一层保护：core 命名空间拒绝写入
        if namespace == "core":
            return
        with self._lock:
            store = self._global_flags.setdefault(namespace, FlagStore(namespace))
            store.set(key, value)

    def delete_global_flag(self, namespace: str, key: str) -> bool:
        if namespace == "core":
            return False
        with self._lock:
            store = self._global_flags.get(namespace)
            return store.delete(key) if store else False

    def has_global_flag(self, namespace: str, key: str) -> bool:
        with self._lock:
            store = self._global_flags.get(namespace)
            return store.has(key) if store else False

    # ── 临时（不存档）─────────────────────────────────────────
    def get_temp(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._temp.get(key, default)

    def set_temp(self, key: str, value: Any) -> None:
        with self._lock:
            self._temp[key] = value

    def clear_temp(self) -> None:
        with self._lock:
            self._temp.clear()

    # ── 序列化 ────────────────────────────────────────────────
    def serialize(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "world": dict(self._world),
                "player": {
                    "stats": self._player["stats"].to_dict(),
                    "inventory": self._player["inventory"].to_dict(),
                    "name": self._player.get("name", ""),
                    "gender": self._player.get("gender", "unknown"),
                },
                "characters": {
                    cid: ch.to_dict() for cid, ch in self._characters.items()
                },
                "global_flags": {
                    ns: store.to_dict() for ns, store in self._global_flags.items()
                },
                "character_flags": {
                    cid: store.to_dict() for cid, store in self._character_flags.items()
                },
            }

    def deserialize(self, data: Dict[str, Any]) -> None:
        with self._lock:
            if not isinstance(data, dict):
                return
            world = data.get("world")
            if isinstance(world, dict):
                self._world.update(world)
            player = data.get("player")
            if isinstance(player, dict):
                if isinstance(player.get("stats"), dict):
                    self._player["stats"] = StatBlock.from_dict(player["stats"])
                if isinstance(player.get("inventory"), dict):
                    self._player["inventory"] = Inventory.from_dict(player["inventory"])
                if "name" in player:
                    self._player["name"] = player["name"]
                if "gender" in player:
                    self._player["gender"] = player["gender"]
            characters = data.get("characters")
            if isinstance(characters, dict):
                self._characters = {
                    cid: CharacterState.from_dict(ch) for cid, ch in characters.items()
                }
            flags = data.get("global_flags")
            if isinstance(flags, dict):
                self._global_flags = {
                    ns: FlagStore.from_dict(ns, d) for ns, d in flags.items()
                }
            cflags = data.get("character_flags")
            if isinstance(cflags, dict):
                self._character_flags = {
                    cid: FlagStore.from_dict(f"char:{cid}", d)
                    for cid, d in cflags.items()
                }
