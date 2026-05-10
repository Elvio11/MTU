import pytest
import asyncio
import json
import runpy
from unittest.mock import MagicMock, AsyncMock, patch
from src.python.agents.dashboard_bridge import DashboardBridge

@pytest.fixture
def mock_redis():
    with patch("aioredis.from_url", new_callable=AsyncMock) as mock:
        mock_instance = AsyncMock()
        mock_pubsub = MagicMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.get_message = AsyncMock()
        mock_pubsub.close = AsyncMock()
        # Ensure pubsub() is a regular mock call, not a coroutine
        mock_instance.pubsub = MagicMock(return_value=mock_pubsub)
        mock_instance.close = AsyncMock()
        mock.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_ws():
    mock_ws = AsyncMock()
    mock_ws.remote_address = ("127.0.0.1", 12345)
    mock_ws.wait_closed = AsyncMock()
    mock_ws.send = AsyncMock()
    return mock_ws

@pytest.mark.asyncio
async def test_dashboard_bridge_handler(mock_ws):
    bridge = DashboardBridge()
    # Mock wait_closed to return immediately
    mock_ws.wait_closed.return_value = None
    
    await bridge.handler(mock_ws, "/test")
    # Discarded in finally
    assert mock_ws not in bridge.clients
    
    # Test error in wait_closed
    mock_ws.wait_closed.side_effect = Exception("Test error")
    await bridge.handler(mock_ws, "/test")
    assert mock_ws not in bridge.clients

@pytest.mark.asyncio
async def test_dashboard_bridge_forward_redis_messages(mock_redis, mock_ws):
    bridge = DashboardBridge()
    bridge.running = True
    bridge.clients.add(mock_ws)
    
    # Mock Redis message
    mock_pubsub = mock_redis.pubsub.return_value
    # Message that will trigger generic Exception in forward loop (e.g. data is not a string for json.loads)
    mock_pubsub.get_message.side_effect = [
        {"type": "message", "channel": "test-channel", "data": json.dumps({"test": "data"})},
        {"type": "message", "channel": "test-channel", "data": "invalid-json"},
        {"type": "message", "channel": "test-channel", "data": 12345}, # TypeError in json.loads
        {"type": "message", "channel": "test-channel", "data": json.dumps({"test": "data"})}, # for client error
        Exception("Redis error"),
        asyncio.CancelledError()
    ]
    
    # Mock client.send to raise error once to cover line 73
    mock_ws.send.side_effect = [None, Exception("Send error")]
    
    # Use shorter sleep to speed up test
    with patch("asyncio.sleep", AsyncMock()):
        try:
            await asyncio.wait_for(bridge.forward_redis_messages(), timeout=0.1)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            pass
        
    assert mock_ws.send.called

@pytest.mark.asyncio
async def test_dashboard_bridge_run(mock_redis):
    bridge = DashboardBridge()
    
    with patch("websockets.serve", new_callable=MagicMock) as mock_serve:
        mock_serve.return_value.__aenter__ = AsyncMock()
        mock_serve.return_value.__aexit__ = AsyncMock()
        
        # Mock forward_redis_messages to stop immediately
        bridge.forward_redis_messages = AsyncMock()
        
        await bridge.run()
        assert bridge.running is True
        bridge.forward_redis_messages.assert_called_once()

@pytest.mark.asyncio
async def test_dashboard_bridge_stop(mock_redis):
    bridge = DashboardBridge()
    bridge.redis = mock_redis
    bridge.pubsub = mock_redis.pubsub.return_value
    
    await bridge.stop()
    assert bridge.running is False
    bridge.pubsub.unsubscribe.assert_called_once()
    bridge.pubsub.close.assert_called_once()
    mock_redis.close.assert_called_once()

def test_dashboard_bridge_main_keyboard_interrupt():
    with patch("src.python.agents.dashboard_bridge.DashboardBridge.run", side_effect=KeyboardInterrupt):
        with patch("src.python.agents.dashboard_bridge.DashboardBridge.stop", new_callable=AsyncMock) as mock_stop:
            with patch("asyncio.run") as mock_asyncio_run:
                mock_asyncio_run.side_effect = [KeyboardInterrupt(), None]
                runpy.run_module("src.python.agents.dashboard_bridge", run_name="__main__")
                assert mock_asyncio_run.call_count == 2
