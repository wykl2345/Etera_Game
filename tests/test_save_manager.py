"""
SaveManager 单元测试

覆盖：保存/加载往返、快速存档、删除、槽位管理、版本迁移。

注意：SaveManager 依赖 GameContext 和 EventBus，
      使用真实的 GameContext 实例测试数据持久化。
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from Core.state.save_manager import (
    SaveManager, SaveMetadata, SaveSlot,
    CURRENT_VERSION, MIGRATION_CHAIN
)
from Core.state.game_context import GameContext
from Core.engine.event_bus import EventBus


@pytest.fixture
def temp_save_dir():
    """创建临时存档目录"""
    tmp = Path(tempfile.mkdtemp(prefix="ee1_test_saves_"))
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def save_manager(temp_save_dir):
    """创建 SaveManager 实例"""
    event_bus = EventBus()
    context = GameContext()
    return SaveManager(
        event_bus=event_bus,
        game_context=context,
        base_dir=temp_save_dir
    ), context


class TestSaveLoadRoundtrip:
    """保存/加载往返"""

    def test_save_and_load_preserves_day(self, save_manager):
        mgr, ctx = save_manager
        ctx.set_day(42)
        assert mgr.save(slot_id=1, description="测试存档")
        assert mgr.load(slot_id=1)
        assert ctx.get_day() == 42

    def test_save_and_load_preserves_location(self, save_manager):
        mgr, ctx = save_manager
        ctx.set_location("magic_forest")
        mgr.save(slot_id=1)
        mgr.load(slot_id=1)
        assert ctx.get_location() == "magic_forest"

    def test_save_and_load_preserves_player_stats(self, save_manager):
        mgr, ctx = save_manager
        ctx.set_player_stat("hp", 30)
        ctx.set_player_stat("money", 5000)
        mgr.save(slot_id=1)
        mgr.load(slot_id=1)
        assert ctx.get_player_stat("hp") == 30
        assert ctx.get_player_stat("money") == 5000

    def test_save_and_load_preserves_inventory(self, save_manager):
        mgr, ctx = save_manager
        ctx.add_item("mushroom", 5)
        ctx.add_item("key", 1)
        mgr.save(slot_id=1)
        mgr.load(slot_id=1)
        assert ctx.get_item_count("mushroom") == 5
        assert ctx.get_item_count("key") == 1

    def test_save_and_load_preserves_characters(self, save_manager):
        mgr, ctx = save_manager
        ctx.add_character("reimu", "灵梦")
        ctx.set_character_relation("reimu", 50)
        ctx.set_character_stat("reimu", "hp", 80)
        mgr.save(slot_id=1)
        mgr.load(slot_id=1)
        assert ctx.has_character("reimu")
        assert ctx.get_character_relation("reimu") == 50
        assert ctx.get_character_stat("reimu", "hp") == 80

    def test_save_and_load_preserves_flags(self, save_manager):
        mgr, ctx = save_manager
        ctx.set_global_flag("story", "intro_done", True)
        ctx.set_global_flag("story", "choice", "forest")
        mgr.save(slot_id=1)
        mgr.load(slot_id=1)
        assert ctx.get_global_flag("story", "intro_done") is True
        assert ctx.get_global_flag("story", "choice") == "forest"

    def test_save_overwrites_previous(self, save_manager):
        mgr, ctx = save_manager
        ctx.set_day(1)
        mgr.save(slot_id=1)
        ctx.set_day(99)
        mgr.save(slot_id=1)
        # 重新加载应该是 99
        ctx.set_day(0)  # 先改掉
        mgr.load(slot_id=1)
        assert ctx.get_day() == 99


class TestSaveSlots:
    """槽位管理"""

    def test_get_save_slots_returns_list(self, save_manager):
        mgr, ctx = save_manager
        slots = mgr.get_save_slots()
        assert len(slots) == 20  # MAX_SAVE_SLOTS

    def test_empty_slot_has_no_metadata(self, save_manager):
        mgr, ctx = save_manager
        slots = mgr.get_save_slots()
        empty_slot = slots[5]
        assert empty_slot.exists is False
        assert empty_slot.metadata is None

    def test_saved_slot_has_metadata(self, save_manager):
        mgr, ctx = save_manager
        ctx.set_day(7)
        ctx.set_location("hakurei_shrine")
        mgr.save(slot_id=3, description="第七章")

        slots = mgr.get_save_slots()
        slot = slots[3]
        assert slot.exists is True
        assert slot.metadata is not None
        assert slot.metadata.day == 7
        assert slot.metadata.location == "hakurei_shrine"
        assert slot.metadata.description == "第七章"

    def test_delete_slot(self, save_manager):
        mgr, ctx = save_manager
        mgr.save(slot_id=5)
        assert mgr.delete(slot_id=5) is True
        slots = mgr.get_save_slots()
        assert slots[5].exists is False

    def test_delete_nonexistent_slot(self, save_manager):
        mgr, ctx = save_manager
        assert mgr.delete(slot_id=10) is False


class TestQuickSave:
    """快速存档"""

    def test_quick_save_and_load(self, save_manager):
        mgr, ctx = save_manager
        ctx.set_day(42)
        assert mgr.quick_save() is True
        assert mgr.has_quick_save() is True

        # 修改状态
        ctx.set_day(1)
        assert mgr.quick_load() is True
        assert ctx.get_day() == 42

    def test_has_quick_save_false_when_empty(self, save_manager):
        mgr, ctx = save_manager
        assert mgr.has_quick_save() is False

    def test_quick_load_nonexistent(self, save_manager):
        mgr, ctx = save_manager
        assert mgr.quick_load() is False


class TestMetadata:
    """存档元数据"""

    def test_save_metadata_includes_version(self, save_manager):
        mgr, ctx = save_manager
        mgr.save(slot_id=1)
        slots = mgr.get_save_slots()
        assert slots[1].metadata.version == CURRENT_VERSION

    def test_save_metadata_includes_save_time(self, save_manager):
        mgr, ctx = save_manager
        mgr.save(slot_id=1)
        slots = mgr.get_save_slots()
        assert slots[1].metadata.save_time != ""


class TestMigration:
    """版本迁移链"""

    def test_migration_chain_is_registered(self):
        """确保迁移链包含所有版本"""
        assert ("1.0", "1.1") in MIGRATION_CHAIN
        assert ("1.1", "1.2") in MIGRATION_CHAIN
        assert ("1.2", "1.3") in MIGRATION_CHAIN

    def test_migrate_1_0_to_1_1_adds_time_of_day(self):
        from Core.state.save_manager import Migration_1_0_to_1_1
        data = {
            "meta": {"version": "1.0"},
            "world": {"day": 1}
        }
        result = Migration_1_0_to_1_1.migrate(data)
        assert result["world"]["time_of_day"] == "morning"
        assert result["world"]["season"] == "spring"
        assert result["meta"]["version"] == "1.1"

    def test_migrate_1_1_to_1_2_restructures_characters(self):
        from Core.state.save_manager import Migration_1_1_to_1_2
        data = {
            "meta": {"version": "1.1"},
            "characters": {
                "reimu": {"name": "灵梦", "stats": {"hp": 100}}
            }
        }
        result = Migration_1_1_to_1_2.migrate(data)
        char = result["characters"]["reimu"]
        assert char["id"] == "reimu"
        assert char["relation"] == 0  # 新字段有默认值
        assert "character_flags" in result
        assert result["meta"]["version"] == "1.2"

    def test_migrate_1_2_to_1_3_adds_weather(self):
        from Core.state.save_manager import Migration_1_2_to_1_3
        data = {
            "meta": {"version": "1.2"},
            "world": {"day": 1}
        }
        result = Migration_1_2_to_1_3.migrate(data)
        assert result["world"]["weather"] == "clear"
        assert result["meta"]["version"] == "1.3"


class TestEdgeCases:
    """边界情况"""

    def test_invalid_slot_id_negative(self, save_manager):
        mgr, ctx = save_manager
        assert mgr.save(slot_id=-1) is False

    def test_invalid_slot_id_too_large(self, save_manager):
        mgr, ctx = save_manager
        assert mgr.save(slot_id=999) is False

    def test_load_nonexistent_slot(self, save_manager):
        mgr, ctx = save_manager
        assert mgr.load(slot_id=15) is False
