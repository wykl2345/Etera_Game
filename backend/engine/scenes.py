"""场景登记（两级：区域 region → 地点 scene）。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Region:
    id: str
    name: str
    adjacent: List[str] = field(default_factory=list)
    # 从其他区域进来时落在哪个地点（未设置则取该区域第一个地点）
    entrance: str = ""


@dataclass
class Scene:
    id: str
    name: str
    region: str = ""
    desc: str = ""
    can_sleep: bool = False
    shop: str = ""
    background: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "region": self.region,
            "desc": self.desc,
            "can_sleep": self.can_sleep,
            "shop": self.shop,
            "background": self.background,
        }


class SceneRegistry:
    """区域 + 地点两级结构。

    移动可达规则：
      ① 同区域内的其他地点
      ② 相邻区域内的所有地点
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._scenes: Dict[str, Scene] = {}
        self._regions: Dict[str, Region] = {}
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

        # ── 区域 ──
        regions_raw = raw.get("regions") or {}
        for rid, spec in (regions_raw.items() if isinstance(regions_raw, dict) else []):
            spec = spec or {}
            self._regions[str(rid)] = Region(
                id=str(rid),
                name=str(spec.get("name", rid)),
                adjacent=[str(x) for x in (spec.get("adjacent") or [])],
                entrance=str(spec.get("entrance", "") or ""),
            )
        # 相邻区域补双向
        for region in list(self._regions.values()):
            for other in region.adjacent:
                target = self._regions.get(other)
                if target is not None and region.id not in target.adjacent:
                    target.adjacent.append(region.id)

        # ── 地点 ──
        scenes_raw = raw.get("scenes") or {}
        if not isinstance(scenes_raw, dict):
            logger.error("场景配置格式错误：scenes 应为字典")
            return 0
        for sid, spec in scenes_raw.items():
            spec = spec or {}
            region_id = str(spec.get("region", ""))
            # 没写 region 时，视为自成区域（兼容旧配置）
            if region_id and region_id not in self._regions:
                self._regions[region_id] = Region(id=region_id, name=region_id)
            self._scenes[str(sid)] = Scene(
                id=str(sid),
                name=str(spec.get("name", sid)),
                region=region_id,
                desc=str(spec.get("desc", "")),
                can_sleep=bool(spec.get("sleep", False)),
                shop=str(spec.get("shop", "") or ""),
                background=str(spec.get("background", "") or ""),
            )

        logger.info(
            "场景已加载: %d 个区域 / %d 个地点 (%s)",
            len(self._regions), len(self._scenes), list(self._scenes.keys()),
        )
        return len(self._scenes)

    # ── 查询 ──────────────────────────────────────────────────
    def get(self, scene_id: str) -> Optional[Scene]:
        return self._scenes.get(scene_id)

    def exists(self, scene_id: str) -> bool:
        return scene_id in self._scenes

    def name_of(self, scene_id: str) -> str:
        scene = self._scenes.get(scene_id)
        return scene.name if scene else (scene_id or "未知地点")

    def region_name(self, region_id: str) -> str:
        region = self._regions.get(region_id)
        return region.name if region else region_id

    def can_sleep(self, scene_id: str) -> bool:
        # 场景表没加载成功时降级为"不限制"，避免睡觉功能被配置问题锁死
        if not self._scenes:
            return True
        scene = self._scenes.get(scene_id)
        return bool(scene and scene.can_sleep)

    def shop_of(self, scene_id: str) -> str:
        scene = self._scenes.get(scene_id)
        return scene.shop if scene else ""

    def background_of(self, scene_id: str) -> str:
        """场景对应的背景 id；未配置时回退为场景 id（缺图时前端显示占位）。"""
        scene = self._scenes.get(scene_id)
        if scene is None:
            return ""
        return scene.background or scene.id

    def reachable(self, scene_id: str) -> List[Dict[str, Any]]:
        """可达地点：同区域其他地点 + 相邻区域的地點。

        返回项带 same_region 标记，前端据此分组显示「本区域内 / 前往其他区域」。
        """
        current = self._scenes.get(scene_id)
        if current is None:
            return []

        out: List[Dict[str, Any]] = []
        seen = {scene_id}

        # ① 同区域
        for s in self._scenes.values():
            if s.id == scene_id or s.region != current.region:
                continue
            d = s.to_dict()
            d["same_region"] = True
            d["region_name"] = self.region_name(s.region)
            out.append(d)
            seen.add(s.id)

        # ② 相邻区域 —— 只暴露「区域」，不直接暴露对方区域里的具体地点。
        #    选中区域后落到该区域的 entrance，再在区域内走到具体地点。
        region = self._regions.get(current.region)
        for adj_region_id in (region.adjacent if region else []):
            adj = self._regions.get(adj_region_id)
            if adj is None:
                continue
            entrance = adj.entrance or self._default_entrance(adj.id)
            out.append({
                "id": entrance,          # 移动目标仍是地点 id（落点）
                "name": adj.name,
                "desc": f"前往{adj.name}",
                "can_sleep": False,
                "shop": "",
                "region": adj.id,
                "same_region": False,
                "region_name": adj.name,
                "is_region_entry": True,
            })

        return out

    def _default_entrance(self, region_id: str) -> str:
        for s in self._scenes.values():
            if s.region == region_id:
                return s.id
        return ""

    def region_entrance(self, region_id: str) -> str:
        region = self._regions.get(region_id)
        if region and region.entrance:
            return region.entrance
        return self._default_entrance(region_id)

    def can_travel_to(self, from_scene: str, to_scene: str) -> bool:
        """同区域可直达；跨区域只有落点正好是对方区域 entrance 时允许。"""
        cur = self._scenes.get(from_scene)
        dst = self._scenes.get(to_scene)
        if cur is None or dst is None:
            return False
        if cur.region == dst.region:
            return True
        region = self._regions.get(cur.region)
        if region is None or dst.region not in region.adjacent:
            return False
        return self.region_entrance(dst.region) == dst.id

    def neighbors(self, scene_id: str) -> List[Scene]:
        """兼容旧接口：返回可达地点对象列表。"""
        return [self._scenes[x["id"]] for x in self.reachable(scene_id) if x["id"] in self._scenes]

    def all_ids(self) -> List[str]:
        return list(self._scenes.keys())
