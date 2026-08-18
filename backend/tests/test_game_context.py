"""GameContext 单元测试（复用 v1 测试要点）。"""
import pytest

from engine.game_context import (
    GameContext,
    Inventory,
    StatBlock,
    TimeOfDay,
)


@pytest.fixture
def ctx():
    return GameContext()


class TestWorldState:
    def test_initial_day_is_1(self, ctx):
        assert ctx.get_day() == 1

    def test_set_get_day(self, ctx):
        ctx.set_day(5)
        assert ctx.get_day() == 5

    def test_time_of_day_default_morning(self, ctx):
        assert ctx.get_time_of_day() == TimeOfDay.MORNING

    def test_time_of_day_set_enum_and_str(self, ctx):
        ctx.set_time_of_day(TimeOfDay.NIGHT)
        assert ctx.get_time_of_day() == TimeOfDay.NIGHT
        ctx.set_time_of_day("dawn")
        assert ctx.get_time_of_day() == TimeOfDay.DAWN

    def test_location_default_home(self, ctx):
        assert ctx.get_location() == "home"


class TestPlayerStats:
    def test_defaults(self, ctx):
        assert ctx.get_player_stat("hp") == 100
        assert ctx.get_player_stat("mp") == 50
        assert ctx.get_player_stat("money") == 0
        assert ctx.get_player_stat("level") == 1

    def test_set_get(self, ctx):
        ctx.set_player_stat("hp", 80)
        assert ctx.get_player_stat("hp") == 80

    def test_modify(self, ctx):
        ctx.modify_player_stat("money", 30)
        assert ctx.get_player_stat("money") == 30

    def test_negative_clamped_to_zero(self, ctx):
        ctx.set_player_stat("hp", -10)
        assert ctx.get_player_stat("hp") == 0

    def test_unknown_stat_returns_default(self, ctx):
        assert ctx.get_player_stat("nonexistent", 99) == 99


class TestInventory:
    def test_add_item(self, ctx):
        assert ctx.add_item("potion", 2) is True
        assert ctx.get_item_count("potion") == 2

    def test_add_accumulates(self, ctx):
        ctx.add_item("potion", 1)
        ctx.add_item("potion", 3)
        assert ctx.get_item_count("potion") == 4

    def test_remove_item(self, ctx):
        ctx.add_item("potion", 5)
        assert ctx.remove_item("potion", 2) is True
        assert ctx.get_item_count("potion") == 3

    def test_remove_nonexistent_false(self, ctx):
        assert ctx.remove_item("nope") is False

    def test_count_zero_for_unknown(self, ctx):
        assert ctx.get_item_count("unknown") == 0


class TestCharacterManagement:
    def test_add_get(self, ctx):
        ch = ctx.add_character("reimu", "灵梦")
        assert ctx.get_character("reimu") is ch

    def test_get_nonexistent_none(self, ctx):
        assert ctx.get_character("nobody") is None

    def test_has_character(self, ctx):
        ctx.add_character("reimu", "灵梦")
        assert ctx.has_character("reimu") is True
        assert ctx.has_character("marisa") is False

    def test_remove(self, ctx):
        ctx.add_character("reimu", "灵梦")
        assert ctx.remove_character("reimu") is True
        assert ctx.remove_character("reimu") is False

    def test_relation_default_zero(self, ctx):
        ctx.add_character("marisa", "魔理沙")
        assert ctx.get_character_relation("marisa") == 0

    def test_relation_clamped(self, ctx):
        ctx.add_character("marisa", "魔理沙")
        ctx.set_character_relation("marisa", 500)
        assert ctx.get_character_relation("marisa") == 100
        ctx.set_character_relation("marisa", -500)
        assert ctx.get_character_relation("marisa") == -100

    def test_modify_relation(self, ctx):
        ctx.add_character("marisa", "魔理沙")
        assert ctx.modify_character_relation("marisa", 15) == 15

    def test_character_stat(self, ctx):
        ctx.add_character("marisa", "魔理沙")
        ctx.set_character_stat("marisa", "mp", 40)
        assert ctx.get_character_stat("marisa", "mp") == 40
        ctx.modify_character_stat("marisa", "mp", -20)
        assert ctx.get_character_stat("marisa", "mp") == 20

    def test_character_stat_clamped_to_max(self, ctx):
        # v1 语义：set 内部 clamp 到 max_mp
        ctx.add_character("marisa", "魔理沙")
        ctx.set_character_stat("marisa", "mp", 500)
        assert ctx.get_character_stat("marisa", "mp") == 50

    def test_character_location(self, ctx):
        ctx.add_character("reimu", "灵梦")
        ctx.set_character_location("reimu", "shrine")
        assert ctx.get_character_location("reimu") == "shrine"


