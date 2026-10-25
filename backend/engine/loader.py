"""Scenario 加载器 —— 扫描 Data/scenarios/ 递归注册剧本（对齐 v1 机制）。

每个 .lua 文件执行顶层代码（注册 Event.on 回调到事件总线），
剧情体在事件触发时由游戏线程执行。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.event_bus import EventPriority
from engine.sandbox import ScriptValidator

logger = logging.getLogger(__name__)


@dataclass
class HubButton:
    """剧本在 Hub（行动枢纽）上注册的入口按钮。

    剧本返回表声明：
        hub = {
            char = "reimu",                      -- 归属角色（决定显示在哪张角色卡下）
            label = "聊聊",                       -- 按钮文案
            order = 10,                          -- 排序（小在前，默认 100）
            require_flag = "story.intro_completed",  -- 可选：需要某 flag（"ns.key"）
            require_relation = 10,               -- 可选：需要该角色好感 ≥ N
        }
    event 由剧本的 on_event 决定（点按钮即 emit 该事件）。
    """

    char: str
    label: str
    event: str
    order: int = 100
    source: str = ""
    require_flag: Optional[str] = None
    require_relation: Optional[int] = None
    # 该 flag 为真时按钮直接隐藏（一次性剧情用：做完就不再显示入口）
    hide_flag: Optional[str] = None
    # 消耗体力：不足则按钮变灰；执行后由引擎扣除（剧本不必再扣）
    stamina_cost: int = 0
    # 每天可用次数上限（0 = 不限）；用完变灰，跨天自动重置
    daily_limit: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "char": self.char,
            "label": self.label,
            "event": self.event,
            "order": self.order,
            "require_flag": self.require_flag,
            "require_relation": self.require_relation,
            "hide_flag": self.hide_flag,
            "stamina_cost": self.stamina_cost,
            "daily_limit": self.daily_limit,
        }


class ScenarioLoader:
    def __init__(self, sandbox: Any, event_bus: Any, scripts_dir: Path) -> None:
        self._sandbox = sandbox
        self._bus = event_bus
        self.scripts_dir = Path(scripts_dir)
        # 剧本注册的 Hub 按钮（按 order 排序后供前端使用）
        self.hub_buttons: List[HubButton] = []

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
            priority = self._read_priority(result, rel)
            self._bus.subscribe(str(on_event), execute_fn, priority=priority)

            hub = self._read_hub(result, str(on_event), rel)
            if hub is not None:
                self.hub_buttons.append(hub)
                logger.info("  Hub 按钮: [%s] %s → %s", hub.char, hub.label, hub.event)
            loaded.append(rel)
            logger.info("[✓] 已注册剧本: %s → %s", rel, on_event)
        return loaded

    @staticmethod
    def _read_priority(result: Any, rel: str) -> EventPriority:
        """读取剧本可选的 priority 字段（low/normal/high/critical）。

        同一事件有多个剧本时按优先级降序执行，同优先级保持注册（文件名）顺序。
        用途：早晨问候这类"每天开场"的剧本要排在随机事件之前。
        """
        raw = None
        try:
            raw = result["priority"]
        except (KeyError, TypeError):
            raw = getattr(result, "priority", None)
        if not raw:
            return EventPriority.NORMAL
        name = str(raw).strip().lower()
        mapping = {
            "low": EventPriority.LOW,
            "normal": EventPriority.NORMAL,
            "high": EventPriority.HIGH,
            "critical": EventPriority.CRITICAL,
        }
        if name not in mapping:
            logger.warning("剧本 priority 非法（%s）: %s，按 normal 处理", name, rel)
            return EventPriority.NORMAL
        return mapping[name]

    @staticmethod
    def _hub_get(hub: Any, key: str, default: Any = None) -> Any:
        """从 Lua table / dict 读字段（lupa 两种访问都支持，按需回退）。"""
        try:
            value = hub[key]
            if value is not None:
                return value
        except (KeyError, TypeError, IndexError):
            pass
        return getattr(hub, key, default)

    def _read_hub(self, result: Any, on_event: str, rel: str) -> Optional[HubButton]:
        """读取剧本可选的 hub 字段；未声明则返回 None。"""
        try:
            hub = result["hub"]
        except (KeyError, TypeError):
            hub = getattr(result, "hub", None)
        if not hub:
            return None

        char = self._hub_get(hub, "char")
        label = self._hub_get(hub, "label")
        if not char or not label:
            logger.warning("剧本 hub 声明缺少 char/label: %s", rel)
            return None

        order = self._hub_get(hub, "order", 100)
        try:
            order = int(order)
        except (TypeError, ValueError):
            order = 100

        hide_flag = self._hub_get(hub, "hide_flag")

        def _int_field(key: str) -> int:
            raw = self._hub_get(hub, key, 0)
            try:
                return max(0, int(raw or 0))
            except (TypeError, ValueError):
                return 0

        stamina_cost = _int_field("stamina_cost")
        daily_limit = _int_field("daily_limit")
        require_flag = self._hub_get(hub, "require_flag")
        require_relation = self._hub_get(hub, "require_relation")
        try:
            require_relation = (
                int(require_relation) if require_relation is not None else None
            )
        except (TypeError, ValueError):
            require_relation = None

        return HubButton(
            char=str(char),
            label=str(label),
            event=on_event,
            order=order,
            source=rel,
            require_flag=str(require_flag) if require_flag else None,
            require_relation=require_relation,
            hide_flag=str(hide_flag) if hide_flag else None,
            stamina_cost=stamina_cost,
            daily_limit=daily_limit,
        )

    def list_scripts(self) -> List[str]:
        if not self.scripts_dir.exists():
            return []
        return [str(p.relative_to(self.scripts_dir)) for p in self.scripts_dir.rglob("*.lua")]
