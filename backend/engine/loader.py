"""Scenario 加载器 —— 扫描 Data/scenarios/ 递归注册剧本（对齐 v1 机制）。

每个 .lua 文件执行顶层代码（注册 Event.on 回调到事件总线），
剧情体在事件触发时由游戏线程执行。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from engine.sandbox import ScriptValidator

logger = logging.getLogger(__name__)


class ScenarioLoader:
    def __init__(self, sandbox: Any, event_bus: Any, scripts_dir: Path) -> None:
        self._sandbox = sandbox
        self._bus = event_bus
        self.scripts_dir = Path(scripts_dir)

    def load_all(self) -> List[str]:
        """扫描并注册全部剧本，返回成功注册的相对路径列表。"""
        if not self.scripts_dir.exists():
            logger.warning("剧本目录不存在: %s", self.scripts_dir)
            return []
        loaded: List[str] = []
        for path in sorted(self.scripts_dir.rglob("*.lua")):
            rel = str(path.relative_to(self.scripts_dir))
            try:
                code = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("读取剧本失败 %s: %s", rel, exc)
                continue
            ok, err = ScriptValidator.validate(code)
            if not ok:
                logger.warning("剧本被安全校验拒绝 %s: %s", rel, err)
                continue
            try:
                result = self._sandbox.execute(code)
            except Exception as exc:  # noqa: BLE001
                logger.warning("剧本注册失败 %s: %s", rel, exc)
                continue
            # 剧本返回表结构：{ on_event = "...", execute = function() ... end }
            if result is None:
                logger.warning("剧本未返回 table，跳过: %s", rel)
                continue
            try:
                on_event = result["on_event"]
                execute_fn = result["execute"]
            except (KeyError, TypeError):
                try:
                    on_event = result.on_event
                    execute_fn = result.execute
                except AttributeError:
                    logger.warning("剧本返回格式无效（缺少 on_event/execute）: %s", rel)
                    continue
            if not on_event or not execute_fn:
                logger.warning("剧本缺少 on_event/execute: %s", rel)
                continue
            self._bus.subscribe(str(on_event), execute_fn)
            loaded.append(rel)
            logger.info("[✓] 已注册剧本: %s → %s", rel, on_event)
        return loaded

    def list_scripts(self) -> List[str]:
        if not self.scripts_dir.exists():
            return []
        return [str(p.relative_to(self.scripts_dir)) for p in self.scripts_dir.rglob("*.lua")]
