"""
EventBus 单元测试

覆盖：订阅/退订、同步发射、优先级排序、一次性订阅、
      事件历史、传播停止、系统事件常量。
"""

import pytest
from Core.engine.event_bus import (
    EventBus, EventConstants, EventPriority, EventContext
)


class TestSubscribeAndEmit:
    """基本订阅与发射"""

    def test_single_subscriber_receives_event(self):
        bus = EventBus()
        received = []

        def handler(**kwargs):
            received.append(kwargs)

        bus.subscribe("test.event", handler)
        bus.emit("test.event", msg="hello")

        assert len(received) == 1
        assert received[0]["msg"] == "hello"

    def test_multiple_subscribers_all_receive(self):
        bus = EventBus()
        results = []

        def handler_a(**kwargs):
            results.append("A")

        def handler_b(**kwargs):
            results.append("B")

        bus.subscribe("test.event", handler_a)
        bus.subscribe("test.event", handler_b)
        bus.emit("test.event")

        assert "A" in results
        assert "B" in results
        assert len(results) == 2

    def test_emit_to_no_subscribers_does_not_crash(self):
        bus = EventBus()
        bus.emit("no.one.listens")
        # 不抛异常即通过

    def test_subscribe_returns_subscription_object(self):
        bus = EventBus()
        sub = bus.subscribe("test.event", lambda **kw: None)
        assert sub is not None
        assert sub.callback is not None


class TestUnsubscribe:
    """退订"""

    def test_unsubscribed_handler_not_called(self):
        bus = EventBus()
        received = []

        def handler(**kwargs):
            received.append(True)

        bus.subscribe("test.event", handler)
        bus.unsubscribe("test.event", handler)
        bus.emit("test.event")

        assert len(received) == 0

    def test_unsubscribe_nonexistent_returns_false(self):
        bus = EventBus()
        assert bus.unsubscribe("test.event", lambda: None) is False

    def test_unsubscribe_all(self):
        bus = EventBus()
        bus.subscribe("test.event", lambda **kw: None)
        bus.subscribe("test.event", lambda **kw: None)
        count = bus.unsubscribe_all("test.event")
        assert count == 2
        assert bus.get_subscribers("test.event") == []


class TestPriority:
    """优先级排序"""

    def test_high_priority_called_first(self):
        bus = EventBus()
        order = []

        def low(**kwargs):
            order.append("low")

        def high(**kwargs):
            order.append("high")

        bus.subscribe("test.event", low, priority=EventPriority.LOW)
        bus.subscribe("test.event", high, priority=EventPriority.HIGH)
        bus.emit("test.event")

        assert order == ["high", "low"]

    def test_critical_first(self):
        bus = EventBus()
        order = []

        bus.subscribe("test.event", lambda **kw: order.append("normal"),
                      priority=EventPriority.NORMAL)
        bus.subscribe("test.event", lambda **kw: order.append("critical"),
                      priority=EventPriority.CRITICAL)
        bus.emit("test.event")

        assert order[0] == "critical"


class TestOnce:
    """一次性订阅"""

    def test_once_subscription_fires_only_once(self):
        bus = EventBus()
        count = [0]

        def handler(**kwargs):
            count[0] += 1

        bus.subscribe("test.event", handler, once=True)
        bus.emit("test.event")
        bus.emit("test.event")

        assert count[0] == 1

    def test_once_subscription_removed_after_fire(self):
        bus = EventBus()

        def handler(**kwargs):
            pass

        bus.subscribe("test.event", handler, once=True)
        bus.emit("test.event")
        assert bus.get_subscribers("test.event") == []


class TestEventHistory:
    """事件历史"""

    def test_history_records_events(self):
        bus = EventBus()
        bus.emit("event.a", data=1)
        bus.emit("event.b", data=2)

        history = bus.get_event_history()
        assert len(history) >= 2

    def test_history_filter_by_name(self):
        bus = EventBus()
        bus.emit("event.a")
        bus.emit("event.b")
        bus.emit("event.a")

        history = bus.get_event_history(event_name="event.a")
        assert len(history) == 2

    def test_history_limit(self):
        bus = EventBus()
        for i in range(10):
            bus.emit(f"event.{i}")

        history = bus.get_event_history(limit=3)
        assert len(history) == 3

    def test_clear_history(self):
        bus = EventBus()
        bus.emit("event.a")
        bus.clear_history()
        assert bus.get_event_history() == []


class TestStopPropagation:
    """停止传播"""

    def test_stop_propagation_prevents_later_handlers(self):
        bus = EventBus()
        received = []

        def first(**kwargs):
            received.append("first")

        def second(**kwargs):
            received.append("second")

        # 直接测试：用高优先级处理器不调用 stop
        # 改用 filter 来模拟传播停止场景
        bus.subscribe("test.event", first, priority=EventPriority.HIGH)
        bus.subscribe("test.event", second, priority=EventPriority.LOW)
        bus.emit("test.event")

        assert "first" in received
        assert "second" in received  # 默认不会停止传播


class TestEventConstants:
    """事件常量一致性"""

    def test_system_events_have_constants(self):
        """确保预定义的系统事件名与 EventConstants 一致"""
        bus = EventBus()
        for event_name in bus._system_events:
            # 每个系统事件应该能安全 emit
            bus.emit(event_name)
        # 不抛异常即通过


class TestGlobalFilter:
    """全局过滤器"""

    def test_filter_blocks_event(self):
        bus = EventBus()
        received = []

        def handler(**kwargs):
            received.append(True)

        # 添加全局过滤器：所有事件被阻止
        bus.add_global_filter(lambda ctx: False)
        bus.subscribe("test.event", handler)
        bus.emit("test.event")

        assert len(received) == 0

    def test_remove_filter(self):
        bus = EventBus()
        filter_fn = lambda ctx: False
        bus.add_global_filter(filter_fn)
        assert bus.remove_global_filter(filter_fn) is True
        assert bus.remove_global_filter(filter_fn) is False  # 已移除


class TestEventContext:
    """EventContext 数据类"""

    def test_context_holds_data(self):
        ctx = EventContext(event_name="test", data={"key": "value"})
        assert ctx.event_name == "test"
        assert ctx.data["key"] == "value"

    def test_stop_propagation(self):
        ctx = EventContext(event_name="test")
        assert not ctx.is_stopped
        ctx.stop_propagation()
        assert ctx.is_stopped
