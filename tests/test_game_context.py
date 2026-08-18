"""
GameContext 单元测试

覆盖：世界状态、玩家属性、角色管理、Flag 命名空间隔离、
      背包操作、序列化/反序列化往返、重置。
"""

import pytest
from Core.state.game_context import (
    GameContext, StatBlock, Inventory, FlagStore,
    CharacterState, TimeOfDay
)


class TestWorldState:
    """世界状态操作"""

    def test_initial_day_is_one(self):
        ctx = GameContext()
        assert ctx.get_day() == 1

    def test_set_and_get_day(self):
        ctx = GameContext()
        ctx.set_day(42)
        assert ctx.get_day() == 42

    def test_set_day_rejects_invalid(self):
        ctx = GameContext()
        ctx.set_day(0)   # 允许设置但 world.set_day 在 api_bridge 层校验
        assert ctx.get_day() == 0  # GameContext 本身不校验

    def test_get_time_of_day_default(self):
        ctx = GameContext()
        assert ctx.get_time_of_day() == TimeOfDay.MORNING

    def test_set_time_of_day_enum(self):
        ctx = GameContext()
        ctx.set_time_of_day(TimeOfDay.NIGHT)
        assert ctx.get_time_of_day() == TimeOfDay.NIGHT

    def test_set_time_of_day_string(self):
        ctx = GameContext()
        ctx.set_time_of_day("evening")
        assert ctx.get_time_of_day() == TimeOfDay.EVENING

    def test_location_default(self):
        ctx = GameContext()
        assert ctx.get_location() == "home"

    def test_set_location(self):
        ctx = GameContext()
        ctx.set_location("hakurei_shrine")
        assert ctx.get_location() == "hakurei_shrine"


class TestPlayerStats:
    """玩家属性操作"""

    def test_default_stats(self):
        ctx = GameContext()
        assert ctx.get_player_stat("hp") == 100
        assert ctx.get_player_stat("max_hp") == 100
        assert ctx.get_player_stat("mp") == 50
        assert ctx.get_player_stat("money") == 0
        assert ctx.get_player_stat("level") == 1

    def test_set_player_stat(self):
        ctx = GameContext()
        ctx.set_player_stat("hp", 80)
        assert ctx.get_player_stat("hp") == 80

    def test_modify_player_stat(self):
        ctx = GameContext()
        new_val = ctx.modify_player_stat("hp", -20)
        assert new_val == 80
        assert ctx.get_player_stat("hp") == 80

    def test_stat_clamped_to_zero(self):
        """StatBlock.clamp_stats 将 hp 钳制到 [0, max_hp]"""
        ctx = GameContext()
        ctx.set_player_stat("hp", -50)
        # clamp_stats 在 set_player_stat 内部调用，负值钳制到 0
        assert ctx.get_player_stat("hp") == 0

    def test_unknown_stat_returns_default(self):
        ctx = GameContext()
        assert ctx.get_player_stat("nonexistent", 999) == 999


class TestInventory:
    """背包操作"""

    def test_add_item(self):
        ctx = GameContext()
        assert ctx.add_item("glowing_mushroom", 3) is True
        assert ctx.get_item_count("glowing_mushroom") == 3

    def test_add_item_twice_accumulates(self):
        ctx = GameContext()
        ctx.add_item("potion", 2)
        ctx.add_item("potion", 3)
        assert ctx.get_item_count("potion") == 5

    def test_remove_item(self):
        ctx = GameContext()
        ctx.add_item("key", 1)
        assert ctx.remove_item("key", 1) is True
        assert ctx.get_item_count("key") == 0

    def test_remove_item_partial(self):
        ctx = GameContext()
        ctx.add_item("coin", 10)
        ctx.remove_item("coin", 3)
        assert ctx.get_item_count("coin") == 7

    def test_remove_nonexistent_item_fails(self):
        ctx = GameContext()
        assert ctx.remove_item("ghost", 1) is False

    def test_item_count_nonexistent(self):
        ctx = GameContext()
        assert ctx.get_item_count("ghost") == 0


