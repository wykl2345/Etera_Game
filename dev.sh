#!/usr/bin/env bash
# Etera_Game 一键启动开发环境（后端 WS + 前端 Vite）
# 用法: ./dev.sh        （Ctrl+C 停止全部）
set -e
cd "$(dirname "$0")"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "正在停止服务…"
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

# 后端
(cd backend && ../.venv/bin/python main.py) &
BACKEND_PID=$!

# 前端（需 PATH 含 node：已写入 ~/.bashrc）
(cd frontend && source ~/.bashrc && npm run dev) &
FRONTEND_PID=$!

echo "════════════════════════════════════════"
echo "  Etera_Game 开发环境已启动"
echo "  前端:  http://127.0.0.1:5173"
echo "  后端:  ws://127.0.0.1:8765 (静态 :8766)"
echo "  按 Ctrl+C 停止"
echo "════════════════════════════════════════"

wait
