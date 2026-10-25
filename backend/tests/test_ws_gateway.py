"""WS 网关集成测试：真实服务器 + 客户端完整链路。"""
import asyncio
import json
import threading
import time
from http.server import HTTPServer
from pathlib import Path

import pytest

from engine.sandbox import LUPA_AVAILABLE
from ws_gateway import handle_connection

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = ROOT / "Data" / "scenarios"
CHARACTERS_DIR = ROOT / "Data" / "characters"


async def _recv_until(ws, msg_type: str, timeout: float = 10.0) -> dict:
    """接收消息直到出现指定类型（忽略其他类型）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        msg = json.loads(raw)
        if msg.get("type") == msg_type:
            return msg
    raise TimeoutError(f"未在 {timeout}s 内收到 {msg_type}")


async def _collect(ws, seconds: float) -> list:
    """收集 seconds 秒内到达的所有消息。"""
    msgs = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=0.2)
            msgs.append(json.loads(raw))
        except asyncio.TimeoutError:
            continue
    return msgs


async def _run_full_flow() -> None:
    from websockets.asyncio.client import connect
    from websockets.asyncio.server import serve

    async def handler(ws):
        await handle_connection(ws, str(SCRIPTS_DIR), str(CHARACTERS_DIR))

    server = await serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    task = asyncio.create_task(server.serve_forever())
    try:
        async with connect(f"ws://127.0.0.1:{port}") as ws:
            # 1. 开始新游戏 → 序章启动
            await ws.send(json.dumps({"type": "game.start"}))
            choice = await _recv_until(ws, "ui.ask_choice")
            assert choice["payload"]["options"][0] == "去村里转转"
            assert "requestId" in choice

            # 2. 选择 1（去村里）→ 继续收到文本 + 完成
            await ws.send(json.dumps({
                "type": "choice.made",
                "requestId": choice["requestId"],
                "payload": {"index": 1},
            }))
            tail = await _collect(ws, 1.0)
            texts = [m["payload"]["text"] for m in tail if m["type"] == "ui.text"]
            assert any("市集" in t for t in texts), f"未收到选择分支文本: {texts}"
    finally:
        server.close()
        await server.wait_closed()
        task.cancel()


@pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
def test_full_flow_over_websocket():
    """真实 WS：game.start → 序章挂起 → choice.made → 分支文本。"""
    asyncio.run(_run_full_flow())


@pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
def test_restart_game_resets_state():
    """同一连接两次 game.start：第二次仍触发序章（状态必须重置）。"""

    async def _run():
        from websockets.asyncio.client import connect
        from websockets.asyncio.server import serve

        async def handler(ws):
            await handle_connection(ws, str(SCRIPTS_DIR), str(CHARACTERS_DIR))

        server = await serve(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        task = asyncio.create_task(server.serve_forever())
        try:
            async with connect(f"ws://127.0.0.1:{port}") as ws:
                # 第一次：完整跑完序章（intro_completed 置位）
                await ws.send(json.dumps({"type": "game.start"}))
                choice1 = await _recv_until(ws, "ui.ask_choice", timeout=8)
                await ws.send(json.dumps({
                    "type": "choice.made", "requestId": choice1["requestId"],
                    "payload": {"index": 1},
                }))
                await _collect(ws, 1.2)  # 等序章收尾

                # 第二次：必须再次触发序章（reset_game 清除了 flag）
                await ws.send(json.dumps({"type": "game.start"}))
                choice2 = await _recv_until(ws, "ui.ask_choice", timeout=8)
                assert choice2 is not None, "第二次 game.start 未触发序章（状态未重置）"
                assert choice2["payload"]["options"][0] == "去村里转转"
        finally:
            server.close()
            await server.wait_closed()
            task.cancel()

    asyncio.run(_run())


@pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
def test_abort_frees_game_thread():
    """挂起中返回主菜单（game.abort）→ 再次 game.start 必须能跑（executor 释放）。"""

    async def _run():
        from websockets.asyncio.client import connect
        from websockets.asyncio.server import serve

        async def handler(ws):
            await handle_connection(ws, str(SCRIPTS_DIR), str(CHARACTERS_DIR))

        server = await serve(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        task = asyncio.create_task(server.serve_forever())
        try:
            async with connect(f"ws://127.0.0.1:{port}") as ws:
                # 第一次 start → 序章挂起在 ask_choice
                await ws.send(json.dumps({"type": "game.start"}))
                choice = await _recv_until(ws, "ui.ask_choice", timeout=8)
                assert choice is not None

                # 挂起中 abort（模拟回主菜单）→ 释放游戏线程
                await ws.send(json.dumps({"type": "game.abort"}))
                await asyncio.sleep(0.3)

                # 再次 start → 必须能触发序章（未被旧任务卡死）
                await ws.send(json.dumps({"type": "game.start"}))
                choice2 = await _recv_until(ws, "ui.ask_choice", timeout=8)
                assert choice2 is not None, "abort 后 game.start 未触发（executor 被占用）"
        finally:
            server.close()
            await server.wait_closed()
            task.cancel()

    asyncio.run(_run())


@pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
def test_scene_registry_loads_from_data_dir(tmp_path, monkeypatch):
    """场景表必须能加载（回归：早期用相对路径 Data/config/scenes.yaml，
    生产工作目录是 backend/ → 找不到 → 移动列表为空、睡觉全灰）。"""
    from engine.bootstrap import init_engine
    from engine.script_runner import UIOutput

    class _O(UIOutput):
        def send(self, msg):
            pass

    # 模拟生产：把工作目录切到 backend/，仍应通过绝对路径正确加载
    backend_dir = Path(__file__).resolve().parent.parent
    monkeypatch.chdir(backend_dir)

    b = init_engine(
        _O(),
        scripts_dir=str(SCRIPTS_DIR),
        characters_dir=str(CHARACTERS_DIR),
        saves_dir=str(tmp_path),
    )
    assert len(b.scenes.all_ids()) >= 4, "场景表未加载"
    assert "home" in b.scenes.all_ids()

    # 玩家初始在 home，应该能走到相邻场景且可以睡觉
    assert b.ctx.get_location() == "home"
    assert [s.id for s in b.scenes.neighbors("home")], "相邻场景不应为空"
    assert b.scenes.can_sleep("home") is True


class TestRelationStage:
    """关系阶段换算（与 v1 设计文档的 7 阶段一致）。"""

    def test_stage_boundaries(self):
        from ws_gateway import _relation_stage

        assert _relation_stage(-80)["label"] == "敌视"
        assert _relation_stage(-20)["label"] == "疏远"
        assert _relation_stage(0)["label"] == "中立"
        assert _relation_stage(10)["label"] == "友人"
        assert _relation_stage(30)["label"] == "亲密"
        assert _relation_stage(60)["label"] == "恋爱"
        assert _relation_stage(95)["label"] == "伴侣"
        # 边界值
        assert _relation_stage(9)["label"] == "中立"
        assert _relation_stage(29)["label"] == "友人"
        assert _relation_stage(100)["label"] == "伴侣"


@pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
def test_characters_payload_has_meta(tmp_path):
    """characters.list 数据要带称号/标签/关系阶段/属性/Flag。"""
    from engine.bootstrap import init_engine
    from engine.script_runner import UIOutput
    from ws_gateway import _characters_payload

    class _O(UIOutput):
        def send(self, msg):
            pass

    b = init_engine(
        _O(), scripts_dir=str(SCRIPTS_DIR),
        characters_dir=str(CHARACTERS_DIR), saves_dir=str(tmp_path),
    )
    b.ctx.set_character_relation("reimu", 15)
    payload = _characters_payload(b)

    by_id = {c["char_id"]: c for c in payload["characters"]}
    reimu = by_id["reimu"]
    assert reimu["name"] == "博丽灵梦"
    assert reimu["title"] == "幻想乡的巫女"
    assert "shrine_maiden" in reimu["tags"]
    assert reimu["relation"] == 15
    assert reimu["relation_stage"]["label"] == "友人"
    assert reimu["relation_stage"]["key"] == "friendly"
    assert reimu["stats"]["max_hp"] == 120
    assert isinstance(reimu["flags"], dict)
    assert reimu["location"] == "hakurei_shrine"


class TestHubPayload:
    """Hub 数据组装：角色卡片 + 按钮条件可用性。"""

    def _bundle(self, tmp_path):
        from engine.bootstrap import init_engine
        from engine.script_runner import UIOutput

        class _O(UIOutput):
            def send(self, msg):
                pass

        return init_engine(
            _O(), scripts_dir=str(SCRIPTS_DIR),
            characters_dir=str(CHARACTERS_DIR), saves_dir=str(tmp_path),
        )

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_payload_hides_condition_unmet(self, tmp_path):
        """条件不满足（好感门槛/前置剧情）→ 按钮直接隐藏，不是变灰。"""
        from ws_gateway import _hub_payload

        b = self._bundle(tmp_path)
        b.ctx.set_location("hakurei_shrine")          # 与灵梦同场景
        b.ctx.set_character_relation("reimu", 0)      # < 门槛 10
        payload = _hub_payload(b)

        chars = {c["char_id"] for c in payload["characters"]}
        assert "reimu" in chars, "同场景角色应出现在卡片里"
        assert "marisa" not in chars, "不同场景的角色不该出现"

        events = [x["event"] for x in payload["buttons"]]
        assert "action:reimu_training" not in events, "好感不足应隐藏"

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_payload_unlocks_when_relation_enough(self, tmp_path):
        from ws_gateway import _hub_payload

        b = self._bundle(tmp_path)
        b.ctx.set_location("hakurei_shrine")
        b.ctx.set_character_relation("reimu", 20)     # ≥ 门槛 10
        payload = _hub_payload(b)
        training = [x for x in payload["buttons"] if x["label"] == "一起修行"][0]
        assert training["available"] is True
        assert training["reason"] is None

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_payload_greys_out_on_low_stamina(self, tmp_path):
        """体力不足 → 按钮保留但变灰（不是隐藏）。"""
        from ws_gateway import _hub_payload

        b = self._bundle(tmp_path)
        b.ctx.set_location("hakurei_shrine")
        b.ctx.set_character_relation("reimu", 20)
        b.ctx.set_player_stat("stamina", 5)           # < 修行消耗 20
        payload = _hub_payload(b)
        training = [x for x in payload["buttons"] if x["event"] == "action:reimu_training"][0]
        assert training["available"] is False
        assert "体力" in (training["reason"] or "")

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_payload_greys_out_on_daily_limit(self, tmp_path):
        """当天次数用完 → 变灰（不隐藏），跨天恢复。"""
        from ws_gateway import _hub_payload

        b = self._bundle(tmp_path)
        b.ctx.set_location("hakurei_shrine")
        b.ctx.set_day(3)
        # 直接写当天计数，模拟已用 3 次（聊聊上限 3）
        b.ctx.set_global_flag("_action", "dialogue:reimu:3", 3)
        payload = _hub_payload(b)
        dlg = [x for x in payload["buttons"] if x["event"] == "dialogue:reimu"][0]
        assert dlg["available"] is False
        assert "3/3" in (dlg["reason"] or "")

        # 换一天 → 计数按天隔离，自动恢复可用
        b.ctx.set_day(4)
        payload2 = _hub_payload(b)
        dlg2 = [x for x in payload2["buttons"] if x["event"] == "dialogue:reimu"][0]
        assert dlg2["available"] is True

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_scene_filters_characters(self, tmp_path):
        """Hub 只显示与玩家同场景的角色。"""
        from ws_gateway import _hub_payload

        b = self._bundle(tmp_path)
        b.ctx.set_location("magic_forest")            # 魔理沙所在地
        payload = _hub_payload(b)
        chars = {c["char_id"] for c in payload["characters"]}
        assert "marisa" in chars
        assert "reimu" not in chars

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_scene_info_has_neighbors_and_sleep(self, tmp_path):
        """Hub 返回场景信息；可达地点按「同区域 / 跨区域」区分。"""
        from ws_gateway import _hub_payload

        b = self._bundle(tmp_path)
        b.ctx.set_location("home")
        scene = _hub_payload(b)["scene"]
        assert scene["name"] == "自宅"
        assert scene["region_name"] == "人间之里"
        assert scene["can_sleep"] is True

        ids = {s["id"] for s in scene["adjacent"]}
        # 同区域：市集；相邻区域：神社 / 魔法森林
        assert ids == {"market", "hakurei_shrine", "magic_forest"}, ids

        same = {s["id"] for s in scene["adjacent"] if s["same_region"]}
        assert same == {"market"}, "只有市集属于同一区域"

        other = {s["id"] for s in scene["adjacent"] if not s["same_region"]}
        assert other == {"hakurei_shrine", "magic_forest"}

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_shop_only_in_scene_with_shop(self, tmp_path):
        """只有配置了 shop 的地点才暴露商店。"""
        from ws_gateway import _hub_payload

        b = self._bundle(tmp_path)

        b.ctx.set_location("home")
        assert _hub_payload(b)["scene"]["shop"] is None, "自宅没有商店"

        b.ctx.set_location("market")
        shop = _hub_payload(b)["scene"]["shop"]
        assert shop is not None
        assert shop["id"] == "village_market"
        assert shop["name"] == "人间之里的市集"


    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_payload_buttons_have_event_and_order(self, tmp_path):
        from ws_gateway import _hub_payload

        payload = _hub_payload(self._bundle(tmp_path))
        for btn in payload["buttons"]:
            assert btn["event"], "每个按钮都要有可触发的事件"
            assert isinstance(btn["order"], int)
            assert btn["char"] in {c["char_id"] for c in payload["characters"]}


class TestCatalog:
    """物品/商店目录：价格换算、送礼好感。"""

    def test_items_and_shop_loaded(self, tmp_path):
        from engine.bootstrap import init_engine
        from engine.script_runner import UIOutput

        class _O(UIOutput):
            def send(self, msg):
                pass

        b = init_engine(
            _O(), scripts_dir=str(SCRIPTS_DIR),
            characters_dir=str(CHARACTERS_DIR), saves_dir=str(tmp_path),
        )
        assert b.catalog.item("煎茶") is not None
        assert b.catalog.gift_value("煎茶") == 5
        goods = b.catalog.shop_goods("village_market")
        ids = {g["id"] for g in goods}
        assert {"煎茶", "团子"} <= ids
        assert all(g["price"] > 0 for g in goods)


class TestRegionTravel:
    """两级场景的移动规则：跨区只能落到对方区域的入口。"""

    def _registry(self):
        from engine.scenes import SceneRegistry

        return SceneRegistry(SCRIPTS_DIR.parent / "config" / "scenes.yaml")

    def test_same_region_any_scene(self):
        r = self._registry()
        assert r.can_travel_to("home", "market") is True
        assert r.can_travel_to("market", "home") is True

    def test_cross_region_only_entrance(self):
        r = self._registry()
        # 神社 → 人间之里：只允许落到入口 home
        assert r.can_travel_to("hakurei_shrine", "home") is True
        # 神社 → 市集（人间之里的非入口地点）不允许直穿
        assert r.can_travel_to("hakurei_shrine", "market") is False
        # 神社 → 魔法森林（对方入口）
        assert r.can_travel_to("hakurei_shrine", "magic_forest") is True

    def test_reachable_exposes_region_not_inner_scenes(self):
        r = self._registry()
        items = r.reachable("hakurei_shrine")
        names = {x["name"] for x in items}
        # 神社同区域没有其他地点；相邻区域各暴露一个入口
        assert "人间之里" in names
        assert "魔法森林" in names
        # 不该直接暴露「市集」这种区域内部地点
        assert "市集" not in names
        assert all(x["same_region"] is False for x in items)


class TestSellAndItemCatalog:
    """卖出回收价 + 物品 id 必须能被 Catalog 命中。"""

    def test_script_item_ids_are_defined(self):
        """剧本里 add_item 用的 id 都应该在 items.yaml 里有定义。

        回归：marisa_mushroom 用 glowing_mushroom，而 items.yaml 曾写成中文
        「发光蘑菇」→ 背包显示原始 id、送礼好感为 0。
        """
        from engine.catalog import Catalog

        catalog = Catalog(
            SCRIPTS_DIR.parent / "items" / "items.yaml",
            SCRIPTS_DIR.parent / "shops" / "shops.yaml",
        )
        # 剧本里出现过的物品 id
        assert catalog.item("glowing_mushroom") is not None, "glowing_mushroom 未定义"
        assert catalog.item("glowing_mushroom").name == "发光蘑菇"
        assert catalog.gift_value("glowing_mushroom") > 0

    def test_sell_ratio_applied(self):
        from engine.catalog import Catalog
        from ws_gateway import SELL_RATIO

        catalog = Catalog(
            SCRIPTS_DIR.parent / "items" / "items.yaml",
            SCRIPTS_DIR.parent / "shops" / "shops.yaml",
        )
        tea = catalog.item("煎茶")
        assert tea is not None
        assert int(tea.price * SELL_RATIO) == 15   # 30 × 0.5
        assert SELL_RATIO == 0.5


class TestTimeFlow:
    """行动消耗时段：morning → afternoon → evening → night，夜里不再推进。"""

    def test_spend_time_advances(self, tmp_path):
        from engine.bootstrap import init_engine
        from engine.script_runner import UIOutput
        from ws_gateway import _spend_time

        class _O(UIOutput):
            def send(self, msg):
                pass

        b = init_engine(
            _O(), scripts_dir=str(SCRIPTS_DIR),
            characters_dir=str(CHARACTERS_DIR), saves_dir=str(tmp_path),
        )
        assert b.ctx.get_time_of_day().value == "morning"
        assert _spend_time(b) == "afternoon"
        assert _spend_time(b) == "evening"
        assert _spend_time(b) == "night"
        # 夜里不再推进（由睡觉进下一天）
        assert _spend_time(b) == "night"
        assert b.ctx.get_time_of_day().value == "night"


class TestItemCategoryAndUse:
    """物品分类（item/equip/skill/key）+ 可使用物品效果。"""

    def _catalog(self):
        from engine.catalog import Catalog

        return Catalog(
            SCRIPTS_DIR.parent / "items" / "items.yaml",
            SCRIPTS_DIR.parent / "shops" / "shops.yaml",
        )

    def test_categories_loaded(self):
        c = self._catalog()
        assert c.item("煎茶").category == "item"
        assert c.item("木刀").category == "equip"
        assert c.item("灵符").category == "skill"
        assert c.item("御守").category == "key"
        assert c.item("御守").category_label == "重要物品"

    def test_usable_flags(self):
        c = self._catalog()
        assert c.item("煎茶").usable is True
        assert c.item("御守").usable is False
        assert c.item("木刀").usable is False

    def test_use_effects_defined(self):
        c = self._catalog()
        effs = c.item("glowing_mushroom").use_effects
        assert any(e.get("stat") == "stamina" and e.get("delta") == 6 for e in effs)
        # 概率副作用
        assert any(e.get("chance") is not None for e in effs)

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_use_item_applies_effect(self, tmp_path):
        """使用发光蘑菇：体力 +6（副作用按概率，可能不触发）。"""
        from engine.bootstrap import init_engine
        from engine.script_runner import UIOutput
        import engine.catalog as catalog_mod

        sent = []

        class _O(UIOutput):
            def send(self, msg):
                sent.append(msg)

        b = init_engine(
            _O(), scripts_dir=str(SCRIPTS_DIR),
            characters_dir=str(CHARACTERS_DIR), saves_dir=str(tmp_path),
        )
        b.ctx.set_player_stat("stamina", 50)
        b.ctx.add_item("glowing_mushroom", 1)

        # 直接调 Catalog 效果解析路径：通过 API 层模拟
        it = b.catalog.item("glowing_mushroom")
        for eff in it.use_effects:
            chance = float(eff.get("chance", 1.0))
            if chance < 1.0:
                continue          # 跳过概率项，只验确定项
            b.ctx.modify_player_stat(str(eff["stat"]), int(eff["delta"]))

        assert b.ctx.get_player_stat("stamina") == 56


class TestCG:
    """CG 特写指令。"""

    def test_cg_sends_event(self, tmp_path):
        from engine.api_bridge import LuaAPI
        from engine.event_bus import EventBus
        from engine.game_context import GameContext
        from engine.script_runner import UIOutput

        sent = []

        class _O(UIOutput):
            def send(self, msg):
                sent.append(msg)

            # scheduler 需要 output 属性
            output = None

        class _Sched:
            def __init__(self, out):
                self.output = out

        out = _O()
        api = LuaAPI(scheduler=_Sched(out), context=GameContext(), event_bus=EventBus())

        api._ui_cg("reimu_breakthrough")
        assert sent[-1]["type"] == "ui.cg"
        assert sent[-1]["payload"]["name"] == "reimu_breakthrough"

        api._ui_cg_off()
        assert sent[-1]["type"] == "ui.cg"
        assert sent[-1]["payload"]["name"] is None


class TestDialogueRecorder:
    """DialogueRecorder：只记录画面类消息，控制类不进快照；begin() 清空。"""

    def _mk(self):
        from engine.script_runner import UIOutput
        from ws_gateway import DialogueRecorder

        sent = []

        class _Inner(UIOutput):
            def send(self, msg):
                sent.append(msg)

        rec = DialogueRecorder(_Inner())
        return rec, sent

    def test_records_display_messages_only(self):
        rec, sent = self._mk()
        rec.send({"type": "ui.text", "payload": {"text": "hi"}})
        rec.send({"type": "ui.background_set", "payload": {"name": "cafe"}})
        rec.send({"type": "save.result", "payload": {"ok": True}})   # 控制类
        rec.send({"type": "status.sync", "payload": {"day": 1}})     # 状态推送

        snap = rec.snapshot()
        assert [e["type"] for e in snap] == ["ui.text", "ui.background_set"]
        # 所有消息都要照常转发给真实 output
        assert len(sent) == 4

    def test_begin_clears_snapshot(self):
        rec, _ = self._mk()
        rec.send({"type": "ui.text", "payload": {"text": "上一事件"}})
        assert len(rec.snapshot()) == 1
        rec.begin()
        assert rec.snapshot() == []

    def test_snapshot_is_copy(self):
        rec, _ = self._mk()
        rec.send({"type": "ui.text", "payload": {"text": "x"}})
        snap = rec.snapshot()
        snap.clear()
        assert len(rec.snapshot()) == 1, "快照应为副本，外部修改不影响内部"


@pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
def test_hub_clears_dialogue_snapshot(tmp_path):
    """进入 Hub（game.hub）后再存档，对话快照必须为空。

    回归：早期 recorder 从不清空，Hub 里存档会带上"上一个事件"的对话，
    读档时莫名重放旧剧情（例如在 Hub 存了档，读档却看到序章）。
    """

    async def _run():
        import json

        from websockets.asyncio.client import connect
        from websockets.asyncio.server import serve

        async def handler(ws):
            await handle_connection(
                ws, str(SCRIPTS_DIR), str(CHARACTERS_DIR), saves_dir=str(tmp_path)
            )

        server = await serve(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        task = asyncio.create_task(server.serve_forever())
        try:
            async with connect(f"ws://127.0.0.1:{port}") as ws:
                # 跑完序章（产生对话）
                await ws.send(json.dumps({"type": "game.start"}))
                choice = await _recv_until(ws, "ui.ask_choice", timeout=10)
                await ws.send(json.dumps({
                    "type": "choice.made", "requestId": choice["requestId"],
                    "payload": {"index": 1},
                }))
                await _collect(ws, 1.5)

                # 叙事界面直接存档 → 应带对话快照
                await ws.send(json.dumps({"type": "game.save", "payload": {"slot_id": 2}}))
                r1 = await _recv_until(ws, "save.result", timeout=5)
                assert r1["payload"]["ok"] is True

                await ws.send(json.dumps({"type": "game.load", "payload": {"slot_id": 2}}))
                l1 = await _recv_until(ws, "load.result", timeout=5)
                assert len(l1["payload"].get("dialogue") or []) > 0, \
                    "叙事界面存档应保留对话快照"

                # 进 Hub（前端会发 game.hub）→ 快照被清空
                await ws.send(json.dumps({"type": "game.hub"}))
                await _collect(ws, 0.5)

                await ws.send(json.dumps({"type": "game.save", "payload": {"slot_id": 3}}))
                r2 = await _recv_until(ws, "save.result", timeout=5)
                assert r2["payload"]["ok"] is True

                await ws.send(json.dumps({"type": "game.load", "payload": {"slot_id": 3}}))
                l2 = await _recv_until(ws, "load.result", timeout=5)
                assert (l2["payload"].get("dialogue") or []) == [], \
                    "Hub 存档不该带对话快照（否则读档会重放旧剧情）"
        finally:
            server.close()
            await server.wait_closed()
            task.cancel()

    asyncio.run(_run())


class TestPersistBlocked:
    """存读档忙状态判定（对话/选项进行中禁止存读档）。"""

    def test_allows_when_idle(self):
        from ws_gateway import _persist_blocked

        class _Sched:
            def is_waiting(self):
                return False

        class _Bundle:
            scheduler = _Sched()

        assert _persist_blocked(_Bundle()) is None

    def test_blocks_when_waiting(self):
        from ws_gateway import _persist_blocked

        class _Sched:
            def is_waiting(self):
                return True

        class _Bundle:
            scheduler = _Sched()

        reason = _persist_blocked(_Bundle())
        assert reason is not None
        assert "对话进行中" in reason


@pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
def test_save_rejected_while_waiting_choice(tmp_path):
    """序章挂起在选项时存档 → 必须被拒（此时存档只含数据，会存出半截画面）。"""

    async def _run():
        from websockets.asyncio.client import connect
        from websockets.asyncio.server import serve

        async def handler(ws):
            await handle_connection(
                ws, str(SCRIPTS_DIR), str(CHARACTERS_DIR), saves_dir=str(tmp_path)
            )

        server = await serve(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        task = asyncio.create_task(server.serve_forever())
        try:
            async with connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(json.dumps({"type": "game.start"}))
                choice = await _recv_until(ws, "ui.ask_choice", timeout=8)
                assert choice is not None

                # 对话进行中存档 → 拒绝并给出原因
                await ws.send(json.dumps({"type": "game.save", "payload": {"slot_id": 3}}))
                res = await _recv_until(ws, "save.result", timeout=5)
                assert res["payload"]["ok"] is False
                assert "对话进行中" in (res["payload"].get("reason") or "")

                # 快存同样被拒
                await ws.send(json.dumps({"type": "game.quick_save"}))
                res2 = await _recv_until(ws, "save.result", timeout=5)
                assert res2["payload"]["ok"] is False

                # 确认没有真的写出存档文件
                assert not list(tmp_path.glob("*.json"))

                # 完成序章后（脚本空闲）存档应成功
                await ws.send(json.dumps({
                    "type": "choice.made",
                    "requestId": choice["requestId"],
                    "payload": {"index": 1},
                }))
                await _collect(ws, 1.5)
                await ws.send(json.dumps({"type": "game.save", "payload": {"slot_id": 3}}))
                deadline_ok = False
                for _ in range(40):
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    got = json.loads(msg)
                    if got.get("type") == "save.result":
                        deadline_ok = bool(got["payload"]["ok"])
                        break
                assert deadline_ok, "空闲时存档应成功"
        finally:
            server.close()
            await server.wait_closed()
            task.cancel()

    asyncio.run(_run())


@pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
def test_emit_event_runs_selftest_scenario(tmp_path):
    """game.emit_event → custom:run_selftest → 剧本主动跑起来（不再靠 on_game_start 强插）。"""

    async def _run():
        from websockets.asyncio.client import connect
        from websockets.asyncio.server import serve

        async def handler(ws):
            await handle_connection(
                ws, str(SCRIPTS_DIR), str(CHARACTERS_DIR), saves_dir=str(tmp_path)
            )

        server = await serve(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        task = asyncio.create_task(server.serve_forever())
        try:
            async with connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(json.dumps({"type": "game.start"}))
                choice = await _recv_until(ws, "ui.ask_choice", timeout=8)

                # 对话进行中触发 → 被拒
                await ws.send(json.dumps({
                    "type": "game.emit_event",
                    "payload": {"event": "custom:run_selftest"},
                }))
                rejected = await _recv_until(ws, "event.result", timeout=5)
                assert rejected["payload"]["ok"] is False

                # 结束序章 → 空闲后触发 → 成功
                await ws.send(json.dumps({
                    "type": "choice.made",
                    "requestId": choice["requestId"],
                    "payload": {"index": 1},
                }))
                await _collect(ws, 1.5)

                await ws.send(json.dumps({
                    "type": "game.emit_event",
                    "payload": {"event": "custom:run_selftest"},
                }))
                ok = await _recv_until(ws, "event.result", timeout=5)
                assert ok["payload"]["ok"] is True

                # 剧本先弹前置选择（要不要检查修行成果），选 1 才进入自检
                gate = await _recv_until(ws, "ui.ask_choice", timeout=8)
                assert gate["payload"]["options"][0] == "帮我检查一下修行成果"
                await ws.send(json.dumps({
                    "type": "choice.made",
                    "requestId": gate["requestId"],
                    "payload": {"index": 1},
                }))

                # 应答后剧本才真正开始输出自检标题
                collected = await _collect(ws, 2.5)
                texts = [m["payload"]["text"] for m in collected if m.get("type") == "ui.text"]
                assert any("修行成果检验" in t for t in texts), f"未收到自检标题: {texts[:8]}"
        finally:
            server.close()
            await server.wait_closed()
            task.cancel()

    asyncio.run(_run())


def test_static_server_404_on_empty_dir(tmp_path):
    """静态资源服务：空目录请求返回 404（不崩溃）。"""
    from main import start_static_server

    server = start_static_server(tmp_path, 0)
    port = server.server_address[1]
    try:
        import urllib.request

        with pytest.raises(Exception) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/missing.png", timeout=5)
        assert exc_info.value.code == 404
    finally:
        server.shutdown()
