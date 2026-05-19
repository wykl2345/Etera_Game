"""
缓存工具模块 (cache.py)

提供通用的缓存工具类，支持 LRU 淘汰策略和 TTL 过期。
供 resource_manager.py 内部使用，也可用于其他需要缓存的场景。

设计特点：
- 泛型支持：可缓存任意类型
- TTL 过期：支持按时间自动过期
- LRU 淘汰：缓存满时淘汰最近最少使用的条目
- 线程安全
"""

import time
import threading
import logging
from typing import Any, Dict, Optional, Callable, Generic, TypeVar
from collections import OrderedDict

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CacheEntry(Generic[T]):
    """缓存条目"""

    def __init__(self, key: str, value: T, ttl: float = None):
        self.key = key
        self.value = value
        self.created_at = time.time()
        self.last_accessed = self.created_at
        self.access_count = 0
        self.ttl = ttl  # 过期时间（秒），None 表示永不过期

    def is_expired(self) -> bool:
        """检查是否已过期"""
        if self.ttl is None:
            return False
        return (time.time() - self.created_at) > self.ttl

    def touch(self):
        """更新访问时间"""
        self.last_accessed = time.time()
        self.access_count += 1


class LRUCache(Generic[T]):
    """
    LRU 缓存

    支持最大条目限制、TTL 过期、回调通知。

    使用示例：
        cache = LRUCache(max_size=100, default_ttl=300)

        # 存
        cache.put("key1", value)

        # 取
        value = cache.get("key1")

        # 如果不存在，用工厂函数创建
        value = cache.get_or_create("key2", lambda: load_data())
    """

    def __init__(
        self,
        max_size: int = 100,
        default_ttl: float = None,
        on_evict: Callable[[str, T], None] = None
    ):
        """
        初始化 LRU 缓存

        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认过期时间（秒），None 表示永不过期
            on_evict: 淘汰回调函数，参数为 (key, value)
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.on_evict = on_evict

        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._lock = threading.RLock()

        logger.debug(f"LRUCache 初始化: max_size={max_size}, ttl={default_ttl}")

    def get(self, key: str) -> Optional[T]:
        """
        获取缓存值

        Args:
            key: 键

        Returns:
            Optional[T]: 缓存值，不存在或已过期返回 None
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            # 检查过期
            if entry.is_expired():
                self._remove(key)
                logger.debug(f"缓存已过期: {key}")
                return None

            # 更新访问记录（移到末尾表示最近使用）
            entry.touch()
            self._cache.move_to_end(key)
            return entry.value

    def put(self, key: str, value: T, ttl: float = None) -> None:
        """
        存入缓存

        Args:
            key: 键
            value: 值
            ttl: 自定义过期时间（覆盖默认值）
        """
        with self._lock:
            # 如果已存在，先移除旧的
            if key in self._cache:
                self._remove(key)

            # 检查容量，触发 LRU 淘汰
            while len(self._cache) >= self.max_size:
                self._evict_lru()

            # 存入新条目
            entry = CacheEntry(key, value, ttl or self.default_ttl)
            self._cache[key] = entry

    def get_or_create(self, key: str, factory: Callable[[], T], ttl: float = None) -> T:
        """
        获取或创建缓存

        Args:
            key: 键
            factory: 创建值的工厂函数
            ttl: 自定义过期时间

        Returns:
            T: 缓存值
        """
        value = self.get(key)
        if value is not None:
            return value

        # 创建新值
        value = factory()
        self.put(key, value, ttl)
        return value

    def remove(self, key: str) -> bool:
        """
        移除缓存

        Args:
            key: 键

        Returns:
            bool: 是否成功移除
        """
        with self._lock:
            return self._remove(key)

    def _remove(self, key: str) -> bool:
        """内部移除（已持有锁）"""
        if key not in self._cache:
            return False

        entry = self._cache.pop(key)
        if self.on_evict:
            try:
                self.on_evict(key, entry.value)
            except Exception as e:
                logger.warning(f"淘汰回调失败: {e}")
        return True

    def _evict_lru(self):
        """淘汰最近最少使用的条目"""
        if not self._cache:
            return

        # OrderedDict 的第一个条目是最久未使用的
        key, entry = next(iter(self._cache.items()))
        self._remove(key)
        logger.debug(f"LRU 淘汰: {key}")

    def clear(self) -> int:
        """
        清空所有缓存

        Returns:
            int: 清空的条目数
        """
        with self._lock:
            count = len(self._cache)
            for key in list(self._cache.keys()):
                self._remove(key)
            logger.debug(f"缓存已清空: {count} 个条目")
            return count

    def clean_expired(self) -> int:
        """
        清理所有过期条目

        Returns:
            int: 清理的条目数
        """
        with self._lock:
            expired = []
            for key, entry in self._cache.items():
                if entry.is_expired():
                    expired.append(key)

            for key in expired:
                self._remove(key)

            if expired:
                logger.debug(f"清理过期缓存: {len(expired)} 个")
            return len(expired)

    def contains(self, key: str) -> bool:
        """检查键是否存在且未过期"""
        value = self.get(key)
        return value is not None

    def size(self) -> int:
        """获取当前缓存条目数"""
        with self._lock:
            return len(self._cache)

    def stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            if not self._cache:
                return {"size": 0, "max_size": self.max_size, "hit_rate": 0.0}

            total_accesses = sum(e.access_count for e in self._cache.values())
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "total_accesses": total_accesses,
            }

    def __contains__(self, key: str) -> bool:
        return self.contains(key)

    def __len__(self) -> int:
        return self.size()
