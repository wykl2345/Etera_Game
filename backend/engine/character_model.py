"""角色模板加载 —— 从 Data/characters/*.yaml 加载角色定义。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_STATS: Dict[str, int] = {
    "hp": 100, "max_hp": 100,
    "mp": 50, "max_mp": 50,
    "stamina": 100, "max_stamina": 100,
    "money": 0, "exp": 0, "level": 1,
}


@dataclass
class CharacterTemplate:
    id: str
    name: str
    title: str = ""
    description: str = ""
    age: int = 0
    gender: str = "unknown"
    base_stats: Dict[str, int] = field(default_factory=lambda: dict(_DEFAULT_STATS))
    base_relation: int = 0
    base_location: str = ""
    tags: List[str] = field(default_factory=list)
    default_flags: Dict[str, Any] = field(default_factory=dict)
    events: List[str] = field(default_factory=list)


class CharacterModel:
    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else Path("data/characters")
        self._cache: Dict[str, CharacterTemplate] = {}

    def load_all(self) -> Dict[str, CharacterTemplate]:
        result: Dict[str, CharacterTemplate] = {}
        if not self.data_dir.exists():
            logger.warning("角色目录不存在: %s", self.data_dir)
            return result
        for path in sorted(self.data_dir.glob("*.yaml")) + sorted(self.data_dir.glob("*.yml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or not data.get("id"):
                    logger.warning("跳过无效角色文件: %s", path.name)
                    continue
                template = self._parse(data)
                result[template.id] = template
                self._cache[template.id] = template
            except Exception as exc:  # noqa: BLE001 - 坏文件跳过
                logger.warning("角色文件解析失败 %s: %s", path.name, exc)
        return result

    def load(self, char_id: str) -> Optional[CharacterTemplate]:
        if char_id in self._cache:
            return self._cache[char_id]
        for ext in ("yaml", "yml"):
            path = self.data_dir / f"{char_id}.{ext}"
            if path.exists():
                try:
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
                    template = self._parse(data)
                    self._cache[template.id] = template
                    return template
                except Exception as exc:  # noqa: BLE001
                    logger.warning("角色文件解析失败 %s: %s", path.name, exc)
        return None

    def get_template(self, char_id: str) -> Optional[CharacterTemplate]:
        return self._cache.get(char_id) or self.load(char_id)

    def list_characters(self) -> List[Dict[str, Any]]:
        return [
            {"id": t.id, "name": t.name, "title": t.title, "tags": t.tags}
            for t in self.load_all().values()
        ]

    def search_by_tag(self, tag: str) -> List[CharacterTemplate]:
        return [t for t in self.load_all().values() if tag in t.tags]

    def apply_template(self, template: CharacterTemplate) -> Dict[str, Any]:
        """输出可直接 CharacterState.from_dict 的结构。"""
        stats = dict(_DEFAULT_STATS)
        stats.update({k: int(v) for k, v in template.base_stats.items()})
        return {
            "id": template.id,
            "name": template.name,
            "stats": stats,
            "flags": dict(template.default_flags),
            "relation": template.base_relation,
            "location": template.base_location,
        }

    # ── 内部 ──────────────────────────────────────────────────
    def _parse(self, data: Dict[str, Any]) -> CharacterTemplate:
        stats = dict(_DEFAULT_STATS)
        base_stats = data.get("base_stats") or data.get("stats")
        if isinstance(base_stats, dict):
            stats.update({k: int(v) for k, v in base_stats.items()})
        return CharacterTemplate(
            id=str(data["id"]),
            name=str(data.get("name", "")),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            age=int(data.get("age", 0)),
            gender=str(data.get("gender", "unknown")),
            base_stats=stats,
            base_relation=int(data.get("base_relation", data.get("relation", 0))),
            base_location=str(data.get("base_location", data.get("location", ""))),
            tags=list(data.get("tags", [])),
            default_flags=dict(data.get("default_flags", {})),
            events=list(data.get("events", [])),
        )
