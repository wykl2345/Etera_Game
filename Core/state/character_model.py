"""
角色数据模型 (character_model.py)

从 YAML 文件加载角色定义，创建角色模板。
为 game_context.py 提供角色初始化数据。

与设计文档对应：
- /data/characters/ 目录下的 YAML 文件定义角色
- 支持自定义属性和默认值
- 角色Flag命名空间隔离
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path
import yaml

logger = logging.getLogger(__name__)


@dataclass
class CharacterTemplate:
    """
    角色模板

    从 YAML 加载的角色定义，用于初始化 CharacterState。
    """
    id: str
    name: str
    title: str = ""                       # 称号（如"幻想乡的巫女"）
    description: str = ""                 # 角色简介
    age: int = 0
    gender: str = "unknown"

    # 基础属性
    base_stats: Dict[str, int] = field(default_factory=lambda: {
        "hp": 100,
        "max_hp": 100,
        "mp": 50,
        "max_mp": 50,
        "stamina": 100,
        "max_stamina": 100,
        "money": 0,
        "exp": 0,
        "level": 1,
    })

    # 初始好感度
    base_relation: int = 0

    # 初始位置
    base_location: str = ""

    # 标签（用于分类和检索）
    tags: List[str] = field(default_factory=list)

    # 默认Flag
    default_flags: Dict[str, Any] = field(default_factory=dict)

    # 角色事件列表
    events: List[str] = field(default_factory=list)


class CharacterModel:
    """
    角色数据模型

    从 YAML 文件加载角色定义，提供角色模板的管理功能。
    """

    def __init__(self, data_dir: Path = None):
        """
        初始化角色模型

        Args:
            data_dir: 角色数据目录（data/characters）
        """
        self._data_dir = data_dir or Path("data/characters")
        self._templates: Dict[str, CharacterTemplate] = {}
        logger.info(f"CharacterModel 初始化，数据目录: {self._data_dir}")

    def load_all(self) -> Dict[str, CharacterTemplate]:
        """
        加载所有角色定义

        Returns:
            Dict[str, CharacterTemplate]: 角色ID → 模板
        """
        if not self._data_dir.exists():
            logger.warning(f"角色数据目录不存在: {self._data_dir}")
            return {}

        yaml_files = list(self._data_dir.glob("*.yaml")) + list(self._data_dir.glob("*.yml"))
        for yaml_file in yaml_files:
            try:
                template = self._load_single(yaml_file)
                if template:
                    self._templates[template.id] = template
            except Exception as e:
                logger.error(f"加载角色文件失败 {yaml_file}: {e}")

        logger.info(f"已加载 {len(self._templates)} 个角色")
        return self._templates

    def load(self, char_id: str) -> Optional[CharacterTemplate]:
        """
        加载单个角色

        Args:
            char_id: 角色ID

        Returns:
            Optional[CharacterTemplate]: 角色模板
        """
        # 先查缓存
        if char_id in self._templates:
            return self._templates[char_id]

        # 从文件加载
        for ext in [".yaml", ".yml"]:
            path = self._data_dir / f"{char_id}{ext}"
            if path.exists():
                template = self._load_single(path)
                if template:
                    self._templates[char_id] = template
                    return template

        logger.warning(f"角色未找到: {char_id}")
        return None

    def _load_single(self, path: Path) -> Optional[CharacterTemplate]:
        """
        加载单个 YAML 文件

        Args:
            path: YAML 文件路径

        Returns:
            Optional[CharacterTemplate]: 角色模板
        """
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data or "id" not in data:
            logger.warning(f"角色文件格式无效: {path}")
            return None

        # 合并基础属性
        base_stats = dict(data.get("base_stats", {}))
        for key in ["hp", "max_hp", "mp", "max_mp", "stamina", "max_stamina"]:
            base_stats.setdefault(key, 100 if "max" not in key else 100)
        base_stats.setdefault("money", 0)
        base_stats.setdefault("exp", 0)
        base_stats.setdefault("level", 1)

        template = CharacterTemplate(
            id=data["id"],
            name=data.get("name", data["id"]),
            title=data.get("title", ""),
            description=data.get("description", ""),
            age=data.get("age", 0),
            gender=data.get("gender", "unknown"),
            base_stats=base_stats,
            base_relation=data.get("base_relation", 0),
            base_location=data.get("base_location", ""),
            tags=data.get("tags", []),
            default_flags=data.get("default_flags", {}),
            events=data.get("events", []),
        )

        logger.debug(f"角色模板加载: {template.id} ({template.name})")
        return template

    def apply_template(self, template: CharacterTemplate) -> Dict[str, Any]:
        """
        将模板转换为用于创建 CharacterState 的字典

        Args:
            template: 角色模板

        Returns:
            Dict: 可直接用于 CharacterState.from_dict 的数据
        """
        return {
            "id": template.id,
            "name": template.name,
            "stats": dict(template.base_stats),
            "flags": dict(template.default_flags),
            "relation": template.base_relation,
            "location": template.base_location,
        }

    def get_template(self, char_id: str) -> Optional[CharacterTemplate]:
        """获取角色模板"""
        return self._templates.get(char_id) or self.load(char_id)

    def list_characters(self) -> List[Dict[str, str]]:
        """列出所有已加载的角色"""
        return [
            {
                "id": t.id,
                "name": t.name,
                "title": t.title,
                "tags": ",".join(t.tags),
            }
            for t in self._templates.values()
        ]

    def search_by_tag(self, tag: str) -> List[CharacterTemplate]:
        """按标签搜索角色"""
        return [t for t in self._templates.values() if tag in t.tags]
