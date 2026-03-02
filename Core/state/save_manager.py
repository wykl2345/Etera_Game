"""
存档管理模块 (save_manager.py)

本模块实现游戏存档的序列化和反序列化功能，采用版本化JSON格式。
支持存档版本迁移，确保不同版本的存档可以互相兼容。

设计特点：
- 版本化存档：每个存档包含版本号，支持版本迁移链
- 原子写入：使用临时文件+重命名确保存档不会损坏
- 元数据管理：保存游戏时间、剧情进度等附加信息
- 自动备份：保存前自动备份旧存档

存档结构：
save_slot_1.json
{
  "meta": {
    "version": "1.2.0",
    "save_time": "2024-01-15T10:30:00",
    "playtime": 3600,
    "screenshot": "base64..."
  },
  "world": { "day": 42, ... },
  "player": { ... },
  "characters": { ... },
  "flags": { ... }
}

版本迁移链：
migrate_1.0_to_1.1.py -> migrate_1.1_to_1.2.py
"""

import os
import json
import shutil
import time
import logging
from typing import List , Any, Dict, Optional
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
import threading
import tempfile


# 配置日志记录器
logger = logging.getLogger(__name__)


# 引擎当前版本
CURRENT_VERSION = "1.2.0"

# 存档目录
SAVE_DIR = Path("saves")
BACKUP_DIR = Path("saves/backups")
MAX_BACKUPS = 5  # 最大备份数量
MAX_SAVE_SLOTS = 20  # 最大存档槽位


@dataclass
class SaveMetadata:
    """存档元数据"""
    version: str = CURRENT_VERSION
    save_time: str = ""
    playtime: int = 0  # 游戏时长（秒）
    chapter: str = ""  # 当前章节
    location: str = ""  # 当前地点
    day: int = 1  # 当前天数
    screenshot: Optional[str] = None  # 截图（base64）
    description: str = ""  # 存档描述


@dataclass
class SaveSlot:
    """存档槽位信息"""
    slot_id: int
    exists: bool = False
    metadata: Optional[SaveMetadata] = None