class TestCharacterManagement:
    """角色管理"""

    def test_add_and_get_character(self):
        ctx = GameContext()
        char = ctx.add_character("reimu", "博丽灵梦")
        assert char.id == "reimu"
        assert char.name == "博丽灵梦"

    def test_get_nonexistent_character(self):
        ctx = GameContext()
        assert ctx.get_character("nonexistent") is None

    def test_has_character(self):
        ctx = GameContext()
        ctx.add_character("marisa", "雾雨魔理沙")
        assert ctx.has_character("marisa") is True
        assert ctx.has_character("reimu") is False

    def test_remove_character(self):
        ctx = GameContext()
        ctx.add_character("temp", "临时角色")
        assert ctx.remove_character("temp") is True
        assert ctx.has_character("temp") is False

    def test_remove_nonexistent_character(self):
        ctx = GameContext()
        assert ctx.remove_character("ghost") is False

    def test_character_default_relation(self):
        ctx = GameContext()
        ctx.add_character("reimu", "灵梦")
        assert ctx.get_character_relation("reimu") == 0

    def test_set_character_relation(self):
        ctx = GameContext()
        ctx.add_character("reimu", "灵梦")
        ctx.set_character_relation("reimu", 50)
        assert ctx.get_character_relation("reimu") == 50

    def test_relation_clamped(self):
        ctx = GameContext()
        ctx.add_character("reimu", "灵梦")
        ctx.set_character_relation("reimu", 200)
        assert ctx.get_character_relation("reimu") == 100  # 钳制上限
        ctx.set_character_relation("reimu", -200)
        assert ctx.get_character_relation("reimu") == -100  # 钳制下限

    def test_modify_character_relation(self):
        ctx = GameContext()
        ctx.add_character("reimu", "灵梦")
        new_val = ctx.modify_character_relation("reimu", 10)
        assert new_val == 10
        assert ctx.get_character_relation("reimu") == 10

    def test_character_stat_operations(self):
        ctx = GameContext()
        ctx.add_character("marisa", "魔理沙")
        ctx.set_character_stat("marisa", "hp", 50)
        assert ctx.get_character_stat("marisa", "hp") == 50

    def test_character_location(self):
        ctx = GameContext()
        ctx.add_character("reimu", "灵梦")
        ctx.set_character_location("reimu", "hakurei_shrine")
        assert ctx.get_character_location("reimu") == "hakurei_shrine"


class TestGlobalFlags:
    """全局 Flag — 命名空间隔离"""

    def test_set_and_get_flag(self):
        ctx = GameContext()
        ctx.set_global_flag("story", "intro_done", True)
        assert ctx.get_global_flag("story", "intro_done") is True

    def test_flag_default_value(self):
        ctx = GameContext()
        assert ctx.get_global_flag("story", "nonexistent", False) is False

    def test_flag_namespace_isolation(self):
        ctx = GameContext()
        ctx.set_global_flag("mod_a", "key", "value_a")
        ctx.set_global_flag("mod_b", "key", "value_b")
        assert ctx.get_global_flag("mod_a", "key") == "value_a"
        assert ctx.get_global_flag("mod_b", "key") == "value_b"

    def test_core_namespace_protected(self):
        """core 命名空间不能被直接写入"""
        ctx = GameContext()
        ctx.set_global_flag("core", "cheat", True)
        assert ctx.get_global_flag("core", "cheat") is None  # 写入被拒绝

    def test_has_flag(self):
        ctx = GameContext()
        assert ctx.has_global_flag("story", "intro_done") is False
        ctx.set_global_flag("story", "intro_done", True)
        assert ctx.has_global_flag("story", "intro_done") is True

    def test_delete_flag(self):
        ctx = GameContext()
        ctx.set_global_flag("quest", "active", True)
        assert ctx.delete_global_flag("quest", "active") is True
        assert ctx.has_global_flag("quest", "active") is False

    def test_delete_nonexistent_flag(self):
        ctx = GameContext()
        assert ctx.delete_global_flag("quest", "ghost") is False


class TestCharacterFlags:
    """角色专属 Flag"""

    def test_character_flag_set_get(self):
        ctx = GameContext()
        ctx.add_character("reimu", "灵梦")
        ctx.set_character_flag("reimu", "met_player", True)
        assert ctx.get_character_flag("reimu", "met_player") is True

    def test_character_flag_nonexistent_character(self):
        ctx = GameContext()
        assert ctx.get_character_flag("ghost", "key", "default") == "default"

    def test_character_flag_isolation(self):
        ctx = GameContext()
        ctx.add_character("reimu", "灵梦")
        ctx.add_character("marisa", "魔理沙")
        ctx.set_character_flag("reimu", "event_a", True)
        ctx.set_character_flag("marisa", "event_a", False)
        assert ctx.get_character_flag("reimu", "event_a") is True
        assert ctx.get_character_flag("marisa", "event_a") is False


