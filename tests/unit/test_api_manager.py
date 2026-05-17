import pytest
import time
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.python.shared.api_manager import (
    ApiRouter,
    ApiProvider,
    CircuitState,
    TokenBucket,
    GlobalApiManager,
)


def test_token_bucket():
    bucket = TokenBucket(capacity=10, refill_rate=1)
    assert bucket.tokens == 10

    assert bucket.consume(5) is True
    assert bucket.tokens == 5

    assert bucket.consume(6) is False
    assert bucket.tokens == 5

    # Test refill
    bucket.last_refill = time.time() - 1
    bucket.refill()
    assert 5.9 < bucket.tokens < 6.1


@pytest.mark.asyncio
async def test_api_router_selection():
    p1 = ApiProvider(name="p1", url="u1", weight=10)
    p2 = ApiProvider(name="p2", url="u2", weight=100)
    router = ApiRouter("test", [p1, p2])

    # p2 should be preferred due to weight
    available = [p for p in router.providers.values() if p.state != CircuitState.OPEN]
    available.sort(
        key=lambda x: (x.bucket.tokens / x.capacity) * x.weight, reverse=True
    )
    assert available[0].name == "p2"


@pytest.mark.asyncio
async def test_api_router_failover():
    p1 = ApiProvider(name="p1", url="u1")
    router = ApiRouter("test", [p1])

    mock_resp_fail = MagicMock()
    mock_resp_fail.status = 500

    mock_context_fail = MagicMock()
    mock_context_fail.__aenter__ = AsyncMock(return_value=mock_resp_fail)
    mock_context_fail.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.request.return_value = mock_context_fail

    with patch.object(router, "get_session", return_value=mock_session):
        # Fail 3 times to open circuit
        await router.call("GET", "/path")
        await router.call("GET", "/path")
        await router.call("GET", "/path")

        assert router.providers["p1"].state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_api_router_429_immediate_open():
    p1 = ApiProvider(name="p1", url="u1")
    router = ApiRouter("test", [p1])

    mock_resp_429 = MagicMock()
    mock_resp_429.status = 429

    mock_context_429 = MagicMock()
    mock_context_429.__aenter__ = AsyncMock(return_value=mock_resp_429)
    mock_context_429.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.request.return_value = mock_context_429

    with patch.object(router, "get_session", return_value=mock_session):
        await router.call("GET", "/path")
        assert router.providers["p1"].state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_global_api_manager_singleton():
    GlobalApiManager._instance = None
    g1 = GlobalApiManager()
    g2 = GlobalApiManager()
    assert g1 is g2


@pytest.mark.asyncio
async def test_global_api_manager_flow():
    GlobalApiManager._instance = None
    g = GlobalApiManager()
    p1 = ApiProvider(name="p1", url="u1")
    g.setup_router("group1", [p1])

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"ok": True})

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.request.return_value = mock_context

    router = g.routers["group1"]
    with patch.object(router, "get_session", return_value=mock_session):
        result = await g.request("group1", "GET", "/path")
        assert result == {"ok": True}

    stats = g.get_stats()
    assert "group1" in stats
    assert stats["group1"]["p1"]["state"] == "closed"
