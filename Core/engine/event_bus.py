"""
事件总线模块 (event_bus.py)

本模块实现游戏引擎的事件通信系统，采用发布-订阅模式。
支持同步和异步两种事件处理机制，用于解耦各模块之间的依赖关系。

事件类型分为两类：
1. 系统事件：由引擎自动触发，如 on_game_start, on_day_begin 等
2. 游戏事件：由脚本主动触发，用于Mod之间的通信

设计要点：
- 使用字典存储订阅者列表，键为事件名称，值为回调函数列表
- 支持同步和异步回调函数混用
- 提供事件过滤和优先级机制
"""

import asyncio
from typing import Callable, Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import threading
import logging


# 配置日志记录器
logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """事件优先级枚举"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class EventContext:
    """事件上下文，包含事件的元数据"""
    event_name: str
    source: Optional[str] = None
    timestamp: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    data: Dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL
    # 阻止事件继续传播的标志
    _stopped: bool = False

    def stop_propagation(self) -> None:
        """阻止事件继续向下传播"""
        self._stopped = True

    @property
    def is_stopped(self) -> bool:
        return self._stopped


@dataclass
class EventSubscription:
    """事件订阅配置"""
    callback: Callable
    priority: EventPriority = EventPriority.NORMAL
    once: bool = False  # 是否只触发一次
    filter_fn: Optional[Callable[[EventContext], bool]] = None


class EventBus:
    """
    事件总线管理器

    提供事件的发布、订阅、退订功能。支持同步和异步处理器，
    并且提供事件过滤、优先级排序等高级功能。

    使用示例：
        event_bus = EventBus()

        # 订阅事件
        def on_day_begin(day: int):
            print(f"新的一天开始了：第{day}天")

        event_bus.subscribe("on_day_begin", on_day_begin)

        # 发布事件
        event_bus.emit("on_day_begin", day=1)

        # 异步事件处理
        async def on_game_save(data: Dict):
            await save_to_cloud(data)

        event_bus.subscribe("on_save", on_game_save)
        await event_bus.emit_async("on_save", data={"hp": 100})
    """

    def __init__(self):
        """初始化事件总线"""
        self._subscribers: Dict[str, List[EventSubscription]] = {}
        self._event_history: List[EventContext] = []  # 事件历史记录
        self._max_history_size: int = 100  # 最大历史记录数
        self._lock = threading.RLock()  # 线程安全锁
        self._global_filters: List[Callable[[EventContext], bool]] = []

        # 预定义的系统事件列表
        self._system_events: Set[str] = {
            "on_game_start",
            "on_game_end",
            "on_day_begin",
            "on_day_end",
            "on_save",
            "on_load",
            "on_scene_change",
            "on_character_stat_changed",
            "on_inventory_changed",
            "on_dialogue_start",
            "on_dialogue_end",
            "on_choice_made",
            "on_battle_start",
            "on_battle_end",
            "on_error",
        }

        logger.info("事件总线初始化完成")

    def subscribe(
        self,
        event_name: str,
        callback: Callable,
        priority: EventPriority = EventPriority.NORMAL,
        once: bool = False,
        filter_fn: Optional[Callable[[EventContext], bool]] = None
    ) -> EventSubscription:
        """
        订阅事件

        Args:
            event_name: 事件名称
            callback: 回调函数，可以是同步或异步函数
            priority: 事件优先级
            once: 是否只触发一次后自动取消订阅
            filter_fn: 事件过滤器函数

        Returns:
            EventSubscription: 订阅对象，可用于后续退订
        """
        with self._lock:
            if event_name not in self._subscribers:
                self._subscribers[event_name] = []

            subscription = EventSubscription(
                callback=callback,
                priority=priority,
                once=once,
                filter_fn=filter_fn
            )

            self._subscribers[event_name].append(subscription)

            # 按优先级排序，高优先级的先执行
            self._subscribers[event_name].sort(
                key=lambda x: x.priority.value,
                reverse=True
            )

            # 如果是系统事件，记录日志
            if event_name in self._system_events:
                logger.debug(f"订阅系统事件: {event_name}")
            else:
                logger.debug(f"订阅游戏事件: {event_name}")

            return subscription

    def unsubscribe(self, event_name: str, callback: Callable) -> bool:
        """
        退订事件

        Args:
            event_name: 事件名称
            callback: 要退订的回调函数

        Returns:
            bool: 是否成功退订
        """
        with self._lock:
            if event_name not in self._subscribers:
                return False

            original_count = len(self._subscribers[event_name])
            self._subscribers[event_name] = [
                sub for sub in self._subscribers[event_name]
                if sub.callback != callback
            ]

            success = len(self._subscribers[event_name]) < original_count

            if success:
                logger.debug(f"成功退订事件: {event_name}")

            return success

    def unsubscribe_all(self, event_name: str) -> int:
        """
        退订指定事件的所有回调

        Args:
            event_name: 事件名称

        Returns:
            int: 退订的回调数量
        """
        with self._lock:
            if event_name not in self._subscribers:
                return 0

            count = len(self._subscribers[event_name])
            del self._subscribers[event_name]

            logger.debug(f"退订事件 {event_name} 的所有 {count} 个回调")
            return count

    def emit(self, event_name: str, **kwargs: Any) -> EventContext:
        """
        同步发布事件

        所有同步回调函数会立即执行，异步回调函数会被跳过。
        适用于不需要等待处理结果的系统事件。

        Args:
            event_name: 事件名称
            **kwargs: 传递给回调函数的关键字参数

        Returns:
            EventContext: 事件上下文对象
        """
        context = EventContext(
            event_name=event_name,
            data=kwargs
        )

        # 应用全局过滤器
        for filter_fn in self._global_filters:
            if not filter_fn(context):
                logger.debug(f"事件 {event_name} 被全局过滤器阻止")
                return context

        with self._lock:
            subscribers = self._subscribers.get(event_name, []).copy()

        # 记录到历史
        self._record_history(context)

        # 执行同步回调
        for subscription in subscribers:
            # 检查过滤器
            if subscription.filter_fn and not subscription.filter_fn(context):
                continue

            # 检查是否停止传播
            if context.is_stopped:
                logger.debug(f"事件 {event_name} 传播已停止")
                break

            try:
                # 判断是否为异步函数
                if asyncio.iscoroutinefunction(subscription.callback):
                    logger.warning(
                        f"事件 {event_name} 的异步回调 {subscription.callback.__name__} "
                        f"在同步 emit 中被跳过，请使用 emit_async"
                    )
                else:
                    subscription.callback(**kwargs)

                # 如果是一次性订阅，执行后退订
                if subscription.once:
                    self.unsubscribe(event_name, subscription.callback)

            except Exception as e:
                logger.error(
                    f"事件 {event_name} 的回调执行出错: {e}",
                    exc_info=True
                )
                # 继续执行其他回调，不中断

        return context

    async def emit_async(self, event_name: str, **kwargs: Any) -> EventContext:
        """
        异步发布事件

        支持同步和异步回调函数混用。异步回调会并发执行，
        同步回调会按顺序执行。适用于需要等待处理结果的事件。

        Args:
            event_name: 事件名称
            **kwargs: 传递给回调函数的关键字参数

        Returns:
            EventContext: 事件上下文对象
        """
        context = EventContext(
            event_name=event_name,
            data=kwargs
        )

        # 应用全局过滤器
        for filter_fn in self._global_filters:
            if not filter_fn(context):
                logger.debug(f"事件 {event_name} 被全局过滤器阻止")
                return context

        with self._lock:
            subscribers = self._subscribers.get(event_name, []).copy()

        # 记录到历史
        self._record_history(context)

        # 分离同步和异步回调
        sync_callbacks = []
        async_callbacks = []

        for subscription in subscribers:
            # 检查过滤器
            if subscription.filter_fn and not subscription.filter_fn(context):
                continue

            # 检查是否停止传播
            if context.is_stopped:
                break

            if asyncio.iscoroutinefunction(subscription.callback):
                async_callbacks.append(subscription)
            else:
                sync_callbacks.append(subscription)

        # 先执行同步回调
        for subscription in sync_callbacks:
            try:
                subscription.callback(**kwargs)

                # 如果是一次性订阅，执行后退订
                if subscription.once:
                    self.unsubscribe(event_name, subscription.callback)

            except Exception as e:
                logger.error(
                    f"事件 {event_name} 的同步回调执行出错: {e}",
                    exc_info=True
                )

        # 并发执行异步回调
        if async_callbacks:
            tasks = []
            for subscription in async_callbacks:
                try:
                    task = asyncio.create_task(
                        subscription.callback(**kwargs)
                    )
                    tasks.append(task)

                    # 如果是一次性订阅，在任务完成后退订
                    if subscription.once:
                        task.add_done_callback(
                            lambda _: self.unsubscribe(event_name, subscription.callback)
                        )

                except Exception as e:
                    logger.error(
                        f"事件 {event_name} 的异步回调创建任务出错: {e}",
                        exc_info=True
                    )

            # 等待所有异步任务完成
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        return context

    def add_global_filter(self, filter_fn: Callable[[EventContext], bool]) -> None:
        """
        添加全局事件过滤器

        全局过滤器会在所有事件触发前执行，可以用于日志记录、
        权限检查、事件统计等场景。

        Args:
            filter_fn: 过滤器函数，返回True表示允许事件通过
        """
        self._global_filters.append(filter_fn)
        logger.debug("添加全局事件过滤器")

    def remove_global_filter(self, filter_fn: Callable[[EventContext], bool]) -> bool:
        """
        移除全局事件过滤器

        Args:
            filter_fn: 要移除的过滤器函数

        Returns:
            bool: 是否成功移除
        """
        try:
            self._global_filters.remove(filter_fn)
            return True
        except ValueError:
            return False

    def get_subscribers(self, event_name: str) -> List[EventSubscription]:
        """
        获取指定事件的所有订阅者

        Args:
            event_name: 事件名称

        Returns:
            List[EventSubscription]: 订阅者列表
        """
        with self._lock:
            return self._subscribers.get(event_name, []).copy()

    def get_event_history(
        self,
        event_name: Optional[str] = None,
        limit: int = 10
    ) -> List[EventContext]:
        """
        获取事件历史记录

        Args:
            event_name: 如果指定，只返回该事件的历史
            limit: 返回的最大记录数

        Returns:
            List[EventContext]: 事件上下文列表
        """
        with self._lock:
            if event_name:
                return [
                    ctx for ctx in self._event_history
                    if ctx.event_name == event_name
                ][-limit:]
            return self._event_history[-limit:]

    def clear_history(self) -> None:
        """清空事件历史记录"""
        with self._lock:
            self._event_history.clear()
            logger.debug("事件历史记录已清空")

    def _record_history(self, context: EventContext) -> None:
        """记录事件到历史"""
        self._event_history.append(context)

        # 限制历史记录大小
        if len(self._event_history) > self._max_history_size:
            self._event_history = self._event_history[-self._max_history_size:]

    def __repr__(self) -> str:
        """事件总线的字符串表示"""
        with self._lock:
            event_count = len(self._subscribers)
            total_subscribers = sum(len(subs) for subs in self._subscribers.values())
            return f"EventBus(events={event_count}, subscribers={total_subscribers})"


class EventConstants:
    """
    事件常量定义

    包含所有预定义的系统事件名称，便于统一引用，
    避免拼写错误。
    """

    # 游戏生命周期事件
    GAME_START = "on_game_start"
    GAME_END = "on_game_end"
    GAME_PAUSE = "on_game_pause"
    GAME_RESUME = "on_game_resume"

    # 时间系统事件
    DAY_BEGIN = "on_day_begin"
    DAY_END = "on_day_end"
    TIME_CHANGE = "on_time_change"
    LOCATION_CHANGE = "on_location_change"

    # 存档事件
    SAVE = "on_save"
    LOAD = "on_load"
    QUICK_SAVE = "on_quick_save"
    QUICK_LOAD = "on_quick_load"

    # 场景事件
    SCENE_CHANGE = "on_scene_change"
    SCENE_LOADED = "on_scene_loaded"

    # 角色事件
    CHARACTER_STAT_CHANGED = "on_character_stat_changed"
    CHARACTER_RELATION_CHANGED = "on_character_relation_changed"
    CHARACTER_ADDED = "on_character_added"
    CHARACTER_REMOVED = "on_character_removed"

    # 背包事件
    INVENTORY_CHANGED = "on_inventory_changed"
    ITEM_ADDED = "on_item_added"
    ITEM_REMOVED = "on_item_removed"

    # 对话事件
    DIALOGUE_START = "on_dialogue_start"
    DIALOGUE_END = "on_dialogue_end"
    DIALOGUE_LINE = "on_dialogue_line"

    # 选择事件
    CHOICE_MADE = "on_choice_made"
    CHOICE_DISPLAYED = "on_choice_displayed"

    # 战斗事件
    BATTLE_START = "on_battle_start"
    BATTLE_END = "on_battle_end"
    BATTLE_TURN = "on_battle_turn"

    # 错误事件
    ERROR = "on_error"
    SCRIPT_ERROR = "on_script_error"

    # UI事件
    UI_UPDATE = "on_ui_update"
    UI_REFRESH = "on_ui_refresh"


# 创建全局事件总线实例
_default_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """
    获取全局事件总线实例

    使用单例模式确保整个应用只有一个事件总线实例。

    Returns:
        EventBus: 全局事件总线实例
    """
    global _default_event_bus
    if _default_event_bus is None:
        _default_event_bus = EventBus()
    return _default_event_bus
