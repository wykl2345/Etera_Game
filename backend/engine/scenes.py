"""场景登记：从 Data/config/scenes.yaml 加载地点与相邻关系。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Scene:
    id: str
    name: str
    desc: str = ""
    adjacent: List[str] = field(default_factory=list)
    can_sleep: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "desc": self.desc,
            "can_sleep": self.can_sleep,
        }


class SceneRegistry:
    """场景表。相邻关系会被补成双向（一处声明即可互相通行）。"""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._scenes: Dict[str, Scene] = {}
        self.config_path = Path(config_path) if config_path else Path("Data/config/scenes.yaml")
        self.load()

    def load(self) -> int:
        if not self.config_path.exists():
            logger.error(
                "场景配置不存在: %s —— 移动列表将为空（睡觉降级为不限制）。"
                "请检查 Data/config/scenes.yaml 是否随项目一起部署。",
                self.config_path.resolve(),
            )
            return 0
        try:
            import yaml

            raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            logger.error("场景配置解析失败 %s: %s", self.config_path, exc)
            return 0

        scenes_raw = raw.get("scenes") or {}
        if not isinstance(scenes_raw, dict):
            logger.error("场景配置格式错误：scenes 应为字典")
            return 0

        for sid, spec in scenes_raw.items():
            spec = spec or {}
            self._scenes[str(sid)] = Scene(
                id=str(sid),
                name=str(spec.get("name", sid)),
                desc=str(spec.get("desc", "")),
                adjacent=[str(x) for x in (spec.get("adjacent") or [])],
                can_sleep=bool(spec.get("sleep", False)),
            )

        # 相邻关系补双向，避免内容作者两边都写
        for scene in list(self._scenes.values()):
            for other in scene.adjacent:
                target = self._scenes.get(other)
                if target is not None and scene.id not in target.adjacent:
                    target.adjacent.append(scene.id)

        logger.info("场景已加载: %s", list(self._scenes.keys()))
        return len(self._scenes)

    # ── 查询 ──────────────────────────────────────────────────
    def get(self, scene_id: str) -> Optional[Scene]:
        return self._scenes.get(scene_id)

    def exists(self, scene_id: str) -> bool:
        return scene_id in self._scenes

    def name_of(self, scene_id: str) -> str:
        scene = self._scenes.get(scene_id)
        return scene.name if scene else (scene_id or "未知地点")

    def neighbors(self, scene_id: str) -> List[Scene]:
        scene = self._scenes.get(scene_id)
        if not scene:
            return []
        return [self._scenes[s] for s in scene.adjacent if s in self._scenes]

    def can_sleep(self, scene_id: str) -> bool:
        # 场景表没加载成功时降级为"不限制"，避免睡觉功能被配置问题锁死
        if not self._scenes:
            return True
        scene = self._scenes.get(scene_id)
        return bool(scene and scene.can_sleep)

    def all_ids(self) -> List[str]:
        return list(self._scenes.keys())