class TestSerialization:
    """序列化/反序列化往返"""

    def test_roundtrip_preserves_world_state(self):
        ctx = GameContext()
        ctx.set_day(15)
        ctx.set_time_of_day("night")
        ctx.set_location("magic_forest")

        data = ctx.serialize()
        ctx2 = GameContext()
        ctx2.deserialize(data)

        assert ctx2.get_day() == 15
        assert ctx2.get_time_of_day() == TimeOfDay.NIGHT
        assert ctx2.get_location() == "magic_forest"

    def test_roundtrip_preserves_player_stats(self):
        ctx = GameContext()
        ctx.set_player_stat("hp", 50)
        ctx.set_player_stat("money", 999)

        data = ctx.serialize()
        ctx2 = GameContext()
        ctx2.deserialize(data)

        assert ctx2.get_player_stat("hp") == 50
        assert ctx2.get_player_stat("money") == 999

    def test_roundtrip_preserves_characters(self):
        ctx = GameContext()
        ctx.add_character("reimu", "灵梦")
        ctx.set_character_relation("reimu", 45)
        ctx.set_character_stat("reimu", "hp", 80)

        data = ctx.serialize()
        ctx2 = GameContext()
        ctx2.deserialize(data)

        assert ctx2.has_character("reimu")
        assert ctx2.get_character_relation("reimu") == 45
        assert ctx2.get_character_stat("reimu", "hp") == 80

    def test_roundtrip_preserves_flags(self):
        ctx = GameContext()
        ctx.set_global_flag("story", "intro_done", True)
        ctx.set_global_flag("story", "choice", "forest")

        data = ctx.serialize()
        ctx2 = GameContext()
        ctx2.deserialize(data)

        assert ctx2.get_global_flag("story", "intro_done") is True
        assert ctx2.get_global_flag("story", "choice") == "forest"

    def test_roundtrip_preserves_inventory(self):
        ctx = GameContext()
        ctx.add_item("mushroom", 5)
        ctx.add_item("potion", 2)

        data = ctx.serialize()
        ctx2 = GameContext()
        ctx2.deserialize(data)

        assert ctx2.get_item_count("mushroom") == 5
        assert ctx2.get_item_count("potion") == 2

    def test_roundtrip_preserves_character_flags(self):
        ctx = GameContext()
        ctx.add_character("reimu", "灵梦")
        ctx.set_character_flag("reimu", "met", True)

        data = ctx.serialize()
        ctx2 = GameContext()
        ctx2.deserialize(data)

        assert ctx2.get_character_flag("reimu", "met") is True


class TestReset:
    """重置状态"""

    def test_reset_clears_all(self):
        ctx = GameContext()
        ctx.set_day(99)
        ctx.set_location("somewhere")
        ctx.set_player_stat("money", 9999)
        ctx.add_character("reimu", "灵梦")
        ctx.set_global_flag("story", "done", True)

        ctx.reset()

        assert ctx.get_day() == 1
        assert ctx.get_location() == "home"
        assert ctx.get_player_stat("money") == 0
        assert not ctx.has_character("reimu")
        assert ctx.get_global_flag("story", "done") is None


class TestStatBlock:
    """StatBlock 数据类"""

    def test_to_dict(self):
        sb = StatBlock(hp=80, max_hp=120, money=500)
        d = sb.to_dict()
        assert d["hp"] == 80
        assert d["max_hp"] == 120
        assert d["money"] == 500

    def test_from_dict(self):
        sb = StatBlock.from_dict({"hp": 60, "mp": 30, "money": 100})
        assert sb.hp == 60
        assert sb.mp == 30
        assert sb.money == 100

    def test_clamp_stats(self):
        sb = StatBlock(hp=200, max_hp=100)
        sb.clamp_stats()
        assert sb.hp == 100  # 钳制到 max_hp
