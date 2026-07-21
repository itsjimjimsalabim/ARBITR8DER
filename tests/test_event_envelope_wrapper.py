"""Tests for the immutable event envelope."""
import time

import pytest

from arbitr8der.market_data.immutable_event_envelope_wrapper import EventEnvelope, EventType


class TestEventEnvelopeCreation:
    """Event creation and immutability tests."""

    def test_create_event_with_basic_fields(self):
        event = EventEnvelope(
            source="test_source",
            event_type=EventType.SPOT_PRICE,
            payload={"price": 112000.50, "asset": "BTC"},
        )
        assert event.source == "test_source"
        assert event.event_type == EventType.SPOT_PRICE
        assert event.payload["price"] == 112000.50
        assert event.ticker is None

    def test_create_event_with_ticker(self):
        event = EventEnvelope(
            source="kalshi_ws",
            event_type=EventType.ORDERBOOK_SNAPSHOT,
            payload={"yes_best": 0.55},
            ticker="KXBTC15M-25JUL211200",
        )
        assert event.ticker == "KXBTC15M-25JUL211200"

    def test_event_has_unique_id(self):
        first_event = EventEnvelope(source="a", event_type=EventType.SYSTEM, payload={})
        second_event = EventEnvelope(source="b", event_type=EventType.SYSTEM, payload={})
        assert first_event.event_id != second_event.event_id

    def test_event_timestamp_is_set(self):
        before = time.time()
        event = EventEnvelope(source="x", event_type=EventType.SYSTEM, payload={})
        after = time.time()
        assert before <= event.timestamp <= after

    def test_event_custom_timestamp(self):
        event = EventEnvelope(
            source="x",
            event_type=EventType.SYSTEM,
            payload={},
            timestamp=1234567890.0,
        )
        assert event.timestamp == 1234567890.0

    def test_payload_is_frozen(self):
        event = EventEnvelope(source="x", event_type=EventType.SYSTEM, payload={"key": "val"})
        with pytest.raises(TypeError):
            event.payload["key"] = "changed"

    def test_event_is_hashable(self):
        event = EventEnvelope(source="x", event_type=EventType.SYSTEM, payload={})
        s = {event}
        assert event in s

    def test_events_are_equal_by_id(self):
        first_event = EventEnvelope(source="x", event_type=EventType.SYSTEM, payload={})
        second_event = EventEnvelope(source="x", event_type=EventType.SYSTEM, payload={})
        assert first_event != second_event  # Different IDs


class TestEventEnvelopeSerialization:
    """Serialization and age tests."""

    def test_to_dict(self):
        event = EventEnvelope(
            source="test",
            event_type=EventType.SPOT_PRICE,
            payload={"price": 100},
            ticker="BTC",
        )
        d = event.to_dict()
        assert d["source"] == "test"
        assert d["event_type"] == "spot_price"
        assert d["ticker"] == "BTC"
        assert d["payload"]["price"] == 100
        assert "event_id" in d
        assert "timestamp" in d

    def test_age_seconds(self):
        event = EventEnvelope(
            source="x",
            event_type=EventType.SYSTEM,
            payload={},
            timestamp=time.time() - 5.0,
        )
        age = event.age_seconds()
        assert age >= 4.9
        assert age < 6.0

    def test_repr_contains_info(self):
        event = EventEnvelope(
            source="kalshi_ws",
            event_type=EventType.ORDERBOOK_DELTA,
            payload={},
            ticker="KXBTC15M",
        )
        r = repr(event)
        assert "kalshi_ws" in r
        assert "orderbook_delta" in r
