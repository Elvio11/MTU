import pytest
import time
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from src.python.shared.rpc_health import RPCHelper, RPCEndpoint, CircuitState

@pytest.fixture
def helper():
    return RPCHelper("h_url", "q_url", "a_url")

@pytest.mark.asyncio
async def test_check_circuit_state(helper):
    ep = helper.endpoints["helius"]
    ep.state = CircuitState.OPEN
    ep.state_change_time = time.time() - 70
    
    await helper._check_circuit_state()
    assert ep.state == CircuitState.HALF_OPEN

@pytest.mark.asyncio
async def test_record_success_failure(helper):
    await helper._record_failure("helius")
    assert helper.endpoints["helius"].failures == 1
    
    await helper._record_success("helius")
    assert helper.endpoints["helius"].failures == 0

@pytest.mark.asyncio
async def test_circuit_breaker_opens(helper):
    helper.failure_threshold = 2
    await helper._record_failure("helius")
    await helper._record_failure("helius")
    assert helper.endpoints["helius"].state == CircuitState.OPEN

@pytest.mark.asyncio
async def test_get_weighted_endpoints(helper):
    helper.endpoints["helius"].last_success = 100
    helper.endpoints["quicknode"].last_success = 50
    helper.endpoints["alchemy"].last_success = 150
    
    endpoints = await helper._get_weighted_endpoints()
    assert endpoints[0].name == "quicknode" # oldest success
    assert endpoints[1].name == "helius"
    assert endpoints[2].name == "alchemy"

@pytest.mark.asyncio
async def test_make_request_success(helper):
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"ok": True})
    
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    
    mock_session = MagicMock()
    mock_session.post.return_value = mock_context
    
    with patch.object(helper, "get_session", return_value=mock_session):
        result = await helper.make_request("POST", {"data": 1})
        assert result == {"ok": True}

@pytest.mark.asyncio
async def test_broadcast_transaction(helper):
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"txid": "123"})
    
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    
    mock_session = MagicMock()
    mock_session.post.return_value = mock_context
    
    with patch.object(helper, "get_session", return_value=mock_session):
        results = await helper.broadcast_transaction("signed_tx")
        assert len(results) == 3
        assert results["helius"]["success"] is True

def test_get_status(helper):
    status = helper.get_status()
    assert "helius" in status
    assert status["helius"]["state"] == "closed"
