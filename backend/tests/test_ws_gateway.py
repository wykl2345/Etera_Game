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

                # 剧本应真的开始输出自检标题
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