class TestGlobalFlags:
    def test_set_get(self, ctx):
        ctx.set_global_flag("story", "intro_done", True)
        assert ctx.get_global_flag("story", "intro_done") is True

    def test_default_value(self, ctx):
        assert ctx.get_global_flag("story", "missing", "d") == "d"

    def test_namespace_isolation(self, ctx):
        ctx.set_global_flag("mod_a", "key", 1)
        ctx.set_global_flag("mod_b", "key", 2)
        assert ctx.get_global_flag("mod_a", "key") == 1
        assert ctx.get_global_flag("mod_b", "key") == 2

    def test_core_namespace_protected(self, ctx):
        ctx.set_global_flag("core", "engine_key", "x")
        assert ctx.get_global_flag("core", "engine_key") is None

    def test_has_and_delete(self, ctx):
        ctx.set_global_flag("story", "k", 1)
        assert ctx.has_global_flag("story", "k") is True
        assert ctx.delete_global_flag("story", "k") is True
        assert ctx.delete_global_flag("story", "k") is False


class TestCharacterFlags:
    def test_set_get(self, ctx):
        ctx.add_character("reimu", "灵梦")
        ctx.set_character_flag("reimu", "met", True)
        assert ctx.get_character_flag("reimu", "met") is True

    def test_unknown_character_returns_default(self, ctx):
        assert ctx.get_character_flag("nobody", "x", "d") == "d"

    def test_isolation_between_characters(self, ctx):
        ctx.add_character("reimu", "灵梦")
        ctx.add_character("marisa", "魔理沙")
        ctx.set_character_flag("reimu", "k", 1)
        assert ctx.get_character_flag("marisa", "k") is None


class TestSerialization:
    def test_roundtrip(self, ctx):
        ctx.set_day(7)
        ctx.set_world("weather", "rain")
        ctx.set_player_stat("money", 500)
        ctx.add_item("potion", 3)
        ctx.add_character("reimu", "灵梦")
        ctx.set_character_relation("reimu", 25)
        ctx.set_character_stat("reimu", "hp", 60)
        ctx.set_global_flag("story", "intro_done", True)
        ctx.set_character_flag("reimu", "met", True)

        data = ctx.serialize()
        new_ctx = GameContext()
        new_ctx.deserialize(data)

        assert new_ctx.get_day() == 7
        assert new_ctx.get_world("weather") == "rain"
        assert new_ctx.get_player_stat("money") == 500
        assert new_ctx.get_item_count("potion") == 3
        assert new_ctx.get_character_relation("reimu") == 25
        assert new_ctx.get_character_stat("reimu", "hp") == 60
        assert new_ctx.get_global_flag("story", "intro_done") is True
        assert new_ctx.get_character_flag("reimu", "met") is True


class TestReset:
    def test_reset_clears_all(self, ctx):
        ctx.set_day(99)
        ctx.add_character("reimu", "灵梦")
        ctx.set_player_stat("money", 999)
        ctx.reset()
        assert ctx.get_day() == 1
        assert ctx.get_player_stat("money") == 0
        assert ctx.has_character("reimu") is False


class TestStatBlock:
    def test_to_from_dict(self):
        sb = StatBlock(hp=50, max_hp=120, money=10)
        sb2 = StatBlock.from_dict(sb.to_dict())
        assert sb2.hp == 50
        assert sb2.max_hp == 120
        assert sb2.money == 10

    def test_clamp(self):
        sb = StatBlock(hp=200, max_hp=100)
        sb.clamp_stats()
        assert sb.hp == 100


class TestInventoryUnit:
    def test_inventory_dict_roundtrip(self):
        inv = Inventory(items={"a": 2, "b": 1})
        inv2 = Inventory.from_dict(inv.to_dict())
        assert inv2.get_count("a") == 2
        assert inv2.get_count("b") == 1
