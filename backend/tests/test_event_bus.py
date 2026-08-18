"""EventBus 单元测试（复用 v1 测试要点，asyncio 化）。"""
import pytest

from engine.event_bus import EventBus, EventPriority


@pytest.fixture
def bus():
    return EventBus()


class TestSubscribeAndEmit:
    def test_single_subscriber_receives_event(self, bus):
        received = []
        bus.subscribe("test_event", lambda ctx: received.append(ctx.data))
        bus.emit("test_event", value=42)
        assert received == [{"value": 42}]

    def test_multiple_subscribers_all_receive(self, bus):
        received = []
        bus.subscribe("test_event", lambda ctx: received.append("a"))
        bus.subscribe("test_event", lambda ctx: received.append("b"))
        bus.emit("test_event")
        assert received == ["a", "b"]

    def test_emit_to_no_subscribers_does_not_crash(self, bus):
        ctx = bus.emit("no_such_event", x=1)
        assert ctx.event_name == "no_such_event"

    def test_subscribe_returns_subscription_object(self, bus):
        sub = bus.subscribe("e", lambda ctx: None)
        assert sub in bus.get_subscribers("e")


class TestUnsubscribe:
    def test_unsubscribed_handler_not_called(self, bus):
        received = []

        def handler(ctx):
            received.append(1)

        bus.subscribe("e", handler)
        bus.unsubscribe("e", handler)
        bus.emit("e")
        assert received == []

    def test_unsubscribe_nonexistent_returns_false(self, bus):
        assert bus.unsubscribe("e", lambda ctx: None) is False

    def test_unsubscribe_all(self, bus):
        bus.subscribe("e", lambda ctx: None)
        bus.subscribe("e", lambda ctx: None)
        assert bus.unsubscribe_all("e") == 2
        assert bus.get_subscribers("e") == []


class TestPriority:
    def test_high_priority_called_first(self, bus):
        order = []
        bus.subscribe("e", lambda ctx: order.append("low"), priority=EventPriority.LOW)
        bus.subscribe("e", lambda ctx: order.append("high"), priority=EventPriority.HIGH)
        bus.emit("e")
        assert order == ["high", "low"]

    def test_critical_first(self, bus):
        order = []
        bus.subscribe("e", lambda ctx: order.append("normal"))
        bus.subscribe("e", lambda ctx: order.append("critical"), priority=EventPriority.CRITICAL)
        bus.emit("e")
        assert order == ["critical", "normal"]


class TestOnce:
    def test_once_subscription_fires_only_once(self, bus):
        count = []
        bus.subscribe("e", lambda ctx: count.append(1), once=True)
        bus.emit("e")
        bus.emit("e")
        assert count == [1]

    def test_once_subscription_removed_after_fire(self, bus):
        bus.subscribe("e", lambda ctx: None, once=True)
        bus.emit("e")
        assert bus.get_subscribers("e") == []


class TestEventHistory:
    def test_record_history(self, bus):
        bus.emit("e1", a=1)
        bus.emit("e2", b=2)
        history = bus.get_event_history()
        assert [c.event_name for c in history] == ["e1", "e2"]

    def test_filter_by_name_and_limit(self, bus):
        for _ in range(5):
            bus.emit("e1")
        bus.emit("e2")
        only_e1 = bus.get_event_history("e1", limit=2)
        assert len(only_e1) == 2
        assert all(c.event_name == "e1" for c in only_e1)

    def test_clear_history(self, bus):
        bus.emit("e1")
        bus.clear_history()
        assert bus.get_event_history() == []


class TestGlobalFilter:
    def test_filter_blocks_event(self, bus):
        received = []
        bus.subscribe("e", lambda ctx: received.append(1))
        bus.add_global_filter(lambda ctx: False)
        bus.emit("e")
        assert received == []

    def test_remove_filter(self, bus):
        fn = lambda ctx: False  # noqa: E731
        bus.add_global_filter(fn)
        assert bus.remove_global_filter(fn) is True
        assert bus.remove_global_filter(fn) is False


class TestEventContext:
    def test_context_holds_data(self, bus):
        ctx = bus.emit("e", key="v")
        assert ctx.event_name == "e"
        assert ctx.data == {"key": "v"}

    def test_stop_propagation(self, bus):
        received = []

        def first(ctx):
            received.append("first")
            ctx.stop_propagation()

        bus.subscribe("e", first, priority=EventPriority.HIGH)
        bus.subscribe("e", lambda ctx: received.append("second"))
        bus.emit("e")
        assert received == ["first"]


class TestSystemEvents:
    def test_system_events_emit_safely(self, bus):
        names = [
            "on_game_start", "on_game_end", "on_day_begin", "on_day_end",
            "on_save", "on_load", "on_scene_change",
            "on_character_stat_changed", "on_inventory_changed",
            "on_dialogue_start", "on_dialogue_end", "on_choice_made",
            "on_battle_start", "on_battle_end", "on_error",
        ]
        for name in names:
            bus.emit(name)  # 不抛异常即通过
