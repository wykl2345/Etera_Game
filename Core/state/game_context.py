"""
状态管理模块 (game_context.py)

本模块实现游戏状态的层次化管理，采用分层命名空间设计。
支持全局状态、玩家状态、角色状态等多层次的数据管理。

核心设计：
- 分层命名空间：世界级、玩家级、角色级、全局Flag级
- 角色专属Flag：每个角色拥有独立的Flag命名空间，防止Mod冲突
- 动态类型支持：支持各种数据类型，包括基本类型、字典、列表

数据结构设计：
GameContext
├── world                    # 世界级状态
│   ├── day: int
│   ├── time_of_day: enum
│   └── location: str
├── player                   # 玩家状态
│   ├── stats: StatBlock
│   └── inventory: Inventory
├── characters               # 所有角色状态
│   ├── "reimu"
│   │   ├── stats: StatBlock
│   │   ├── flags: FlagStore
│   │   └── relation: int
│   └── "marisa"
└── global_flags             # 全局剧情开关
    ├── namespace: "core"
    └── namespace: "mod_xxx"
"""

import copy
import threading
from typing import Any, Dict, Optional, List, Set, Union
from dataclasses import dataclass, field
from enum import Enum
import logging
import time


# 配置日志记录器
logger = logging.getLogger(__name__)


class TimeOfDay(Enum):
    """一天中的时段枚举"""
    MORNING = "morning"       # 早晨
    AFTERNOON = "afternoon"   # 下午
    EVENING = "evening"       # 傍晚
    NIGHT = "night"           # 夜晚
    DAWN = "dawn"             # 黎明


class ContextScope(Enum):
    """状态作用域枚举"""
    WORLD = "world"           # 世界级
    PLAYER = "player"         # 玩家级
    CHARACTER = "character"    # 角色级
    GLOBAL = "global"         # 全局Flag级
    TEMP = "temp"             # 临时状态（不存档）


@dataclass
class StatBlock:
    """
    属性数据块

    用于存储角色的各种属性值，支持默认值和边界检查。
    """
    hp: int = 100             # 生命值
    max_hp: int = 100         # 最大生命值
    mp: int = 50              # 魔法值
    max_mp: int = 50          # 最大魔法值
    stamina: int = 100        # 体力
    max_stamina: int = 100    # 最大体力
    money: int = 0            # 金钱
    exp: int = 0              # 经验值
    level: int = 1             # 等级

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "hp": self.hp,
            "max_hp": self.max_hp,
            "mp": self.mp,
            "max_mp": self.max_mp,
            "stamina": self.stamina,
            "max_stamina": self.max_stamina,
            "money": self.money,
            "exp": self.exp,
            "level": self.level,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StatBlock':
        """从字典创建"""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})

    def clamp_stats(self) -> None:
        """将属性值限制在有效范围内"""
        self.hp = max(0, min(self.hp, self.max_hp))
        self.mp = max(0, min(self.mp, self.max_mp))
        self.stamina = max(0, min(self.stamina, self.max_stamina))


@dataclass
class Inventory:
    """
    背包数据

    管理玩家的物品栏，支持物品数量、容量限制等功能。
    """
    items: Dict[str, int] = field(default_factory=dict)  # 物品ID -> 数量
    max_size: int = 100  # 最大容量

    def add_item(self, item_id: str, count: int = 1) -> bool:
        """
        添加物品

        Args:
            item_id: 物品ID
            count: 数量

        Returns:
            bool: 是否添加成功
        """
        if len(self.items) >= self.max_size and item_id not in self.items:
            return False

        self.items[item_id] = self.items.get(item_id, 0) + count
        return True

    def remove_item(self, item_id: str, count: int = 1) -> bool:
        """
        移除物品

        Args:
            item_id: 物品ID
            count: 数量

        Returns:
            bool: 是否移除成功
        """
        if item_id not in self.items:
            return False

        self.items[item_id] -= count
        if self.items[item_id] <= 0:
            del self.items[item_id]
        return True

    def get_count(self, item_id: str) -> int:
        """获取物品数量"""
        return self.items.get(item_id, 0)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "items": copy.deepcopy(self.items),
            "max_size": self.max_size,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Inventory':
        """从字典创建"""
        return cls(
            items=data.get("items", {}),
            max_size=data.get("max_size", 100),
        )


