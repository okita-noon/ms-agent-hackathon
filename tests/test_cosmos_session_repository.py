from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.connectors.adapters.cosmos_session_repository import CosmosSessionRepository


class _EmptyAsyncItems:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


def _make_repo_with_container():
    container = MagicMock()
    container.query_items.return_value = _EmptyAsyncItems()

    repo = CosmosSessionRepository.__new__(CosmosSessionRepository)
    repo._db = SimpleNamespace(get_container_client=lambda _name: container)
    return repo, container


@pytest.mark.asyncio
async def test_find_active_session_filters_expired_sessions():
    repo, container = _make_repo_with_container()

    result = await repo.find_active_session("T-TEST", "email", "buyer@example.com")

    assert result is None
    query = container.query_items.call_args.args[0]
    params = container.query_items.call_args.kwargs["parameters"]
    assert "c.expires_at > @now" in query
    assert {"name": "@tid", "value": "T-TEST"} in params
    assert {"name": "@ch", "value": "email"} in params
    assert {"name": "@uid", "value": "buyer@example.com"} in params
    now_param = next(p for p in params if p["name"] == "@now")
    assert now_param["value"]


@pytest.mark.asyncio
async def test_find_by_conversation_id_filters_expired_sessions():
    repo, container = _make_repo_with_container()

    result = await repo.find_by_conversation_id("T-TEST", "conv-123")

    assert result is None
    query = container.query_items.call_args.args[0]
    params = container.query_items.call_args.kwargs["parameters"]
    assert "c.expires_at > @now" in query
    assert {"name": "@tid", "value": "T-TEST"} in params
    assert {"name": "@cid", "value": "conv-123"} in params
    now_param = next(p for p in params if p["name"] == "@now")
    assert now_param["value"]