class SaveMigration:
    """
    存档迁移基类

    每个版本的迁移需要继承此类并实现migrate方法。
    """

    @staticmethod
    def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行数据迁移

        Args:
            data: 原始存档数据

        Returns:
            Dict[str, Any]: 迁移后的存档数据
        """
        raise NotImplementedError


class Migration_1_0_to_1_1(SaveMigration):
    """1.0 -> 1.1 迁移"""

    @staticmethod
    def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
        """添加新的字段"""
        logger.info("执行存档迁移: 1.0 -> 1.1")

        # 1.1版本添加了新的time_of_day字段
        if "world" in data and "time_of_day" not in data["world"]:
            data["world"]["time_of_day"] = "morning"

        # 添加新的season字段
        if "world" in data and "season" not in data["world"]:
            data["world"]["season"] = "spring"

        data["meta"]["version"] = "1.1"

        return data


class Migration_1_1_to_1_2(SaveMigration):
    """1.1 -> 1.2 迁移"""

    @staticmethod
    def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
        """重构角色数据结构"""
        logger.info("执行存档迁移: 1.1 -> 1.2")

        # 1.2版本角色数据结构变化
        if "characters" in data:
            new_characters = {}
            for char_id, char_data in data["characters"].items():
                # 新的角色数据结构
                new_characters[char_id] = {
                    "id": char_id,
                    "name": char_data.get("name", char_id),
                    "stats": char_data.get("stats", {}),
                    "flags": char_data.get("flags", {}),
                    "relation": char_data.get("relation", 0),
                    "location": char_data.get("location", ""),
                }
            data["characters"] = new_characters

        # 添加character_flags
        if "character_flags" not in data:
            data["character_flags"] = {}

        data["meta"]["version"] = "1.2"

        return data


class Migration_1_2_to_1_3(SaveMigration):
    """1.2 -> 1.3 迁移"""

    @staticmethod
    def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
        """添加天气系统"""
        logger.info("执行存档迁移: 1.2 -> 1.3")

        # 添加天气字段
        if "world" in data and "weather" not in data["world"]:
            data["world"]["weather"] = "clear"

        data["meta"]["version"] = "1.3"

        return data


# 迁移链注册
MIGRATION_CHAIN = {
    ("1.0", "1.1"): Migration_1_0_to_1_1,
    ("1.1", "1.2"): Migration_1_1_to_1_2,
    ("1.2", "1.3"): Migration_1_2_to_1_3,
}


class SaveManager:
    """
    存档管理器

    负责游戏的保存和加载功能，支持多存档槽位和自动版本迁移。

    使用示例：
        save_manager = SaveManager(event_bus, game_context)

        # 保存游戏
        save_manager.save(slot_id=1, description="第一章结束")

        # 加载游戏
        success = save_manager.load(slot_id=1)

        # 获取存档列表
        slots = save_manager.get_save_slots()

        # 删除存档
        save_manager.delete(slot_id=1)
    """

    def __init__(
        self,
        event_bus: Any,
        game_context: Any,
        base_dir: Optional[Path] = None
    ):
        """
        初始化存档管理器

        Args:
            event_bus: 事件总线实例
            game_context: 游戏上下文实例
            base_dir: 存档目录（可选）
        """
        self.event_bus = event_bus
        self.context = game_context
        self.base_dir = base_dir or SAVE_DIR

        # 确保目录存在
        self.base_dir.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        # 线程锁
        self._lock = threading.RLock()

        # 游戏开始时间（用于计算游玩时长）
        self._session_start_time: Optional[float] = None

        logger.info(f"存档管理器初始化完成，目录: {self.base_dir}")

    def start_session(self) -> None:
        """开始新的游戏会话，记录开始时间"""
        self._session_start_time = time.time()

    def get_playtime(self) -> int:
        """
        获取当前会话的游玩时长

        Returns:
            int: 秒数
        """
        if self._session_start_time is None:
            return 0
        return int(time.time() - self._session_start_time)

    def save(
        self,
        slot_id: int,
        description: str = "",
        screenshot: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        保存游戏

        Args:
            slot_id: 存档槽位ID
            description: 存档描述
            screenshot: 截图（base64编码）
            metadata: 额外的元数据

        Returns:
            bool: 是否保存成功
        """
        if slot_id < 0 or slot_id >= MAX_SAVE_SLOTS:
            logger.error(f"无效的存档槽位: {slot_id}")
            return False

        with self._lock:
            try:
                # 序列化游戏状态
                save_data = self.context.serialize()

                # 构建元数据
                meta = SaveMetadata(
                    version=CURRENT_VERSION,
                    save_time=datetime.now().isoformat(),
                    playtime=self.get_playtime(),
                    day=self.context.get_day(),
                    location=self.context.get_location(),
                    chapter=metadata.get("chapter", "") if metadata else "",
                    description=description,
                    screenshot=screenshot,
                )

                save_data["meta"] = {
                    "version": meta.version,
                    "save_time": meta.save_time,
                    "playtime": meta.playtime,
                    "day": meta.day,
                    "location": meta.location,
                    "chapter": meta.chapter,
                    "description": meta.description,
                    "screenshot": meta.screenshot,
                }

                # 执行保存
                success = self._write_save_file(slot_id, save_data)

                if success:
                    logger.info(f"游戏已保存: 槽位 {slot_id}")
                    self.event_bus.emit("save.completed", slot_id=slot_id)
                else:
                    logger.error(f"保存失败: 槽位 {slot_id}")

                return success

            except Exception as e:
                logger.error(f"保存游戏时出错: {e}", exc_info=True)
                return False

    def load(self, slot_id: int) -> bool:
        """
        加载游戏

        Args:
            slot_id: 存档槽位ID

        Returns:
            bool: 是否加载成功
        """
        if slot_id < 0 or slot_id >= MAX_SAVE_SLOTS:
            logger.error(f"无效的存档槽位: {slot_id}")
            return False

        with self._lock:
            try:
                # 读取存档文件
                save_data = self._read_save_file(slot_id)
                if save_data is None:
                    logger.warning(f"存档不存在: 槽位 {slot_id}")
                    return False

                # 版本迁移
                save_data = self._migrate_save(save_data)

                # 恢复游戏状态
                self.context.deserialize(save_data)

                # 重置会话时间
                self.start_session()

                logger.info(f"游戏已加载: 槽位 {slot_id}")
                self.event_bus.emit("load.completed", slot_id=slot_id)

                return True

            except Exception as e:
                logger.error(f"加载游戏时出错: {e}", exc_info=True)
                return False

    def delete(self, slot_id: int) -> bool:
        """
        删除存档

        Args:
            slot_id: 存档槽位ID

        Returns:
            bool: 是否删除成功
        """
        with self._lock:
            save_file = self.base_dir / f"save_slot_{slot_id}.json"

            if not save_file.exists():
                logger.warning(f"存档不存在，无法删除: 槽位 {slot_id}")
                return False

            try:
                # 先备份
                self._backup_save(slot_id)

                # 删除文件
                save_file.unlink()

                logger.info(f"存档已删除: 槽位 {slot_id}")
                self.event_bus.emit("save.deleted", slot_id=slot_id)

                return True

            except Exception as e:
                logger.error(f"删除存档时出错: {e}")
                return False

    def get_save_slots(self) -> List[SaveSlot]:
        """
        获取所有存档槽位信息

        Returns:
            List[SaveSlot]: 存档槽位列表
        """
        slots = []

        for i in range(MAX_SAVE_SLOTS):
            save_file = self.base_dir / f"save_slot_{i}.json"

            slot = SaveSlot(slot_id=i, exists=save_file.exists())

            if save_file.exists():
                try:
                    with open(save_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    if "meta" in data:
                        meta = data["meta"]
                        slot.metadata = SaveMetadata(
                            version=meta.get("version", "unknown"),
                            save_time=meta.get("save_time", ""),
                            playtime=meta.get("playtime", 0),
                            day=meta.get("day", 1),
                            location=meta.get("location", ""),
                            chapter=meta.get("chapter", ""),
                            description=meta.get("description", ""),
                        )
                except Exception as e:
                    logger.warning(f"读取存档元数据失败: {e}")

            slots.append(slot)

        return slots

    def quick_save(self) -> bool:
        """快速保存到快速存档槽位"""
        return self.save(slot_id=0, description="Quick Save")

    def quick_load(self) -> bool:
        """从快速存档槽位加载"""
        save_file = self.base_dir / "save_slot_0.json"
        if not save_file.exists():
            logger.warning("快速存档不存在")
            return False
        return self.load(slot_id=0)

    def has_quick_save(self) -> bool:
        """检查快速存档是否存在"""
        save_file = self.base_dir / "save_slot_0.json"
        return save_file.exists()

    def _write_save_file(self, slot_id: int, data: Dict[str, Any]) -> bool:
        """
        写入存档文件（原子操作）

        Args:
            slot_id: 存档槽位ID
            data: 存档数据

        Returns:
            bool: 是否写入成功
        """
        save_file = self.base_dir / f"save_slot_{slot_id}.json"
        temp_file = self.base_dir / f".save_slot_{slot_id}.tmp"

        try:
            # 先备份旧存档
            if save_file.exists():
                self._backup_save(slot_id)

            # 写入临时文件
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 原子重命名
            temp_file.replace(save_file)

            return True

        except Exception as e:
            # 清理临时文件
            if temp_file.exists():
                temp_file.unlink()
            raise e

    def _read_save_file(self, slot_id: int) -> Optional[Dict[str, Any]]:
        """
        读取存档文件

        Args:
            slot_id: 存档槽位ID

        Returns:
            Optional[Dict]: 存档数据
        """
        save_file = self.base_dir / f"save_slot_{slot_id}.json"

        if not save_file.exists():
            return None

        with open(save_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _backup_save(self, slot_id: int) -> bool:
        """
        备份存档

        Args:
            slot_id: 存档槽位ID

        Returns:
            bool: 是否备份成功
        """
        save_file = self.base_dir / f"save_slot_{slot_id}.json"

        if not save_file.exists():
            return False

        try:
            # 生成备份文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = BACKUP_DIR / f"save_slot_{slot_id}_{timestamp}.json"

            # 复制文件
            shutil.copy2(save_file, backup_file)

            # 清理旧备份
            self._cleanup_old_backups(slot_id)

            logger.debug(f"存档已备份: {backup_file}")
            return True

        except Exception as e:
            logger.warning(f"备份存档失败: {e}")
            return False

    def _cleanup_old_backups(self, slot_id: int) -> None:
        """清理旧的备份文件"""
        backups = sorted(
            BACKUP_DIR.glob(f"save_slot_{slot_id}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        # 删除多余的备份
        for old_backup in backups[MAX_BACKUPS:]:
            try:
                old_backup.unlink()
                logger.debug(f"删除旧备份: {old_backup}")
            except Exception as e:
                logger.warning(f"删除旧备份失败: {e}")

    def _migrate_save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行存档版本迁移

        Args:
            data: 原始存档数据

        Returns:
            Dict: 迁移后的存档数据
        """
        current_version = data.get("meta", {}).get("version", "1.0")

        if current_version == CURRENT_VERSION:
            return data

        logger.info(f"开始存档迁移: {current_version} -> {CURRENT_VERSION}")

        # 解析版本号
        def parse_version(version: str) -> tuple:
            parts = version.split(".")
            return tuple(int(p) for p in parts)

        current = parse_version(current_version)
        target = parse_version(CURRENT_VERSION)

        # 按顺序执行迁移
        while current < target:
            # 尝试找到下一个版本的迁移
            next_version = None
            migration = None

            for (from_ver, to_ver), migrator in MIGRATION_CHAIN.items():
                if parse_version(from_ver) == current:
                    next_version = to_ver
                    migration = migrator
                    break

            if migration is None:
                logger.warning(f"没有找到从 {current} 的迁移路径")
                break

            # 执行迁移
            data = migration.migrate(data)
            current = parse_version(next_version)

        logger.info("存档迁移完成")
        return data

    def export_save(self, slot_id: int, export_path: Path) -> bool:
        """
        导出存档到指定路径

        Args:
            slot_id: 存档槽位ID
            export_path: 导出路径

        Returns:
            bool: 是否导出成功
        """
        with self._lock:
            save_file = self.base_dir / f"save_slot_{slot_id}.json"

            if not save_file.exists():
                return False

            try:
                shutil.copy2(save_file, export_path)
                return True
            except Exception as e:
                logger.error(f"导出存档失败: {e}")
                return False

    def import_save(self, import_path: Path, slot_id: int) -> bool:
        """
        从指定路径导入存档

        Args:
            import_path: 导入路径
            slot_id: 存档槽位ID

        Returns:
            bool: 是否导入成功
        """
        with self._lock:
            if not import_path.exists():
                return False

            try:
                # 验证存档文件
                with open(import_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if "meta" not in data or "world" not in data:
                    logger.error("无效的存档文件格式")
                    return False

                # 写入存档槽位
                return self._write_save_file(slot_id, data)

            except Exception as e:
                logger.error(f"导入存档失败: {e}")
                return False

    def get_save_info(self, slot_id: int) -> Optional[SaveSlot]:
        """
        获取指定槽位的存档信息

        Args:
            slot_id: 存档槽位ID

        Returns:
            Optional[SaveSlot]: 存档信息
        """
        slots = self.get_save_slots()
        return slots[slot_id] if slot_id < len(slots) else None
