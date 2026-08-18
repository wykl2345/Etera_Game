"""沙箱 / 调度器 / API 白名单 / 剧本端到端测试。"""
import threading
import time
from pathlib import Path

import pytest

from engine.api_bridge import LuaAPI
from engine.event_bus import EventBus
from engine.game_context import GameContext
from engine.loader import ScenarioLoader
from engine.sandbox import (
    DANGEROUS_GLOBALS,
    LUPA_AVAILABLE,
    LuaSandbox,
    ScriptSecurityError,
    ScriptValidator,
)
from engine.script_runner import ScriptScheduler, ScriptAbortedError, UIOutput

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "Data" / "scenarios"


class FakeOutput(UIOutput):
    def __init__(self):
        self.messages = []

    def send(self, msg):
        self.messages.append(msg)


@pytest.fixture
def env():
    """完整引擎最小环境：用 init_engine 组装（与生产一致）。"""
    from engine.bootstrap import init_engine

    output = FakeOutput()
    bundle = init_engine(
        output,
        scripts_dir=SCRIPTS_DIR,
        characters_dir=SCRIPTS_DIR.parent / "characters",
        debug_mode=True,
    )
    return {
        "bus": bundle.bus, "ctx": bundle.ctx, "output": output,
        "sandbox": bundle.sandbox, "scheduler": bundle.scheduler, "api": bundle.api,
    }


# ══════════════════ 沙箱安全 ══════════════════
class TestSandbox:
    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_dangerous_globals_removed(self):
        sb = LuaSandbox()
        for name in ["os", "io", "debug", "require", "loadfile", "dofile", "package"]:
            assert sb.execute(f"return {name} == nil") is True, f"{name} 未删除"

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_math_randomseed_disabled(self):
        sb = LuaSandbox()
        assert sb.execute("return math.randomseed == nil") is True

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_basic_execution(self):
        sb = LuaSandbox()
        assert sb.execute("return 1 + 2") == 3

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_print_redirected(self):
        sb = LuaSandbox()
        # print 被替换为 Python 函数，不应抛异常
        assert sb.execute("print('hello'); return 1") == 1


class TestScriptValidator:
    def test_rejects_os_execute(self):
        ok, err = ScriptValidator.validate('os.execute("rm -rf /")')
        assert ok is False
        assert "os.execute" in err

    def test_rejects_io_open(self):
        ok, _ = ScriptValidator.validate("io.open('/etc/passwd')")
        assert ok is False

    def test_rejects_require(self):
        ok, _ = ScriptValidator.validate("require('socket')")
        assert ok is False

    def test_accepts_normal_code(self):
        ok, err = ScriptValidator.validate("ui.text('你好'); data.set_flag('a','b',1)")
        assert ok is True and err is None

    def test_rejects_empty(self):
        ok, _ = ScriptValidator.validate("")
        assert ok is False


# ══════════════════ 调度器 ══════════════════
class TestScheduler:
    def test_ask_choice_hangs_and_resolves(self, env):
        sched = env["scheduler"]
        output = env["output"]
        result = {}

        def call():
            result["value"] = sched.ask_choice(["a", "b", "c"])

        t = threading.Thread(target=call, daemon=True)
        t.start()
        # 等待挂起并发出消息
        deadline = time.time() + 2
        while time.time() < deadline and not sched.is_waiting():
            time.sleep(0.02)
        assert sched.is_waiting()
        choice_msg = [m for m in output.messages if m["type"] == "ui.ask_choice"][-1]
        assert choice_msg["payload"]["options"] == ["a", "b", "c"]
        sched.resolve_wait(choice_msg["requestId"], choice_index=2)
        t.join(timeout=2)
        assert result["value"] == 2
        assert not sched.is_waiting()

    def test_ask_input(self, env):
        sched = env["scheduler"]
        output = env["output"]
        result = {}

        def call():
            result["value"] = sched.ask_input("名字?", "默认")

        t = threading.Thread(target=call, daemon=True)
        t.start()
        deadline = time.time() + 2
        while time.time() < deadline and not sched.is_waiting():
            time.sleep(0.02)
        msg = [m for m in output.messages if m["type"] == "ui.ask_input"][-1]
        sched.resolve_wait(msg["requestId"], input_text="灵梦")
        t.join(timeout=2)
        assert result["value"] == "灵梦"

    def test_stop_all_raises_aborted(self, env):
        sched = env["scheduler"]
        result = {}

        def call():
            try:
                sched.ask_choice(["a"])
                result["v"] = "no-error"
            except ScriptAbortedError:
                result["v"] = "aborted"

        t = threading.Thread(target=call, daemon=True)
        t.start()
        deadline = time.time() + 2
        while time.time() < deadline and not sched.is_waiting():
            time.sleep(0.02)
        assert sched.is_waiting()
        sched.stop_all()
        t.join(timeout=2)
        assert result["v"] == "aborted"

    def test_path_traversal_blocked(self, env):
        sched = env["scheduler"]
        assert sched._resolve_script_path("../secret.lua") is None
        assert sched._resolve_script_path("../../etc/passwd") is None

    def test_run_script_sync_missing_file(self, env):
        assert env["scheduler"].run_script_sync("no_such.lua") is False


