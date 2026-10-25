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


def _wait_choice(output, first_option: str, timeout: float = 8.0):
    """按首个选项文案等待对应的 ask_choice 消息（比按计数健壮）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for m in output.messages:
            if (m["type"] == "ui.ask_choice"
                    and m["payload"]["options"]
                    and m["payload"]["options"][0] == first_option):
                return m
        time.sleep(0.05)
    return None


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

    def test_ask_minigame_hangs_and_resolves(self, env):
        sched = env["scheduler"]
        output = env["output"]
        result = {}

        def call():
            result["value"] = sched.ask_minigame("slime_battle", {"hp": 30})

        t = threading.Thread(target=call, daemon=True)
        t.start()
        deadline = time.time() + 2
        while time.time() < deadline and not sched.is_waiting():
            time.sleep(0.02)
        assert sched.is_waiting()
        msg = [m for m in output.messages if m["type"] == "minigame.start"][-1]
        assert msg["payload"]["game_id"] == "slime_battle"
        assert msg["payload"]["options"] == {"hp": 30}
        sched.resolve_wait(msg["requestId"], result={"won": True, "score": 50})
        t.join(timeout=2)
        assert result["value"] == {"won": True, "score": 50}
        assert not sched.is_waiting()

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


    def test_data_list_characters_returns_lua_table(self, env):
        """data.list_characters() 必须返回真 Lua table：支持 # / ipairs / 1-based。

        若返回 Python list，Lua 侧是 userdata，# 会报
        "attempt to get length of a POBJECT value"，下标还是 0-based。
        """
        sandbox = env["sandbox"]
        assert sandbox.execute("return type(data.list_characters())") == "table"
        assert sandbox.execute("return #data.list_characters()") == 2  # reimu + marisa
        first = sandbox.execute("return data.list_characters()[1]")
        assert first in ("reimu", "marisa")
        # 注意：lupa 的 execute 不返回 IIFE（(function()...end)()）的值，用多行写法
        count = sandbox.execute(
            "local n = 0\n"
            "for _ in ipairs(data.list_characters()) do n = n + 1 end\n"
            "return n"
        )
        assert count == 2

    def test_data_modify_stat_is_delta(self, env):
        """modify_stat 是增量（与 set_stat 的绝对值语义相对）。"""
        api = env["api"]
        api._data_set_stat("player", "money", 100)
        assert api._data_modify_stat("player", "money", -30) == 70
        assert api._data_get_stat("player", "money") == 70
        assert api._data_modify_stat("player", "money", 5) == 75

    def test_data_modify_stat_relation_forwards(self, env):
        """modify_stat 对 relation 转发到 modify_relation。"""
        api, ctx = env["api"], env["ctx"]
        ctx.add_character("reimu", "灵梦")
        assert api._data_modify_stat("reimu", "relation", 15) == 15
        assert ctx.get_character_relation("reimu") == 15
        assert api._data_modify_stat("reimu", "relation", -5) == 10

    def test_data_modify_stat_unknown_target(self, env):
        api = env["api"]
        assert api._data_modify_stat("nobody", "hp", 5) == 0
        assert api._data_modify_stat("player", "relation", 5) == 0

    def test_event_emit_payload_from_lua(self, env):
        """event.emit 的 Lua table payload 必须透传到订阅者的 ctx.data。

        回归：_event_emit 曾用 isinstance(payload, dict) 判空，而 lupa 的
        LuaTable 不是 dict，导致 payload 恒被丢弃；Lua handler 访问
        ctx.data["score"] 时抛 KeyError，会中断整个剧本。
        """
        from engine.event_bus import EventContext

        sandbox, bus = env["sandbox"], env["bus"]
        received = []

        def handler(ctx: EventContext):
            received.append(dict(ctx.data))

        bus.subscribe("custom:probe", handler)
        sandbox.execute('event.emit("custom:probe", { score = 42, tag = "x" })')

        assert received, "订阅者未被调用"
        assert received[0]["score"] == 42
        assert received[0]["tag"] == "x"

    def test_event_emit_without_payload(self, env):
        """不带 payload 时 ctx.data 为空，不应报错。"""
        from engine.event_bus import EventContext

        api, bus = env["api"], env["bus"]
        received = []

        def handler(ctx: EventContext):
            received.append(dict(ctx.data))

        bus.subscribe("custom:noargs", handler)
        api._event_emit("custom:noargs")

        assert received == [{}]


# ══════════════════ 端到端：剧本加载 + 完整流程 ══════════════════
class TestHubButtons:
    """角色剧本声明 hub 按钮 → loader 收集。"""

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_loader_collects_hub_buttons(self):
        from engine.loader import ScenarioLoader

        bus = EventBus()
        loader = ScenarioLoader(LuaSandbox(), bus, SCRIPTS_DIR)
        loader.load_all()

        pairs = {(b.char, b.label) for b in loader.hub_buttons}
        assert ("reimu", "聊聊") in pairs
        assert ("reimu", "一起修行") in pairs
        assert ("marisa", "聊聊") in pairs

        training = [b for b in loader.hub_buttons if b.label == "一起修行"][0]
        assert training.event == "action:reimu_training"
        assert training.require_relation == 10
        assert training.order == 20

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_character_dialogue_event(self, env):
        """Hub 按钮落点：dialogue:reimu 触发灵梦的对话剧本。"""
        bus, output = env["bus"], env["output"]
        sched = env["scheduler"]

        t = threading.Thread(target=lambda: bus.emit("dialogue:reimu"), daemon=True)
        t.start()

        m = _wait_choice(output, "随便聊聊", timeout=5)
        assert m is not None, "角色对话剧本未触发"
        assert m["payload"]["options"] == ["随便聊聊", "帮忙做事", "告辞"]

        sched.resolve_wait(m["requestId"], choice_index=2)
        t.join(timeout=5)
        assert not t.is_alive()


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
        # env fixture 的 init_engine 已注册全部剧本，此处不能再 load_all()
        # （重复注册会让每个剧本执行两次，例如早晨问候会连弹两个选项）

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
        assert choice_msg["payload"]["options"] == [
            "去村里转转", "在神社帮忙", "去魔法森林探险", "帮灵梦清理异变",
        ]

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
        # env fixture 的 init_engine 已注册全部剧本，此处不能再 load_all()
        # （重复注册会让每个剧本执行两次，例如早晨问候会连弹两个选项）
        ctx.set_global_flag("story", "intro_completed", True)

        bus.emit("on_game_start")
        # 同步触发完成，不应有 ask_choice 消息
        assert not [m for m in output.messages if m["type"] == "ui.ask_choice"]

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_minigame_from_lua(self, env):
        """DSL 链路：Lua 调 minigame.start → 挂起 → 结果回传 → Lua 恢复拿到结果。"""
        sandbox, sched, output = env["sandbox"], env["scheduler"], env["output"]
        result = {}
        code = """
        local r = minigame.start("slime_battle", {hp = 30})
        return r.won
        """

        def run():
            result["value"] = sandbox.execute(code)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        deadline = time.time() + 3
        msg = None
        while time.time() < deadline:
            msgs = [m for m in output.messages if m["type"] == "minigame.start"]
            if msgs:
                msg = msgs[-1]
                break
            time.sleep(0.05)
        assert msg is not None, "Lua 未触发 minigame.start"
        assert msg["payload"]["game_id"] == "slime_battle"
        assert msg["payload"]["options"] == {"hp": 30}
        sched.resolve_wait(msg["requestId"], result={"won": True, "score": 50})
        t.join(timeout=3)
        assert result["value"] is True  # Lua 端 r.won == true

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_intro_exorcism_choice_plays_minigame(self, env):
        """序章第 4 选项：帮灵梦清理异变 → minigame.start → 结果回传 → 好感/金钱。"""
        bus, ctx, output = env["bus"], env["ctx"], env["output"]
        sched = env["scheduler"]
        # env fixture 的 init_engine 已注册全部剧本，此处不能再 load_all()
        # （重复注册会让每个剧本执行两次，例如早晨问候会连弹两个选项）

        t = threading.Thread(target=lambda: bus.emit("on_game_start"), daemon=True)
        t.start()
        deadline = time.time() + 8
        choice_msg = None
        while time.time() < deadline:
            msgs = [m for m in output.messages if m["type"] == "ui.ask_choice"]
            if msgs:
                choice_msg = msgs[-1]
                break
            time.sleep(0.05)
        assert choice_msg is not None

        # 选 4：帮灵梦清理异变
        sched.resolve_wait(choice_msg["requestId"], choice_index=4)

        # 等待 minigame.start 出现（脚本挂起等小游戏结果）
        deadline = time.time() + 5
        mg_msg = None
        while time.time() < deadline:
            msgs = [m for m in output.messages if m["type"] == "minigame.start"]
            if msgs:
                mg_msg = msgs[-1]
                break
            time.sleep(0.05)
        assert mg_msg is not None, "第 4 选项未触发小游戏"
        assert mg_msg["payload"]["game_id"] == "slime_battle"

        # 回传胜利结果 → 脚本继续 → 好感 +10
        sched.resolve_wait(mg_msg["requestId"], result={"won": True, "score": 25})
        t.join(timeout=5)
        assert not t.is_alive()
        assert ctx.get_global_flag("story", "first_choice") == "exorcism"
        assert ctx.get_character_relation("reimu") == 10
        assert ctx.get_player_stat("money") == 25

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_morning_call_daily_event(self, env):
        """早晨问候：每个角色各有剧本，day≥2 随机触发，当天最多一次。

        两个角色剧本各 50% 概率，所以单天可能都不触发 —— 循环多天直到触发。
        """
        bus, ctx, output = env["bus"], env["ctx"], env["output"]
        sched = env["scheduler"]

        ctx.set_global_flag("mushroom_test", "triggered", True)
        ctx.set_global_flag("demo", "minigame_done", True)

        handled = set()
        fired_opts = None
        fired_day = None

        for day in range(2, 16):                     # 概率上 15 天内几乎必然触发
            ctx.set_day(day)
            t = threading.Thread(target=lambda: bus.emit("on_day_begin"), daemon=True)
            t.start()
            deadline = time.time() + 3
            while time.time() < deadline and t.is_alive():
                for m in output.messages:
                    if m["type"] == "ui.ask_choice" and m["requestId"] not in handled:
                        handled.add(m["requestId"])
                        if fired_opts is None and m["payload"]["options"][0] == "起来了":
                            fired_opts = m["payload"]["options"]
                            fired_day = day
                        sched.resolve_wait(m["requestId"], choice_index=1)
                time.sleep(0.05)
            t.join(timeout=3)

            if fired_opts is not None:
                # 当天只播一次：同一天再 emit 不应再弹早晨选项
                before = len([x for x in output.messages if x["type"] == "ui.ask_choice"])
                bus.emit("on_day_begin")
                after = len([x for x in output.messages if x["type"] == "ui.ask_choice"])
                assert after == before, "同一天不应重复叫醒"
                break

        assert fired_opts is not None, "15 天内早晨问候一次都没触发"
        assert fired_opts == ["起来了", "再睡五分钟", "装作没听见"]
        assert fired_day >= 2

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_morning_event_skipped_when_already_done(self, env):
        """当天已有人叫醒（daily.morning_done = day）时，早晨剧本直接跳过。"""
        bus, ctx, output = env["bus"], env["ctx"], env["output"]

        ctx.set_day(4)
        ctx.set_global_flag("daily", "morning_done", 4)
        ctx.set_global_flag("mushroom_test", "triggered", True)
        ctx.set_global_flag("demo", "minigame_done", True)

        bus.emit("on_day_begin")
        assert [m for m in output.messages if m["type"] == "ui.ask_choice"] == []

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_coffee_shop_daily_event(self, env):
        """日常事件：day≥5 + 灵梦好感≥20 → on_day_begin 触发咖啡店 → 选项 → Flag。"""
        bus, ctx, output = env["bus"], env["ctx"], env["output"]
        sched = env["scheduler"]
        # env fixture 的 init_engine 已注册全部剧本，此处不能再 load_all()
        # （重复注册会让每个剧本执行两次，例如早晨问候会连弹两个选项）

        # 满足触发条件
        ctx.set_day(5)
        ctx.set_character_relation("reimu", 25)
        ctx.set_player_stat("money", 100)
        # 隔离干扰：早晨问候用当天占坑旗标跳过、蘑菇事件随机、小游戏会阻塞
        ctx.set_global_flag("daily", "morning_done", 5)
        ctx.set_global_flag("mushroom_test", "triggered", True)
        ctx.set_global_flag("demo", "minigame_done", True)

        t = threading.Thread(target=lambda: bus.emit("on_day_begin"), daemon=True)
        t.start()

        choice_msg = _wait_choice(output, "进去打招呼")
        assert choice_msg is not None, "咖啡店事件未触发"
        assert choice_msg["payload"]["options"] == ["进去打招呼", "假装没看见"]

        # 选 1：付钱 → 扣 30 元 + 好感 +5 + met_at_cafe flag
        sched.resolve_wait(choice_msg["requestId"], choice_index=1)
        t.join(timeout=5)
        assert not t.is_alive()
        assert ctx.get_global_flag("coffee_mod", "met_at_cafe") is True
        # 增量语义：25 + 5 = 30。
        # 旧实现误用 set_stat（设绝对值），会把好感直接覆写成 5、金钱设成 -30。
        assert ctx.get_character_relation("reimu") == 30
        assert ctx.get_player_stat("money") == 70

