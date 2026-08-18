"""Etera_Game 后端入口 —— WS 网关 + 静态资源服务。

用法:
    python backend/main.py                  # 默认 127.0.0.1:8765 (WS) + :8766 (静态)
    python backend/main.py --port 9000 --debug
"""
from __future__ import annotations

import argparse
import functools
import logging
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from ws_gateway import serve

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def start_static_server(resources_dir: Path, port: int) -> HTTPServer:
    """标准库静态文件服务（resources/ 经 HTTP 提供给前端）。"""

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(resources_dir), **kwargs)

        def log_message(self, fmt: str, *args: object) -> None:  # 静默访问日志
            logger.debug("static: " + fmt, *args)

    server = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Etera_Game 后端服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket 端口")
    parser.add_argument("--static-port", type=int, default=8766, help="静态资源端口")
    parser.add_argument("--scripts-dir", default="data/scenarios")
    parser.add_argument("--characters-dir", default="data/characters")
    parser.add_argument("--resources-dir", default="resources")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    resources_dir = root / args.resources_dir
    resources_dir.mkdir(parents=True, exist_ok=True)
    static = start_static_server(resources_dir, args.static_port)
    logger.info("静态资源服务: http://127.0.0.1:%s (目录 %s)", args.static_port, resources_dir)

    import asyncio

    try:
        asyncio.run(serve(
            host=args.host, port=args.port,
            scripts_dir=str(root / args.scripts_dir),
            characters_dir=str(root / args.characters_dir),
            debug_mode=args.debug,
        ))
    except KeyboardInterrupt:
        logger.info("服务停止")
    finally:
        static.shutdown()


if __name__ == "__main__":
    main()