# ══════════════════ API 白名单（数据/世界/工具） ══════════════════
class TestApiBridge:
    def test_data_stat_player(self, env):
        api = env["api"]
        assert api._data_set_stat("player", "money", 100) is True
        assert api._data_get_stat("player", "money") == 100

    def test_data_stat_character(self, env):
        api, ctx = env["api"], env["ctx"]
        ctx.add_character("reimu", "灵梦")
        assert api._data_set_stat("reimu", "relation", 30) is True
        assert api._data_get_relation("reimu") == 30
        assert api._data_modify_relation("reimu", 5) == 35

    def test_data_stat_nonexistent_target(self, env):
        api = env["api"]
        assert api._data_set_stat("nobody", "hp", 1) is False

    def test_data_core_flag_protected(self, env):
        api = env["api"]
        assert api._data_set_flag("core", "engine", 1) is False
        assert api._data_get_flag("core", "engine") is None

    def test_data_flag_namespace(self, env):
        api = env["api"]
        assert api._data_set_flag("story", "intro", True) is True
        assert api._data_get_flag("story", "intro") is True
        assert api._data_has_flag("story", "intro") is True

    def test_data_char_flag(self, env):
        api, ctx = env["api"], env["ctx"]
        ctx.add_character("reimu", "灵梦")
        api._data_set_flag("char:reimu", "met", True)
        assert api._data_get_flag("char:reimu", "met") is True

    def test_data_inventory(self, env):
        api = env["api"]
        assert api._data_add_item("potion", 2) is True
        assert api._data_get_item_count("potion") == 2
        assert api._data_get_inventory() == {"potion": 2}
        assert api._data_remove_item("potion", 1) is True

    def test_data_get_chara(self, env):
        api, ctx = env["api"], env["ctx"]
        ctx.add_character("reimu", "灵梦")
        data = api._data_get_chara("reimu")
        assert data["name"] == "灵梦"
        assert api._data_get_chara("nobody") is None

    def test_world_api(self, env):
        api = env["api"]
        assert api._world_get_day() == 1
        api._world_set_day(5)
        assert api._world_get_day() == 5
        api._world_set_day(0)  # 非法，忽略
        assert api._world_get_day() == 5
        assert api._world_get_time() == "morning"
        api._world_set_time("night")
        assert api._world_get_time() == "night"
        api._world_set_location("village")
        assert api._world_get_location() == "village"

    def test_util_random_range(self, env):
        api = env["api"]
        v = api._util_random_range(5, 1)  # 自动交换
        assert 1 <= v <= 5
        assert 0.0 <= api._util_random() <= 1.0

    def test_ui_text_message(self, env):
        api = env["api"]
        api._ui_text("你好", "white", True)
        msg = env["output"].messages[-1]
        assert msg["type"] == "ui.text"
        assert msg["payload"]["text"] == "你好"
        assert msg["payload"]["color"] == "white"

    def test_ui_text_invalid_color_ignored(self, env):
        api = env["api"]
        api._ui_text("x", "not-a-color")
        assert env["output"].messages[-1]["payload"]["color"] is None


