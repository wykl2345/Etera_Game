"""
资源管理模块 (resource_manager.py)

本模块实现游戏资源的统一加载和缓存管理。采用LRU缓存策略，
避免重复加载相同的资源，提高游戏性能。

支持的资源类型：
- 图片资源 (PNG, JPG, WebP, SVG)
- 音频资源 (MP3, WAV, OGG)
- 字体资源 (TTF, OTF)
- 脚本资源 (Lua, YAML, JSON)
- 配置资源 (YAML, JSON)

设计特点：
- LRU缓存：最近最少使用的资源会被优先卸载
- 异步加载：大资源支持异步加载，不阻塞主线程
- 预加载：支持批量预加载常用资源
- 资源引用计数：跟踪资源使用情况
"""

import os
import json
import yaml
import logging
from typing import Any, Dict, List, Optional, Set, Callable, Union
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import threading
import hashlib
import time
from functools import lru_cache

from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt


# 配置日志记录器
logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """资源类型枚举"""
    IMAGE = "image"
    AUDIO = "audio"
    MUSIC = "music"
    FONT = "font"
    SCRIPT = "script"
    CONFIG = "config"
    TEXT = "text"
    DATA = "data"


@dataclass
class ResourceInfo:
    """资源信息"""
    path: str
    resource_type: ResourceType
    size: int  # 文件大小（字节）
    loaded_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    checksum: Optional[str] = None


