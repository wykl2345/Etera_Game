"""SaveManager 单元测试（复用 v1 测试要点）。"""
import pytest

from engine.event_bus import EventBus
from engine.game_context import GameContext
from engine.save_manager import (
    CURRENT_VERSION,
    MIGRATION_CHAIN,
    Migration_1_0_to_1_1,
    SaveManager,
)


@pytest.fixture
def save_manager(tmp_path):
    bus = EventBus()
    ctx = GameContext()
    mgr = SaveManager(bus, ctx, base_dir=tmp_path / "saves")
    mgr.start_session()
    return mgr, ctx


def _populate(ctx):
    ctx.set_day(7)
    ctx.set_location("village")
    ctx.set_player_stat("money", 500)
    ctx.set_player_stat("hp", 60)
    ctx.add_item("potion", 3)
    ctx.add_character("reimu", "灵梦")
    ctx.set_character_relation("reimu", 25)
    ctx.set_character_stat("reimu", "hp", 80)
    ctx.set_global_flag("story", "intro_done", True)
    ctx.set_character_flag("reimu", "met", True)


class TestSaveLoadRoundtrip:
    def test_roundtrip(self, save_manager):
        mgr, ctx = save_manager
        _populate(ctx)
        assert mgr.save(1, description="测试存档") is True

        ctx.reset()
        assert mgr.load(1) is True

        assert ctx.get_day() == 7
        assert ctx.get_location() == "village"
        assert ctx.get_player_stat("money") == 500
        assert ctx.get_player_stat("hp") == 60
        assert ctx.get_item_count("potion") == 3
        assert ctx.get_character_relation("reimu") == 25
        assert ctx.get_character_stat("reimu", "hp") == 80
        assert ctx.get_global_flag("story", "intro_done") is True
        assert ctx.get_character_flag("reimu", "met") is True

    def test_save_overwrites_previous(self, save_manager):
        mgr, ctx = save_manager
        ctx.set_day(3)
        assert mgr.save(1) is True
        ctx.set_day(9)
        assert mgr.save(1) is True
        ctx.reset()
        assert mgr.load(1) is True
        assert ctx.get_day() == 9

    def test_load_empty_slot_false(self, save_manager):
        mgr, _ = save_manager
        assert mgr.load(15) is False


class TestSaveSlots:
    def test_twenty_slots(self, save_manager):
        mgr, ctx = save_manager
        _populate(ctx)
        slots = mgr.get_save_slots()
        assert len(slots) == 20
        assert all(s.slot_id == i for i, s in enumerate(slots))

    def test_empty_slot_no_metadata(self, save_manager):
        mgr, _ = save_manager
        slots = mgr.get_save_slots()
        assert slots[5].exists is False
        assert slots[5].metadata is None

    def test_metadata(self, save_manager):
        mgr, ctx = save_manager
        ctx.set_day(12)
        ctx.set_location("forest")
        assert mgr.save(3, description="森林存档") is True
        slot = mgr.get_save_info(3)
        assert slot.exists is True
        assert slot.metadata.day == 12
        assert slot.metadata.location == "forest"
        assert slot.metadata.description == "森林存档"
        assert slot.metadata.save_time  # 非空

    def test_delete(self, save_manager):
        mgr, ctx = save_manager
        _populate(ctx)
        assert mgr.save(2) is True
        assert mgr.delete(2) is True
        assert mgr.delete(2) is False
        assert mgr.get_save_info(2).exists is False

    def test_invalid_slot(self, save_manager):
        mgr, _ = save_manager
        assert mgr.save(-1) is False
        assert mgr.save(999) is False
        assert mgr.load(-1) is False


class TestQuickSave:
    def test_quick_save_load(self, save_manager):
        mgr, ctx = save_manager
        _populate(ctx)
        assert mgr.quick_save() is True
        assert mgr.has_quick_save() is True

        ctx.reset()
        assert mgr.quick_load() is True
        assert ctx.get_day() == 7

    def test_quick_load_no_save_false(self, save_manager):
        mgr, _ = save_manager
        assert mgr.has_quick_save() is False
        assert mgr.quick_load() is False


class TestMigration:
    def test_chain_registered(self):
        assert ("1.0", "1.1") in MIGRATION_CHAIN
        assert ("1.1", "1.2") in MIGRATION_CHAIN
        assert ("1.2", "1.3") in MIGRATION_CHAIN
        assert ("1.3", "2.0.0") in MIGRATION_CHAIN

    def test_migrate_1_0_to_1_1(self):
        data = {"meta": {"version": "1.0"}, "world": {}}
        result = Migration_1_0_to_1_1.migrate(data)
        assert result["world"]["time_of_day"] == "morning"
        assert result["world"]["season"] == "spring"
        assert result["meta"]["version"] == "1.1"

    def test_full_chain_migration(self, save_manager, tmp_path):
        """1.0 存档经完整链迁移到当前版本。"""
        mgr, ctx = save_manager
        old_data = {
            "meta": {"version": "1.0"},
            "world": {"day": 3, "location": "home"},
            "player": {"stats": {"hp": 50, "max_hp": 100, "mp": 30, "max_mp": 50,
                                 "stamina": 90, "max_stamina": 100, "money": 10,
                                 "exp": 0, "level": 1}, "inventory": {}, "name": "", "gender": "unknown"},
            "characters": {},
            "global_flags": {},
        }
        save_file = mgr._slot_path(4)
        import json
        save_file.write_text(json.dumps(old_data, ensure_ascii=False), encoding="utf-8")

        assert mgr.load(4) is True
        assert ctx.get_day() == 3
        assert ctx.get_player_stat("hp") == 50
        assert ctx.get_world("time_of_day") == "morning"
        assert ctx.get_world("season") == "spring"
        assert ctx.get_world("weather") == "clear"

        # 迁移后的存档版本应为当前版本
        reloaded = mgr._read_save_file(4)
        assert reloaded["meta"]["version"] == CURRENT_VERSION
