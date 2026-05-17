import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from src.python.shared.rpc_health import RPCHelper, CircuitState, RPCEndpoint
from src.python.shared.telegram_bot import TelegramBot
import aiohttp

@pytest.mark.asyncio
async def test_rpc_helper_rigorous():
    helper = RPCHelper(
        helius_url="http://helius",
        quicknode_url="http://quicknode",
        alchemy_url="http://alchemy",
        failure_threshold=2,
        reset_timeout=1
    )
    
    # Test circuit state transitions
    ep = helper.endpoints["helius"]
    ep.state = CircuitState.OPEN
    ep.state_change_time = asyncio.get_event_loop().time() - 2
    
    await helper._check_circuit_state()
    assert ep.state == CircuitState.HALF_OPEN
    
    # Test half-open to open
    ep.failures = 3
    ep.state_change_time = asyncio.get_event_loop().time() - 11
    await helper._check_circuit_state()
    assert ep.state == CircuitState.OPEN
    
    # Test half-open to closed
    ep.state = CircuitState.HALF_OPEN
    ep.failures = 0
    ep.state_change_time = asyncio.get_event_loop().time() - 11
    await helper._check_circuit_state()
    assert ep.state == CircuitState.CLOSED

    # Test weighted endpoints when all are open
    for name in helper.endpoints:
        helper.endpoints[name].state = CircuitState.OPEN
    
    endpoints = await helper._get_weighted_endpoints()
    assert len(endpoints) == 3 # Returns all if none available
    
    # Test make_request failures
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_post.return_value.__aenter__.return_value = mock_resp
        
        result = await helper.make_request("method", {})
        assert result is None
        assert helper.endpoints["helius"].failures >= 1

    # Test broadcast_transaction
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json.return_value = {"txid": "123"}
        mock_post.return_value.__aenter__.return_value = mock_resp
        
        results = await helper.broadcast_transaction("signed_tx")
        assert len(results) == 3
        assert results["helius"]["success"] is True

    await helper.close()

@pytest.mark.asyncio
async def test_telegram_bot_rigorous():
    bot = TelegramBot(token="test_token", admin_chat_id="123", otp_seed="seed")
    bot.session = aiohttp.ClientSession()
    
    with patch.object(bot.session, 'post') as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value.__aenter__.return_value = mock_resp
        
        result = await bot.send_message("123", "test message")
        assert result.get("ok") is True

    # Test exception handling
    with patch.object(bot.session, 'post', side_effect=Exception("network error")):
        result = await bot.send_message("123", "test message")
        assert result is None

    # Test notification
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.notify("System alert", priority="high")
        mock_send.assert_called_with("123", "[HIGH] System alert")

    # Test handle_message unauthorized
    bot.admin_chat_id = "999"
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.handle_message({"text": "/help", "chat": {"id": "123"}})
        mock_send.assert_called()
        assert "Unauthorized" in mock_send.call_args[0][1]

    await bot.session.close()
