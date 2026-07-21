"""Immutable event envelope — every piece of data in the system is wrapped in this.

Timestamps are UTC. Payloads are frozen via MappingProxyType.
Events carry a source tag, event type, and optional ticker for market data.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional


class EventType(str, Enum):
    ORDERBOOK_SNAPSHOT = "orderbook_snapshot"
    ORDERBOOK_DELTA = "orderbook_delta"
    SPOT_PRICE = "spot_price"
    SENTIMENT = "sentiment"
    MACRO = "macro"
    TRADE_SIGNAL = "trade_signal"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    HEALTH_CHECK = "health_check"
    VESSEL_STATE_CHANGE = "vessel_state_change"
    SYSTEM = "system"


class EventEnvelope:
    """Immutable, hashable event wrapper.

    The payload is frozen via MappingProxyType so no downstream code can
    accidentally mutate shared event data. This is critical for the
    prediction engine reading hot state snapshots while new events arrive.
    """

    __slots__ = (
        "_event_id",
        "_source",
        "_event_type",
        "_ticker",
        "_payload",
        "_timestamp",
    )

    def __init__(
        self,
        source: str,
        event_type: EventType,
        payload: Mapping[str, Any],
        ticker: Optional[str] = None,
        timestamp: Optional[float] = None,
    ):
        object.__setattr__(self, "_event_id", str(uuid.uuid4()))
        object.__setattr__(self, "_source", source)
        object.__setattr__(self, "_event_type", event_type)
        object.__setattr__(self, "_ticker", ticker)
        object.__setattr__(self, "_payload", MappingProxyType(dict(payload)))
        object.__setattr__(self, "_timestamp", timestamp or time.time())

    @property
    def event_id(self) -> str:
        return self._event_id

    @property
    def source(self) -> str:
        return self._source

    @property
    def event_type(self) -> EventType:
        return self._event_type

    @property
    def ticker(self) -> Optional[str]:
        return self._ticker

    @property
    def payload(self) -> MappingProxyType:
        return self._payload

    @property
    def timestamp(self) -> float:
        return self._timestamp

    def age_seconds(self) -> float:
        """How old is this event?"""
        return time.time() - self._timestamp

    def to_dict(self) -> dict:
        """Serialize for DB storage or JSON dumps."""
        return {
            "event_id": self._event_id,
            "source": self._source,
            "event_type": self._event_type.value,
            "ticker": self._ticker,
            "payload": dict(self._payload),
            "timestamp": self._timestamp,
        }

    def __repr__(self) -> str:
        return (
            f"Event(id={self._event_id[:8]}, src={self._source}, "
            f"type={self._event_type.value}, ticker={self._ticker})"
        )

    def __hash__(self) -> int:
        return hash(self._event_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EventEnvelope):
            return NotImplemented
        return self._event_id == other._event_id
