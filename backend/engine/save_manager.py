"""版本化 JSON 存档系统（v2，对齐 v1 语义）。

- 版本链迁移：1.0 → 1.1 → 1.2 → 1.3 → 2.0.0
- 原子写入：tmp 文件 + replace
- 自动备份：写前备份旧档，最多 5 个
- 20 个槽位 + 槽位 0 = 快速存档
"""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CURRENT_VERSION = "2.0.0"
MAX_SAVE_SLOTS = 20
MAX_BACKUPS = 5
QUICK_SLOT = 0


@dataclass
class SaveMetadata:
    version: str = CURRENT_VERSION
    save_time: str = ""
    playtime: int = 0
    chapter: str = ""
    location: str = ""
    day: int = 1
    screenshot: Optional[str] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version, "save_time": self.save_time,
            "playtime": self.playtime, "chapter": self.chapter,
            "location": self.location, "day": self.day,
            "screenshot": self.screenshot, "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SaveMetadata":
        return cls(
            version=str(data.get("version", CURRENT_VERSION)),
            save_time=str(data.get("save_time", "")),
            playtime=int(data.get("playtime", 0)),
            chapter=str(data.get("chapter", "")),
            location=str(data.get("location", "")),
            day=int(data.get("day", 1)),
            screenshot=data.get("screenshot"),
            description=str(data.get("description", "")),
        )


@dataclass
class SaveSlot:
    slot_id: int
    exists: bool = False
    metadata: Optional[SaveMetadata] = None


class SaveMigration:
    @staticmethod
    def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class Migration_1_0_to_1_1(SaveMigration):
    @staticmethod
    def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
        if "world" in data:
            data["world"].setdefault("time_of_day", "morning")
            data["world"].setdefault("season", "spring")
        data["meta"]["version"] = "1.1"
        return data


class Migration_1_1_to_1_2(SaveMigration):
    @staticmethod
    def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
        if "characters" in data:
            new_characters = {}
            for char_id, char_data in data["characters"].items():
                new_characters[char_id] = {
                    "id": char_id,
                    "name": char_data.get("name", char_id),
                    "stats": char_data.get("stats", {}),
                    "flags": char_data.get("flags", {}),
                    "relation": char_data.get("relation", 0),
                    "location": char_data.get("location", ""),
                }
            data["characters"] = new_characters
        data.setdefault("character_flags", {})
        data["meta"]["version"] = "1.2"
        return data


class Migration_1_2_to_1_3(SaveMigration):
    @staticmethod
    def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
        if "world" in data:
            data["world"].setdefault("weather", "clear")
        data["meta"]["version"] = "1.3"
        return data


class Migration_1_3_to_2_0(SaveMigration):
    """2.0 重写：格式与 1.3 兼容（ctx.serialize() 同构），仅版本号推进。"""

    @staticmethod
    def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
        data["meta"]["version"] = CURRENT_VERSION
        return data


MIGRATION_CHAIN = {
    ("1.0", "1.1"): Migration_1_0_to_1_1,
    ("1.1", "1.2"): Migration_1_1_to_1_2,
    ("1.2", "1.3"): Migration_1_2_to_1_3,
    ("1.3", "2.0.0"): Migration_1_3_to_2_0,
}


