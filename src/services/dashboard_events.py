from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import uuid4


@dataclass(slots=True)
class DashboardEvent:
    event: str
    tenant_id: str
    data: dict[str, Any]
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_sse(self) -> str:
        payload = {
            **self.data,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at.isoformat(),
        }
        return f"id: {self.id}\nevent: {self.event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


class DashboardEventBroker:
    """In-memory pub/sub for dashboard SSE clients.

    This is intentionally process-local for the MVP. When Container Apps scales to
    multiple API replicas, replace the publish/subscribe source with Service Bus
    or Cosmos DB Change Feed so all replicas receive the same events.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[DashboardEvent]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, event: str, tenant_id: str, data: dict[str, Any]) -> None:
        dashboard_event = DashboardEvent(event=event, tenant_id=tenant_id, data=data)
        async with self._lock:
            queues = list(self._subscribers.get(tenant_id, set()))

        for queue in queues:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(dashboard_event)

    async def subscribe(self, tenant_id: str) -> AsyncIterator[str]:
        queue: asyncio.Queue[DashboardEvent] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers[tenant_id].add(queue)

        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield event.to_sse()
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            async with self._lock:
                self._subscribers[tenant_id].discard(queue)
                if not self._subscribers[tenant_id]:
                    del self._subscribers[tenant_id]


dashboard_event_broker = DashboardEventBroker()
