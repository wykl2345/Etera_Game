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