class SaveManager:
    def __init__(self, event_bus: Any, game_context: Any, base_dir: Optional[Path] = None) -> None:
        self._bus = event_bus
        self._ctx = game_context
        self.base_dir = Path(base_dir) if base_dir else Path("saves")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._session_start = time.monotonic()

    # ── 会话 ──────────────────────────────────────────────────
    def start_session(self) -> None:
        self._session_start = time.monotonic()

    def get_playtime(self) -> int:
        return int(time.monotonic() - self._session_start)

    # ── 保存 ──────────────────────────────────────────────────
    def save(
        self,
        slot_id: int,
        description: str = "",
        screenshot: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not (0 <= slot_id < MAX_SAVE_SLOTS):
            logger.warning("非法槽位: %d", slot_id)
            return False
        meta = SaveMetadata(
            save_time=time.strftime("%Y-%m-%d %H:%M:%S"),
            playtime=self.get_playtime(),
            location=self._ctx.get_location(),
            day=self._ctx.get_day(),
            screenshot=screenshot,
            description=description,
        )
        save_data = {
            "meta": meta.to_dict(),
            **self._ctx.serialize(),
        }
        success = self._write_save_file(slot_id, save_data)
        if success:
            self._bus.emit("save.completed", slot_id=slot_id, ok=True)
        return success

    def load(self, slot_id: int) -> bool:
        if not (0 <= slot_id < MAX_SAVE_SLOTS):
            return False
        data = self._read_save_file(slot_id)
        if data is None:
            return False
        try:
            data = self._migrate_save(data)
            # 迁移结果写回磁盘，避免每次读档重复迁移
            if data.get("meta", {}).get("version") != self._read_save_file(slot_id).get("meta", {}).get("version"):
                self._write_save_file(slot_id, data)
            self._ctx.deserialize(data)
        except Exception as exc:  # noqa: BLE001
            logger.exception("读档失败: %s", exc)
            return False
        self._bus.emit("load.completed", slot_id=slot_id, ok=True)
        return True

    def delete(self, slot_id: int) -> bool:
        if not (0 <= slot_id < MAX_SAVE_SLOTS):
            return False
        save_file = self._slot_path(slot_id)
        if not save_file.exists():
            return False
        self._backup_save(slot_id)
        save_file.unlink()
        self._bus.emit("save.deleted", slot_id=slot_id)
        return True

    # ── 槽位查询 ──────────────────────────────────────────────
    def get_save_slots(self) -> List[SaveSlot]:
        slots: List[SaveSlot] = []
        for slot_id in range(MAX_SAVE_SLOTS):
            save_file = self._slot_path(slot_id)
            if not save_file.exists():
                slots.append(SaveSlot(slot_id=slot_id))
                continue
            meta = None
            try:
                data = json.loads(save_file.read_text(encoding="utf-8"))
                meta = SaveMetadata.from_dict(data.get("meta", {}))
            except (OSError, json.JSONDecodeError):
                logger.warning("存档文件损坏: %s", save_file)
            slots.append(SaveSlot(slot_id=slot_id, exists=True, metadata=meta))
        return slots

    def get_save_info(self, slot_id: int) -> Optional[SaveSlot]:
        if not (0 <= slot_id < MAX_SAVE_SLOTS):
            return None
        return self.get_save_slots()[slot_id]

    # ── 快速存档（槽位 0）─────────────────────────────────────
    def quick_save(self) -> bool:
        return self.save(QUICK_SLOT, description="快速存档")

    def quick_load(self) -> bool:
        return self.load(QUICK_SLOT)

    def has_quick_save(self) -> bool:
        return self._slot_path(QUICK_SLOT).exists()

    # ── 内部：文件读写 ────────────────────────────────────────
    def _slot_path(self, slot_id: int) -> Path:
        return self.base_dir / f"save_slot_{slot_id}.json"

    def _write_save_file(self, slot_id: int, data: Dict[str, Any]) -> bool:
        save_file = self._slot_path(slot_id)
        temp_file = self.base_dir / f".save_slot_{slot_id}.tmp"
        try:
            if save_file.exists():
                self._backup_save(slot_id)
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_file.replace(save_file)
            return True
        except OSError as exc:
            logger.error("写入存档失败: %s", exc)
            if temp_file.exists():
                temp_file.unlink()
            return False

    def _read_save_file(self, slot_id: int) -> Optional[Dict[str, Any]]:
        save_file = self._slot_path(slot_id)
        if not save_file.exists():
            return None
        try:
            return json.loads(save_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("读取存档失败: %s", exc)
            return None

    def _backup_save(self, slot_id: int) -> bool:
        save_file = self._slot_path(slot_id)
        if not save_file.exists():
            return False
        backup = self.base_dir / f"save_slot_{slot_id}.bak"
        shutil.copy2(save_file, backup)
        self._cleanup_old_backups(slot_id)
        return True

    def _cleanup_old_backups(self, slot_id: int) -> None:
        backups = sorted(self.base_dir.glob(f"save_slot_{slot_id}.bak*"))
        for old in backups[MAX_BACKUPS:]:
            try:
                old.unlink()
            except OSError:
                pass

    # ── 内部：版本迁移 ────────────────────────────────────────
    def _migrate_save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        meta = data.get("meta", {})
        version = str(meta.get("version", "1.0"))
        if version == CURRENT_VERSION:
            return data
        # 归一化：1.2.0 → 1.2；1.2 → 1.2
        parts = version.split(".")
        current = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else version
        target = ".".join(CURRENT_VERSION.split(".")[:2])
        applied = 0
        while current != target:
            migrated = False
            for (src, dst), migration in MIGRATION_CHAIN.items():
                if src == current:
                    logger.info("存档迁移: %s -> %s", src, dst)
                    data = migration.migrate(data)
                    current = dst.split(".")[0] + "." + dst.split(".")[1] if len(dst.split(".")) >= 2 else dst
                    applied += 1
                    migrated = True
                    break
            if not migrated:
                logger.error("存档版本无法迁移: %s（当前 %s）", current, version)
                break
            if applied > 20:
                break
        return data
