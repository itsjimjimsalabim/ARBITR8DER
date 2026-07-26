"""Bounded asynchronous persistence queue for provider events.

Market/order/audit events have priority over disposable sensor samples.
The queue has a configurable maximum depth; when full, the oldest low-priority
(sensor) items are dropped first. High-priority items block the producer
rather than being dropped.
"""

import asyncio
import enum
import time
from dataclasses import dataclass, field
from typing import Any

from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)

_DEFAULT_MAX_DEPTH = 10_000
_SENSOR_DROP_BATCH = 100


class Priority(enum.IntEnum):
    """Queue priority — lower value = higher priority, dropped last."""
    CRITICAL = 0   # emergency stop, lease conflict
    MARKET = 1     # order book updates, fills, settlement
    AUDIT = 2      # trade intents, journal entries
    OBSERVATION = 3  # price observations, sentiment
    SENSOR = 4     # disposable health metrics, telemetry


@dataclass(order=True)
class QueueItem:
    """A prioritized item in the persistence queue."""
    priority: Priority
    timestamp: float = field(compare=False)
    payload: dict[str, Any] = field(compare=False)
    item_type: str = field(compare=False, default="unknown")


class BoundedPersistenceQueue:
    """Async queue with priority-based eviction when at capacity.

    Usage:
        queue = BoundedPersistenceQueue(max_depth=10000)
        await queue.enqueue(payload, priority=Priority.MARKET, item_type="order_book")
        item = await queue.dequeue()
    """

    def __init__(self, max_depth: int = _DEFAULT_MAX_DEPTH) -> None:
        self._max_depth = max_depth
        self._queue: asyncio.PriorityQueue[QueueItem] = asyncio.PriorityQueue(maxsize=max_depth)
        self._depth = 0
        self._total_enqueued = 0
        self._total_dropped = 0

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def total_enqueued(self) -> int:
        return self._total_enqueued

    @property
    def total_dropped(self) -> int:
        return self._total_dropped

    async def enqueue(self, payload: dict[str, Any], priority: Priority = Priority.OBSERVATION, item_type: str = "unknown") -> bool:
        """Add an item to the queue. Returns False if dropped due to backpressure."""
        if self._depth >= self._max_depth:
            if priority <= Priority.AUDIT:
                # High priority — try to make room by evicting sensor items
                evicted = await self._evict_sensors(_SENSOR_DROP_BATCH)
                if evicted == 0:
                    logger.warning("Queue full, high-priority item queued anyway (may block)")
            else:
                # Low priority — drop it
                self._total_dropped += 1
                logger.debug("Queue full, dropping %s item (priority=%s)", item_type, priority.name)
                return False

        item = QueueItem(priority=priority, timestamp=time.time(), payload=payload, item_type=item_type)
        await self._queue.put(item)
        self._depth += 1
        self._total_enqueued += 1
        return True

    async def dequeue(self) -> QueueItem | None:
        """Remove and return the highest-priority item, or None if empty."""
        try:
            item = self._queue.get_nowait()
            self._depth -= 1
            return item
        except asyncio.QueueEmpty:
            return None

    async def drain(self, max_items: int = 0) -> list[QueueItem]:
        """Drain up to max_items (0 = all) from the queue, highest priority first."""
        items = []
        limit = max_items if max_items > 0 else self._depth
        for _ in range(limit):
            item = await self.dequeue()
            if item is None:
                break
            items.append(item)
        return items

    async def _evict_sensors(self, count: int) -> int:
        """Remove up to `count` sensor-priority items from the queue.

        This is a best-effort sweep — re-inserts non-sensor items.
        """
        evicted = 0
        temp: list[QueueItem] = []
        for _ in range(min(count, self._depth)):
            try:
                item = self._queue.get_nowait()
                self._depth -= 1
                if item.priority == Priority.SENSOR:
                    evicted += 1
                    self._total_dropped += 1
                else:
                    temp.append(item)
            except asyncio.QueueEmpty:
                break
        # Re-insert non-sensor items
        for item in temp:
            await self._queue.put(item)
            self._depth += 1
        return evicted
