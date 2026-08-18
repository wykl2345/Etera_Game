#!/usr/bin/env bash
# 停止 Etera_Game 开发服务（按端口识别，避免误杀其他项目）
# 前端 vite :5173 | 后端 main.py :8765 (WS) / :8766 (静态)

set -u

echo "═══ 停止 Etera_Game 开发服务 ═══"

killed=0
if command -v fuser >/dev/null 2>&1; then
  # fuser -k 按端口精确杀进程；无进程时返回非零
  if fuser -k 5173/tcp 8765/tcp 8766/tcp 2>/dev/null; then
    killed=1
  fi
else
  # 兜底：按命令行特征匹配
  for pat in "vite" "main.py"; do
    if pkill -f "$pat" 2>/dev/null; then killed=1; fi
  done
fi

if [ "$killed" -eq 1 ]; then
  echo "[✓] 已停止前端与后端服务"
else
  echo "[-] 没有发现运行中的服务"
fi

echo "（dev.sh 前台窗口此时应已退出，可关闭）"