# ══════════════════ 端到端：剧本加载 + 完整流程 ══════════════════
class TestEndToEnd:
    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_loader_registers_all_three(self, env):
        loader = ScenarioLoader(env["sandbox"], env["bus"], SCRIPTS_DIR)
        loaded = loader.load_all()
        assert "story/intro.lua" in loaded
        assert "daily/coffee_shop.lua" in loaded
        assert "daily/marisa_mushroom.lua" in loaded

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_intro_full_flow(self, env):
        """完整闭环：加载 → 触发 on_game_start → 脚本挂起等选项 → 选择 → Flag 生效。"""
        bus, ctx, output = env["bus"], env["ctx"], env["output"]
        sched = env["scheduler"]
        loader = ScenarioLoader(env["sandbox"], bus, SCRIPTS_DIR)
        loader.load_all()

        # 游戏线程触发 on_game_start（脚本内部会挂起等待选项）
        t = threading.Thread(target=lambda: bus.emit("on_game_start"), daemon=True)
        t.start()

        # 等待 ui.ask_choice 出现（含 1.5s sleep，给 8s 余量）
        deadline = time.time() + 8
        choice_msg = None
        while time.time() < deadline:
            msgs = [m for m in output.messages if m["type"] == "ui.ask_choice"]
            if msgs:
                choice_msg = msgs[-1]
                break
            time.sleep(0.05)
        assert choice_msg is not None, "脚本未发出选项（挂起失败）"
        assert choice_msg["payload"]["options"] == ["去村里转转", "在神社帮忙", "去魔法森林探险"]

        # 选 2：在神社帮忙 → first_choice=shrine, reimu 好感 +3
        sched.resolve_wait(choice_msg["requestId"], choice_index=2)
        t.join(timeout=5)
        assert not t.is_alive(), "剧本未在超时内完成"

        assert ctx.get_global_flag("story", "first_choice") == "shrine"
        assert ctx.get_global_flag("story", "intro_completed") is True
        assert ctx.get_character_relation("reimu") == 3

        # 消息流完整：立绘/背景/文本都发出过
        types = {m["type"] for m in output.messages}
        assert "ui.background_set" in types
        assert "ui.character_show" in types
        assert "ui.character_hide" in types

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_intro_only_runs_once(self, env):
        """intro_completed 后再次触发不重复剧情（无新 ask_choice）。"""
        bus, ctx, output = env["bus"], env["ctx"], env["output"]
        loader = ScenarioLoader(env["sandbox"], bus, SCRIPTS_DIR)
        loader.load_all()
        ctx.set_global_flag("story", "intro_completed", True)

        bus.emit("on_game_start")
        # 同步触发完成，不应有 ask_choice 消息
        assert not [m for m in output.messages if m["type"] == "ui.ask_choice"]

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_coffee_shop_daily_event(self, env):
        """日常事件：day≥5 + 灵梦好感≥20 → on_day_begin 触发咖啡店 → 选项 → Flag。"""
        bus, ctx, output = env["bus"], env["ctx"], env["output"]
        sched = env["scheduler"]
        loader = ScenarioLoader(env["sandbox"], bus, SCRIPTS_DIR)
        loader.load_all()

        # 满足触发条件
        ctx.set_day(5)
        ctx.set_character_relation("reimu", 25)

        def run():
            bus.emit("on_day_begin")

        t = threading.Thread(target=run, daemon=True)
        t.start()
        deadline = time.time() + 5
        choice_msg = None
        while time.time() < deadline:
            msgs = [m for m in output.messages if m["type"] == "ui.ask_choice"]
            if msgs:
                choice_msg = msgs[-1]
                break
            time.sleep(0.05)
        assert choice_msg is not None, "咖啡店事件未触发"
        assert choice_msg["payload"]["options"] == ["进去打招呼", "假装没看见"]

        # 选 1：付钱 → 扣钱 + 好感 +5 + met_at_cafe flag
        sched.resolve_wait(choice_msg["requestId"], choice_index=1)
        t.join(timeout=5)
        assert not t.is_alive()
        assert ctx.get_global_flag("coffee_mod", "met_at_cafe") is True
        assert ctx.get_character_relation("reimu") == 5  # set_stat 设绝对值