class ResourceCache:
    """
    资源缓存

    采用LRU（最近最少使用）策略管理资源缓存。
    """

    def __init__(self, max_size: int = 100, max_memory_mb: int = 512):
        """
        初始化缓存

        Args:
            max_size: 最大缓存资源数量
            max_memory_mb: 最大内存使用（MB）
        """
        self.max_size = max_size
        self.max_memory = max_memory_mb * 1024 * 1024  # 转换为字节

        self._cache: Dict[str, Any] = {}
        self._info: Dict[str, ResourceInfo] = {}
        self._lock = threading.RLock()
        self._current_memory: int = 0

        logger.info(f"资源缓存初始化完成: max_size={max_size}, max_memory={max_memory_mb}MB")

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存资源

        Args:
            key: 资源键

        Returns:
            Optional[Any]: 缓存的资源，如果不存在返回None
        """
        with self._lock:
            if key not in self._cache:
                return None

            # 更新访问信息
            info = self._info[key]
            info.last_accessed = time.time()
            info.access_count += 1

            return self._cache[key]

    def put(self, key: str, value: Any, info: ResourceInfo) -> None:
        """
        添加资源到缓存

        Args:
            key: 资源键
            value: 资源值
            info: 资源信息
        """
        with self._lock:
            # 如果缓存已满，执行LRU清理
            if len(self._cache) >= self.max_size or self._current_memory + info.size > self.max_memory:
                self._evict_lru()

            # 检查是否已存在
            if key in self._cache:
                self._current_memory -= self._info[key].size

            # 添加到缓存
            self._cache[key] = value
            self._info[key] = info
            self._current_memory += info.size

            logger.debug(f"资源已缓存: {key} ({info.size} bytes)")

    def remove(self, key: str) -> bool:
        """
        移除缓存资源

        Args:
            key: 资源键

        Returns:
            bool: 是否成功移除
        """
        with self._lock:
            if key not in self._cache:
                return False

            self._current_memory -= self._info[key].size
            del self._cache[key]
            del self._info[key]

            return True

    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()
            self._info.clear()
            self._current_memory = 0
            logger.info("资源缓存已清空")

    def _evict_lru(self) -> None:
        """驱逐最近最少使用的资源"""
        if not self._cache:
            return

        # 找到最久未访问的资源
        lru_key = min(
            self._info.keys(),
            key=lambda k: self._info[k].last_accessed
        )

        # 移除
        self._current_memory -= self._info[lru_key].size
        del self._cache[lru_key]
        del self._info[lru_key]

        logger.debug(f"LRU驱逐资源: {lru_key}")

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "memory_used": self._current_memory,
                "max_memory": self.max_memory,
                "total_accesses": sum(i.access_count for i in self._info.values()),
            }

    def __contains__(self, key: str) -> bool:
        """检查资源是否在缓存中"""
        return key in self._cache


class ResourceManager:
    """
    资源管理器

    负责游戏资源的统一加载、缓存和管理。
    支持多种资源类型，提供同步和异步加载接口。

    使用示例：
        resource_manager = ResourceManager()

        # 加载图片
        image = resource_manager.load_image("background.png")

        # 加载配置
        config = resource_manager.load_config("game_settings.yaml")

        # 预加载资源
        await resource_manager.preload(["image1.png", "image2.png"])

        # 卸载未使用的资源
        resource_manager.unload_unused()
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        cache_size: int = 100,
        max_memory_mb: int = 512
    ):
        """
        初始化资源管理器

        Args:
            base_dir: 资源根目录
            cache_size: 缓存最大资源数
            max_memory_mb: 最大内存使用（MB）
        """
        self.base_dir = base_dir or Path("resources")

        # 初始化缓存
        self.cache = ResourceCache(cache_size, max_memory_mb)

        # 资源路径映射
        self._path_mappings: Dict[ResourceType, Path] = {
            ResourceType.IMAGE: self.base_dir / "images",
            ResourceType.AUDIO: self.base_dir / "audio",
            ResourceType.MUSIC: self.base_dir / "music",
            ResourceType.FONT: self.base_dir / "fonts",
            ResourceType.SCRIPT: self.base_dir / "scripts",
            ResourceType.CONFIG: self.base_dir / "config",
            ResourceType.TEXT: self.base_dir / "text",
            ResourceType.DATA: self.base_dir / "data",
        }

        # 加载器注册表
        self._loaders: Dict[ResourceType, Callable] = {
            ResourceType.IMAGE: self._load_image,
            ResourceType.AUDIO: self._load_audio,
            ResourceType.MUSIC: self._load_music,
            ResourceType.FONT: self._load_font,
            ResourceType.SCRIPT: self._load_script,
            ResourceType.CONFIG: self._load_config,
            ResourceType.TEXT: self._load_text,
            ResourceType.DATA: self._load_data,
        }

        # 资源引用计数
        self._ref_counts: Dict[str, int] = {}

        # 线程锁
        self._lock = threading.RLock()

        # 验证目录
        self._verify_directories()

        logger.info(f"资源管理器初始化完成: {self.base_dir}")

    def _verify_directories(self) -> None:
        """验证资源目录是否存在"""
        for resource_type, path in self._path_mappings.items():
            if not path.exists():
                logger.warning(f"资源目录不存在: {path}")
                # 创建目录
                path.mkdir(parents=True, exist_ok=True)

    def get_resource_path(
        self,
        resource_type: ResourceType,
        filename: str
    ) -> Path:
        """
        获取资源文件的完整路径

        Args:
            resource_type: 资源类型
            filename: 文件名

        Returns:
            Path: 完整路径
        """
        base_path = self._path_mappings.get(resource_type, self.base_dir)
        return base_path / filename

    def load(
        self,
        resource_type: ResourceType,
        filename: str,
        use_cache: bool = True
    ) -> Optional[Any]:
        """
        加载资源

        Args:
            resource_type: 资源类型
            filename: 文件名
            use_cache: 是否使用缓存

        Returns:
            Optional[Any]: 加载的资源，失败返回None
        """
        # 构建资源键
        key = f"{resource_type.value}:{filename}"

        # 尝试从缓存获取
        if use_cache:
            cached = self.cache.get(key)
            if cached is not None:
                self._increment_ref(key)
                return cached

        # 加载资源
        loader = self._loaders.get(resource_type)
        if not loader:
            logger.error(f"未知的资源类型: {resource_type}")
            return None

        try:
            resource_path = self.get_resource_path(resource_type, filename)
            resource = loader(resource_path)

            if resource is not None:
                # 获取文件大小
                size = resource_path.stat().st_size if resource_path.exists() else 0

                # 计算校验和
                checksum = self._calculate_checksum(resource_path) if resource_path.exists() else None

                # 创建资源信息
                info = ResourceInfo(
                    path=str(resource_path),
                    resource_type=resource_type,
                    size=size,
                    checksum=checksum
                )

                # 添加到缓存
                if use_cache:
                    self.cache.put(key, resource, info)

                # 增加引用计数
                self._increment_ref(key)

                logger.debug(f"资源已加载: {filename} ({resource_type.value})")
                return resource

        except Exception as e:
            logger.error(f"加载资源失败: {filename}, 错误: {e}")

        return None

    def _increment_ref(self, key: str) -> None:
        """增加资源引用计数"""
        with self._lock:
            self._ref_counts[key] = self._ref_counts.get(key, 0) + 1

    def _decrement_ref(self, key: str) -> None:
        """减少资源引用计数"""
        with self._lock:
            count = self._ref_counts.get(key, 1) - 1
            if count <= 0:
                self._ref_counts.pop(key, None)
                self.cache.remove(key)
            else:
                self._ref_counts[key] = count

    def release(self, resource_type: ResourceType, filename: str) -> None:
        """
        释放资源引用

        Args:
            resource_type: 资源类型
            filename: 文件名
        """
        key = f"{resource_type.value}:{filename}"
        self._decrement_ref(key)

    def _load_image(self, path: Path) -> Any:
        """加载图片资源（原始路径版本，供通用 load 方法使用）"""
        return str(path)

    def load_image(
        self,
        name: str,
        use_cache: bool = True,
        target_width: int = 400,
        target_height: int = 600
    ) -> Optional[QPixmap]:
        """
        加载图片资源并返回 QPixmap

        在 images 目录下按扩展名探测，加载后缓存。
        这是 ImageWidget 等显示组件的统一加载入口。

        Args:
            name: 图片名（不含路径和扩展名）
            use_cache: 是否使用缓存
            target_width: 目标宽度（保持宽高比缩放）
            target_height: 目标高度

        Returns:
            Optional[QPixmap]: 加载成功返回 QPixmap，失败返回 None
        """
        cache_key = f"pixmap:{name}:{target_width}x{target_height}"

        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        extensions = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]
        image_dir = self._path_mappings[ResourceType.IMAGE]

        for ext in extensions:
            path = image_dir / f"{name}{ext}"
            if path.exists():
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    pixmap = pixmap.scaled(
                        target_width, target_height,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    if use_cache:
                        info = ResourceInfo(
                            path=str(path),
                            resource_type=ResourceType.IMAGE,
                            size=path.stat().st_size,
                        )
                        self.cache.put(cache_key, pixmap, info)
                    return pixmap

        logger.warning(f"图片资源未找到: {name}")
        return None

    def _load_audio(self, path: Path) -> Any:
        """加载音频资源"""
        return str(path)

    def _load_music(self, path: Path) -> Any:
        """加载音乐资源"""
        return str(path)

    def _load_font(self, path: Path) -> Any:
        """加载字体资源"""
        return str(path)

    def _load_script(self, path: Path) -> Optional[str]:
        """加载脚本资源"""
        if not path.exists():
            return None

        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def _load_config(self, path: Path) -> Optional[Dict[str, Any]]:
        """加载配置资源"""
        if not path.exists():
            return None

        suffix = path.suffix.lower()

        try:
            if suffix in ['.yaml', '.yml']:
                with open(path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            elif suffix == '.json':
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.warning(f"不支持的配置格式: {suffix}")
                return None
        except Exception as e:
            logger.error(f"加载配置文件失败: {path}, 错误: {e}")
            return None

    def _load_text(self, path: Path) -> Optional[str]:
        """加载文本资源"""
        if not path.exists():
            return None

        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def _load_data(self, path: Path) -> Optional[Any]:
        """加载数据资源"""
        return self._load_config(path)

    def load_image(
        self,
        filename: str,
        use_cache: bool = True
    ) -> Optional[Any]:
        """加载图片资源"""
        return self.load(ResourceType.IMAGE, filename, use_cache)

    def load_audio(
        self,
        filename: str,
        use_cache: bool = True
    ) -> Optional[Any]:
        """加载音频资源"""
        return self.load(ResourceType.AUDIO, filename, use_cache)

    def load_music(
        self,
        filename: str,
        use_cache: bool = True
    ) -> Optional[Any]:
        """加载音乐资源"""
        return self.load(ResourceType.MUSIC, filename, use_cache)

    def load_script(
        self,
        filename: str,
        use_cache: bool = True
    ) -> Optional[str]:
        """加载脚本资源"""
        return self.load(ResourceType.SCRIPT, filename, use_cache)

    def load_config(
        self,
        filename: str,
        use_cache: bool = True
    ) -> Optional[Dict[str, Any]]:
        """加载配置资源"""
        return self.load(ResourceType.CONFIG, filename, use_cache)

    def preload(
        self,
        resources: List[tuple]
    ) -> Dict[str, Any]:
        """
        批量预加载资源

        Args:
            resources: 资源列表，每个元素为 (ResourceType, filename)

        Returns:
            Dict: 加载结果 {"success": [], "failed": []}
        """
        results = {"success": [], "failed": []}

        for resource_type, filename in resources:
            resource = self.load(resource_type, filename, use_cache=True)
            if resource is not None:
                results["success"].append(filename)
            else:
                results["failed"].append(filename)

        logger.info(f"预加载完成: 成功 {len(results['success'])}, 失败 {len(results['failed'])}")
        return results

    def unload_unused(self) -> int:
        """
        卸载未被引用的资源

        Returns:
            int: 卸载的资源数量
        """
        with self._lock:
            unused_keys = [
                key for key in self.cache._cache.keys()
                if key not in self._ref_counts
            ]

            for key in unused_keys:
                self.cache.remove(key)

            logger.info(f"已卸载 {len(unused_keys)} 个未使用的资源")
            return len(unused_keys)

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return self.cache.get_stats()

    def list_resources(
        self,
        resource_type: ResourceType,
        pattern: str = "*"
    ) -> List[str]:
        """
        列出指定类型的资源

        Args:
            resource_type: 资源类型
            pattern: 文件名模式

        Returns:
            List[str]: 资源文件名列表
        """
        path = self._path_mappings.get(resource_type)
        if not path or not path.exists():
            return []

        return [p.name for p in path.glob(pattern)]

    def resource_exists(
        self,
        resource_type: ResourceType,
        filename: str
    ) -> bool:
        """
        检查资源是否存在

        Args:
            resource_type: 资源类型
            filename: 文件名

        Returns:
            bool: 是否存在
        """
        path = self.get_resource_path(resource_type, filename)
        return path.exists()

    def _calculate_checksum(self, path: Path) -> Optional[str]:
        """计算文件校验和"""
        try:
            with open(path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return None

    def clear_cache(self) -> None:
        """清空资源缓存"""
        with self._lock:
            self.cache.clear()
            self._ref_counts.clear()
            logger.info("资源缓存已清空")


class ResourceValidator:
    """
    资源验证器

    用于验证资源文件的完整性和格式。
    """

    @staticmethod
    def validate_image(path: Path) -> bool:
        """验证图片资源"""
        if not path.exists():
            return False

        valid_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}
        return path.suffix.lower() in valid_extensions

    @staticmethod
    def validate_audio(path: Path) -> bool:
        """验证音频资源"""
        if not path.exists():
            return False

        valid_extensions = {'.mp3', '.wav', '.ogg', '.flac', '.m4a'}
        return path.suffix.lower() in valid_extensions

    @staticmethod
    def validate_script(path: Path) -> bool:
        """验证脚本资源"""
        if not path.exists():
            return False

        valid_extensions = {'.lua', '.luac'}
        return path.suffix.lower() in valid_extensions

    @staticmethod
    def validate_config(path: Path) -> bool:
        """验证配置文件"""
        if not path.exists():
            return False

        valid_extensions = {'.yaml', '.yml', '.json', '.toml'}
        return path.suffix.lower() in valid_extensions
