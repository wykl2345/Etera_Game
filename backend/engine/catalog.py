"""物品与商店目录（数据驱动：Data/items/items.yaml + Data/shops/shops.yaml）。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ItemDef:
    id: str
    name: str
    price: int = 0
    gift_value: int = 0
    desc: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "price": self.price,
            "gift_value": self.gift_value,
            "desc": self.desc,
        }


@dataclass
class Shop:
    id: str
    name: str
    items: List[str] = field(default_factory=list)
    markup: float = 1.0


class Catalog:
    """物品 + 商店。数据文件缺失时降级为空目录（不影响其它功能）。"""

    def __init__(
        self,
        items_path: Optional[Path] = None,
        shops_path: Optional[Path] = None,
    ) -> None:
        self._items: Dict[str, ItemDef] = {}
        self._shops: Dict[str, Shop] = {}
        self.items_path = Path(items_path) if items_path else Path("Data/items/items.yaml")
        self.shops_path = Path(shops_path) if shops_path else Path("Data/shops/shops.yaml")
        self.load_items()
        self.load_shops()

    # ── 加载 ──────────────────────────────────────────────────
    def _read_yaml(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            logger.warning("配置不存在: %s", path.resolve())
            return {}
        try:
            import yaml

            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            logger.error("配置解析失败 %s: %s", path, exc)
            return {}

    def load_items(self) -> int:
        raw = self._read_yaml(self.items_path).get("items") or {}
        if isinstance(raw, dict):
            for iid, spec in raw.items():
                spec = spec or {}
                self._items[str(iid)] = ItemDef(
                    id=str(iid),
                    name=str(spec.get("name", iid)),
                    price=int(spec.get("price", 0) or 0),
                    gift_value=int(spec.get("gift_value", 0) or 0),
                    desc=str(spec.get("desc", "")),
                )
        logger.info("物品已加载: %d 种", len(self._items))
        return len(self._items)

    def load_shops(self) -> int:
        raw = self._read_yaml(self.shops_path).get("shops") or {}
        if isinstance(raw, dict):
            for sid, spec in raw.items():
                spec = spec or {}
                self._shops[str(sid)] = Shop(
                    id=str(sid),
                    name=str(spec.get("name", sid)),
                    items=[str(x) for x in (spec.get("items") or [])],
                    markup=float(spec.get("markup", 1.0) or 1.0),
                )
        logger.info("商店已加载: %d 家", len(self._shops))
        return len(self._shops)

    # ── 查询 ──────────────────────────────────────────────────
    def item(self, item_id: str) -> Optional[ItemDef]:
        return self._items.get(item_id)

    def item_name(self, item_id: str) -> str:
        it = self._items.get(item_id)
        return it.name if it else item_id

    def gift_value(self, item_id: str) -> int:
        it = self._items.get(item_id)
        return it.gift_value if it else 0

    def shop(self, shop_id: str) -> Optional[Shop]:
        return self._shops.get(shop_id)

    def shop_goods(self, shop_id: str) -> List[Dict[str, Any]]:
        """商店商品列表（价格已按 markup 换算）。"""
        shop = self._shops.get(shop_id)
        if shop is None:
            return []
        goods: List[Dict[str, Any]] = []
        for iid in shop.items:
            it = self._items.get(iid)
            if it is None:
                logger.warning("商店 %s 引用了未定义物品: %s", shop_id, iid)
                continue
            d = it.to_dict()
            d["price"] = int(round(it.price * shop.markup))
            goods.append(d)
        return goods
