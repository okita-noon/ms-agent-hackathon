from __future__ import annotations

import asyncio

_locks: dict[str, asyncio.Lock] = {}


def get_channel_user_lock(channel: str, user_id: str) -> asyncio.Lock:
    """Return a per-user asyncio.Lock scoped to a channel.

    Keyed by "{channel}:{user_id}" so LINE and phone locks are independent
    even if the same identifier appears in both channels.
    Safe to call without awaiting — dict mutation happens between await points.
    """
    key = f"{channel}:{user_id}"
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]