class FlagStore:
    """
    Flag存储器

    支持命名空间隔离的Flag存储，每个Mod可以使用独立的命名空间，
    避免Flag冲突问题。
    """

    def __init__(self, namespace: str = "default"):
        """
        初始化Flag存储器

        Args:
            namespace: 命名空间名称
        """
        self.namespace = namespace
        self._flags: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def set(self, key: str, value: Any) -> None:
        """设置Flag值"""
        with self._lock:
            self._flags[key] = value
            logger.debug(f"[{self.namespace}] Flag set: {key} = {value}")

    def get(self, key: str, default: Any = None) -> Any:
        """获取Flag值"""
        with self._lock:
            return self._flags.get(key, default)

    def delete(self, key: str) -> bool:
        """删除Flag"""
        with self._lock:
            if key in self._flags:
                del self._flags[key]
                return True
            return False

    def has(self, key: str) -> bool:
        """检查Flag是否存在"""
        with self._lock:
            return key in self._flags

    def clear(self) -> None:
        """清空所有Flag"""
        with self._lock:
            self._flags.clear()

    def keys(self) -> List[str]:
        """获取所有Flag键"""
        with self._lock:
            return list(self._flags.keys())

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        with self._lock:
            return copy.deepcopy(self._flags)

    @classmethod
    def from_dict(cls, namespace: str, data: Dict[str, Any]) -> 'FlagStore':
        """从字典创建"""
        store = cls(namespace)
        store._flags = copy.deepcopy(data)
        return store


@dataclass
class CharacterState:
    """
    角色状态

    包含角色的属性、Flag、好感度等信息。
    """
    id: str                              # 角色ID
    name: str                            # 角色名称
    stats: StatBlock = field(default_factory=StatBlock)
    flags: FlagStore = field(default_factory=lambda: FlagStore(""))
    relation: int = 0                    # 好感度
    location: str = ""                   # 当前所在位置

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "stats": self.stats.to_dict(),
            "flags": self.flags.to_dict(),
            "relation": self.relation,
            "location": self.location,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CharacterState':
        """从字典创建"""
        stats = StatBlock.from_dict(data.get("stats", {}))
        flags = FlagStore.from_dict(
            data.get("id", "default"),
            data.get("flags", {})
        )
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            stats=stats,
            flags=flags,
            relation=data.get("relation", 0),
            location=data.get("location", ""),
        )


