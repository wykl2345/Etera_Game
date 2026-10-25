"""DSL 全指令自检执行器。

用内存 output 驱动 tools/scenarios/dsl_selftest.lua，收集全部 UI 消息并汇总
[OK]/[NG] 结果，最后核对游戏状态是否被剧本恢复原值。

用法（在项目根执行）：
    .venv/bin/python tools/run_dsl_selftest.py

场景目录固定为 tools/scenarios（只含自检剧本），因此不会加载 Data/scenarios
下的正式剧本，序章等剧情不会干扰输出。
"""
from __future__ import annotations

import logging
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from engine.bootstrap import init_engine  # noqa: E402
from engine.script_runner import UIOutput  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"
CHARACTERS_DIR = ROOT / "Data" / "characters"
BLOCKING = ("ui.ask_choice", "ui.ask_input", "minigame.start")

# 自动应答：选择第 2 项、输入「测试者」
AUTO_CHOICE = 2
AUTO_INPUT = "测试者"


class Collect(UIOutput):
    """线程安全的输出收集器，同时记录阻塞请求。"""

    def __init__(self) -> None:
        self.msgs = []
        self.blocking = []
        self.lock = threading.Lock()

    def send(self, msg):
        with self.lock:
            self.msgs.append(msg)
            if msg.get("type") in BLOCKING:
                self.blocking.append(msg)


def _snapshot(ctx) -> dict:
    return {
        "day": ctx.get_day(),
        "time": ctx.get_time_of_day().value,
        "location": ctx.get_location(),
        "money": ctx.get_player_stat("money"),
        "hp": ctx.get_player_stat("hp"),
        "reimu_relation": ctx.get_character_relation("reimu"),
        "marisa_relation": ctx.get_character_relation("marisa"),
        "selftest_item": ctx.get_item_count("selftest_item"),
    }


def main() -> int:
    out = Collect()
    bundle = init_engine(
        output=out,
        scripts_dir=str(SCENARIOS_DIR),
        characters_dir=str(CHARACTERS_DIR),
        saves_dir=tempfile.mkdtemp(prefix="selftest-saves-"),
    )
    ctx = bundle.ctx
    before = _snapshot(ctx)

    errors = []

    def run() -> None:
        try:
            bundle.bus.emit("on_game_start")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=run, daemon=True)
    t.start()

    interactions = []
    deadline = time.time() + 60
    while t.is_alive() and time.time() < deadline:
        with out.lock:
            pending = list(out.blocking)
            out.blocking.clear()
        for msg in pending:
            kind, rid = msg["type"], msg["requestId"]
            if kind == "ui.ask_choice":
                interactions.append(("choice", AUTO_CHOICE))
                bundle.scheduler.resolve_wait(rid, choice_index=AUTO_CHOICE)
            elif kind == "ui.ask_input":
                interactions.append(("input", AUTO_INPUT))
                bundle.scheduler.resolve_wait(rid, input_text=AUTO_INPUT)
            else:
                interactions.append(("minigame", "won"))
                bundle.scheduler.resolve_wait(rid, result={"won": True, "score": 10})
        time.sleep(0.02)
    t.join(timeout=5)

    # ── 输出 ──
    print("=" * 72)
    print(f"消息 {len(out.msgs)} 条 | 交互 {len(interactions)} 次 | 脚本结束={not t.is_alive()}")
    print("=" * 72)
    for m in out.msgs:
        kind = m.get("type")
        payload = m.get("payload") or {}
        if kind == "ui.text":
            color = payload.get("color") or "-"
            print(f"text[{color:>6}] {payload.get('text')}")
        elif kind == "ui.clear":
            print("---- ui.clear ----")
        elif kind == "status.sync":
            continue  # 状态推送噪音，跳过
        else:
            print(f"[{kind}] {payload}")

    # ── 汇总 ──
    ok_n = sum(1 for m in out.msgs
               if m.get("type") == "ui.text" and "[OK]" in (m.get("payload") or {}).get("text", ""))
    ng_n = sum(1 for m in out.msgs
               if m.get("type") == "ui.text" and "[NG]" in (m.get("payload") or {}).get("text", ""))

    print("=" * 72)
    print(f"[OK] {ok_n} 项 | [NG] {ng_n} 项")

    if errors:
        print(f"!! 脚本异常: {errors[0]!r}")
    if t.is_alive():
        print("!! 脚本超时未结束（可能仍在阻塞等待）")

    after = _snapshot(ctx)
    print("状态恢复核对:")
    restore_ok = True
    for key, old in before.items():
        new = after[key]
        mark = "OK  " if old == new else "DIFF"
        if old != new:
            restore_ok = False
        print(f"  [{mark}] {key}: {old} -> {new}")
    print(f"selftest.done = {ctx.get_global_flag('selftest', 'done', None)}")

    success = (ng_n == 0) and not errors and not t.is_alive() and restore_ok
    print("=" * 72)
    print("结论:", "全部通过" if success else "存在失败项")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
