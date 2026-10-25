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
        """Hub 返回当前场景的名称/描述/相邻地点/能否睡觉。"""
        from ws_gateway import _hub_payload

        b = self._bundle(tmp_path)
        b.ctx.set_location("home")
        scene = _hub_payload(b)["scene"]
        assert scene["name"] == "自宅"
        assert scene["can_sleep"] is True
        assert {s["id"] for s in scene["adjacent"]} >= {"hakurei_shrine", "village"}

    @pytest.mark.skipif(not LUPA_AVAILABLE, reason="lupa 不可用")
    def test_payload_buttons_have_event_and_order(self, tmp_path):
        from ws_gateway import _hub_payload

        payload = _hub_payload(self._bundle(tmp_path))
        for btn in payload["buttons"]:
            assert btn["event"], "每个按钮都要有可触发的事件"
            assert isinstance(btn["order"], int)
            assert btn["char"] in {c["char_id"] for c in payload["characters"]}


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