class GameContext:
    """
    游戏上下文管理器

    这是整个状态管理的核心类，提供分层命名空间的状态访问接口。
    支持世界状态、玩家状态、角色状态的管理，以及全局Flag的存取。

    使用示例：
        context = GameContext()

        # 设置世界状态
        context.set_world("day", 1)
        context.set_world("time_of_day", TimeOfDay.MORNING)

        # 设置玩家属性
        context.set_player_stat("hp", 80)
        context.set_player_stat("money", 1000)

        # 角色操作
        context.add_character("reimu", "博丽灵梦")
        context.set_character_stat("reimu", "hp", 100)
        context.set_character_flag("reimu", "met_player", True)
        context.set_character_relation("reimu", 10)

        # 全局Flag操作
        context.set_global_flag("story", "intro_completed", True)
    """

    def __init__(self):
        """初始化游戏上下文"""
        self._lock = threading.RLock()

        # 世界级状态
        self._world: Dict[str, Any] = {
            "day": 1,
            "time_of_day": TimeOfDay.MORNING.value,
            "location": "home",
            "season": "spring",
            "weather": "clear",
        }

        # 玩家状态
        self._player: Dict[str, Any] = {
            "stats": StatBlock(),
            "inventory": Inventory(),
            "name": "Player",
            "gender": "unknown",
        }

        # 角色状态字典
        self._characters: Dict[str, CharacterState] = {}

        # 全局Flag存储（支持命名空间）
        self._global_flags: Dict[str, FlagStore] = {
            "core": FlagStore("core"),  # 引擎保留命名空间
        }

        # 临时状态（不存档）
        self._temp: Dict[str, Any] = {}

        # 创建默认角色Flag命名空间
        self._character_flags: Dict[str, FlagStore] = {}

        logger.info("游戏上下文初始化完成")

    # ==================== 世界状态操作 ====================

    def get_world(self, key: str, default: Any = None) -> Any:
        """获取世界状态"""
        with self._lock:
            return self._world.get(key, default)

    def set_world(self, key: str, value: Any) -> None:
        """设置世界状态"""
        with self._lock:
            self._world[key] = value
            logger.debug(f"World state set: {key} = {value}")

    def get_day(self) -> int:
        """获取当前天数"""
        return self.get_world("day", 1)

    def set_day(self, day: int) -> None:
        """设置当前天数"""
        self.set_world("day", day)

    def get_time_of_day(self) -> TimeOfDay:
        """获取当前时段"""
        value = self.get_world("time_of_day", "morning")
        return TimeOfDay(value)

    def set_time_of_day(self, time: Union[TimeOfDay, str]) -> None:
        """设置当前时段"""
        if isinstance(time, TimeOfDay):
            time = time.value
        self.set_world("time_of_day", time)

    def get_location(self) -> str:
        """获取当前位置"""
        return self.get_world("location", "")

    def set_location(self, location: str) -> None:
        """设置当前位置"""
        old_location = self.get_location()
        self.set_world("location", location)
        logger.info(f"Location changed: {old_location} -> {location}")

    # ==================== 玩家状态操作 ====================

    def get_player(self, key: str, default: Any = None) -> Any:
        """获取玩家状态"""
        with self._lock:
            return self._player.get(key, default)

    def set_player(self, key: str, value: Any) -> None:
        """设置玩家状态"""
        with self._lock:
            self._player[key] = value

    def get_player_stat(self, stat_name: str, default: int = 0) -> Any:
        """获取玩家属性"""
        with self._lock:
            stats = self._player.get("stats")
            if stats and hasattr(stats, stat_name):
                return getattr(stats, stat_name)
            return default

    def set_player_stat(self, stat_name: str, value: int) -> None:
        """设置玩家属性"""
        with self._lock:
            stats = self._player.get("stats")
            if stats and hasattr(stats, stat_name):
                setattr(stats, stat_name, value)
                stats.clamp_stats()
                logger.debug(f"Player stat set: {stat_name} = {value}")

    def modify_player_stat(self, stat_name: str, delta: int) -> int:
        """
        修改玩家属性（增量）

        Args:
            stat_name: 属性名称
            delta: 增量值（可以为负数）

        Returns:
            int: 修改后的值
        """
        current = self.get_player_stat(stat_name, 0)
        new_value = current + delta
        self.set_player_stat(stat_name, new_value)
        return new_value

    def get_inventory(self) -> Inventory:
        """获取玩家背包"""
        with self._lock:
            return self._player.get("inventory", Inventory())

    def add_item(self, item_id: str, count: int = 1) -> bool:
        """添加物品到背包"""
        inventory = self.get_inventory()
        result = inventory.add_item(item_id, count)
        if result:
            self._player["inventory"] = inventory
            logger.info(f"Item added: {item_id} x{count}")
        return result

    def remove_item(self, item_id: str, count: int = 1) -> bool:
        """从背包移除物品"""
        inventory = self.get_inventory()
        result = inventory.remove_item(item_id, count)
        if result:
            self._player["inventory"] = inventory
            logger.info(f"Item removed: {item_id} x{count}")
        return result

    def get_item_count(self, item_id: str) -> int:
        """获取物品数量"""
        return self.get_inventory().get_count(item_id)

    # ==================== 角色状态操作 ====================

    def add_character(self, char_id: str, name: str) -> CharacterState:
        """
        添加角色

        Args:
            char_id: 角色ID
            name: 角色名称

        Returns:
            CharacterState: 创建的角色状态对象
        """
        with self._lock:
            if char_id in self._characters:
                logger.warning(f"Character already exists: {char_id}")
                return self._characters[char_id]

            char_state = CharacterState(id=char_id, name=name)
            self._characters[char_id] = char_state

            # 为角色创建独立的Flag命名空间
            self._character_flags[char_id] = FlagStore(char_id)

            logger.info(f"Character added: {char_id} ({name})")
            return char_state

    def remove_character(self, char_id: str) -> bool:
        """移除角色"""
        with self._lock:
            if char_id in self._characters:
                del self._characters[char_id]
                if char_id in self._character_flags:
                    del self._character_flags[char_id]
                logger.info(f"Character removed: {char_id}")
                return True
            return False

    def get_character(self, char_id: str) -> Optional[CharacterState]:
        """获取角色状态"""
        with self._lock:
            return self._characters.get(char_id)

    def get_all_characters(self) -> Dict[str, CharacterState]:
        """获取所有角色状态"""
        with self._lock:
            return copy.deepcopy(self._characters)

    def has_character(self, char_id: str) -> bool:
        """检查角色是否存在"""
        with self._lock:
            return char_id in self._characters

    def get_character_stat(self, char_id: str, stat_name: str, default: int = 0) -> Any:
        """获取角色属性"""
        char = self.get_character(char_id)
        if char and hasattr(char.stats, stat_name):
            return getattr(char.stats, stat_name)
        return default

    def set_character_stat(self, char_id: str, stat_name: str, value: int) -> None:
        """设置角色属性"""
        char = self.get_character(char_id)
        if char and hasattr(char.stats, stat_name):
            setattr(char.stats, stat_name, value)
            char.stats.clamp_stats()
            logger.debug(f"Character {char_id} stat set: {stat_name} = {value}")

    def modify_character_stat(self, char_id: str, stat_name: str, delta: int) -> int:
        """修改角色属性（增量）"""
        current = self.get_character_stat(char_id, stat_name, 0)
        new_value = current + delta
        self.set_character_stat(char_id, stat_name, new_value)
        return new_value

    def get_character_relation(self, char_id: str) -> int:
        """获取角色好感度"""
        char = self.get_character(char_id)
        return char.relation if char else 0

    def set_character_relation(self, char_id: str, value: int) -> None:
        """设置角色好感度"""
        char = self.get_character(char_id)
        if char:
            old_value = char.relation
            char.relation = max(-100, min(100, value))  # 限制在-100到100之间
            logger.info(
                f"Character {char_id} relation changed: {old_value} -> {char.relation}"
            )

    def modify_character_relation(self, char_id: str, delta: int) -> int:
        """修改角色好感度（增量）"""
        current = self.get_character_relation(char_id)
        new_value = current + delta
        self.set_character_relation(char_id, new_value)
        return new_value

    def get_character_flag(self, char_id: str, key: str, default: Any = None) -> Any:
        """获取角色Flag"""
        with self._lock:
            flags = self._character_flags.get(char_id)
            if flags:
                return flags.get(key, default)
            return default

    def set_character_flag(self, char_id: str, key: str, value: Any) -> None:
        """设置角色Flag"""
        with self._lock:
            flags = self._character_flags.get(char_id)
            if flags:
                flags.set(key, value)

    def get_character_location(self, char_id: str) -> str:
        """获取角色位置"""
        char = self.get_character(char_id)
        return char.location if char else ""

    def set_character_location(self, char_id: str, location: str) -> None:
        """设置角色位置"""
        char = self.get_character(char_id)
        if char:
            char.location = location

    # ==================== 全局Flag操作 ====================

    def get_global_flag_namespace(self, namespace: str) -> FlagStore:
        """获取指定命名空间的FlagStore"""
        with self._lock:
            if namespace not in self._global_flags:
                self._global_flags[namespace] = FlagStore(namespace)
            return self._global_flags[namespace]

    def get_global_flag(self, namespace: str, key: str, default: Any = None) -> Any:
        """
        获取全局Flag

        Args:
            namespace: 命名空间（如 "story", "quest", "mod_xxx"）
            key: Flag键
            default: 默认值

        Returns:
            Any: Flag值
        """
        store = self.get_global_flag_namespace(namespace)
        return store.get(key, default)

    def set_global_flag(self, namespace: str, key: str, value: Any) -> None:
        """
        设置全局Flag

        Args:
            namespace: 命名空间
            key: Flag键
            value: Flag值
        """
        # 保护核心命名空间
        if namespace == "core":
            logger.warning("Cannot modify core namespace flags directly")
            return

        store = self.get_global_flag_namespace(namespace)
        store.set(key, value)

    def delete_global_flag(self, namespace: str, key: str) -> bool:
        """删除全局Flag"""
        store = self.get_global_flag_namespace(namespace)
        return store.delete(key)

    def has_global_flag(self, namespace: str, key: str) -> bool:
        """检查全局Flag是否存在"""
        store = self.get_global_flag_namespace(namespace)
        return store.has(key)

    # ==================== 临时状态操作 ====================

    def get_temp(self, key: str, default: Any = None) -> Any:
        """获取临时状态（不存档）"""
        return self._temp.get(key, default)

    def set_temp(self, key: str, value: Any) -> None:
        """设置临时状态"""
        self._temp[key] = value

    def clear_temp(self) -> None:
        """清空临时状态"""
        self._temp.clear()

    # ==================== 序列化操作 ====================

    def serialize(self) -> Dict[str, Any]:
        """
        序列化游戏状态

        将整个游戏状态转换为字典，用于存档。

        Returns:
            Dict[str, Any]: 序列化后的字典
        """
        with self._lock:
            return {
                "world": copy.deepcopy(self._world),
                "player": {
                    "stats": self._player.get("stats", StatBlock()).to_dict(),
                    "inventory": self._player.get("inventory", Inventory()).to_dict(),
                    "name": self._player.get("name", "Player"),
                    "gender": self._player.get("gender", "unknown"),
                },
                "characters": {
                    char_id: char_state.to_dict()
                    for char_id, char_state in self._characters.items()
                },
                "global_flags": {
                    namespace: store.to_dict()
                    for namespace, store in self._global_flags.items()
                },
                "character_flags": {
                    char_id: store.to_dict()
                    for char_id, store in self._character_flags.items()
                },
            }

    def deserialize(self, data: Dict[str, Any]) -> None:
        """
        反序列化游戏状态

        从字典恢复游戏状态，用于读档。

        Args:
            data: 序列化后的字典
        """
        with self._lock:
            # 恢复世界状态
            if "world" in data:
                self._world.update(data["world"])

            # 恢复玩家状态
            if "player" in data:
                player_data = data["player"]
                if "stats" in player_data:
                    self._player["stats"] = StatBlock.from_dict(player_data["stats"])
                if "inventory" in player_data:
                    self._player["inventory"] = Inventory.from_dict(player_data["inventory"])
                self._player["name"] = player_data.get("name", "Player")
                self._player["gender"] = player_data.get("gender", "unknown")

            # 恢复角色状态
            if "characters" in data:
                self._characters = {
                    char_id: CharacterState.from_dict(char_data)
                    for char_id, char_data in data["characters"].items()
                }

            # 恢复全局Flag
            if "global_flags" in data:
                self._global_flags = {
                    namespace: FlagStore.from_dict(namespace, flags_data)
                    for namespace, flags_data in data["global_flags"].items()
                }

            # 恢复角色Flag
            if "character_flags" in data:
                self._character_flags = {
                    char_id: FlagStore.from_dict(char_id, flags_data)
                    for char_id, flags_data in data["character_flags"].items()
                }

            logger.info("游戏状态已恢复")

    def reset(self) -> None:
        """
        重置游戏状态

        将所有状态恢复到初始值。
        """
        with self._lock:
            self._world = {
                "day": 1,
                "time_of_day": TimeOfDay.MORNING.value,
                "location": "home",
                "season": "spring",
                "weather": "clear",
            }

            self._player = {
                "stats": StatBlock(),
                "inventory": Inventory(),
                "name": "Player",
                "gender": "unknown",
            }

            self._characters.clear()
            self._global_flags = {"core": FlagStore("core")}
            self._character_flags.clear()
            self._temp.clear()

            logger.info("游戏状态已重置")

    def __repr__(self) -> str:
        """字符串表示"""
        with self._lock:
            return (
                f"GameContext(day={self.get_day()}, "
                f"location={self.get_location()}, "
                f"characters={len(self._characters)})"
            )
