"""In-process pub/sub hub for Server-Sent Events (SSE)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, Optional, Set


class EventHub:
    def __init__(self) -> None:
        self._subscribers: Set[asyncio.Queue[Dict[str, Any]]] = set()

    def publish(self, event_type: str, session_id: Optional[str] = None, **data: Any) -> None:
        payload = {
            "type": event_type,
            "session_id": session_id,
            "ts": round(time.time(), 3),
            **data,
        }
        for q in list(self._subscribers):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def subscribe(self, filter_session_id: Optional[str] = None) -> AsyncIterator[str]:
        q: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        try:
            # Send initial connected ping
            yield f"data: {json.dumps({'type': 'connected', 'session_id': filter_session_id})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    if filter_session_id and msg.get("session_id") not in (None, filter_session_id):
                        continue
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            self._subscribers.discard(q)
