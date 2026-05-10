import asyncio
import json
import pytest
import runpy
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.dashboard_bridge import DashboardBridge

CONFIG = {
    "dashboard": {
        "host": "localhost",
        "port": 8765
    }
}

@pytest.fixture
def agent():
    a = DashboardBridge(CONFIG)
    a.redis = AsyncMock()
    return a

@pytest.mark.asyncio
async def test_dashboard_bridge_forward_redis_messages():
    a = DashboardBridge(CONFIG)
    mock_redis = MagicMock()
    mock_pubsub = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    mock_pubsub.subscribe = AsyncMock()
    
    async def get_msg_then_stop(*args, **kwargs):
        a.running = False
        return None
    mock_pubsub.get_message = AsyncMock(side_effect=get_msg_then_stop)

    with patch("aioredis.from_url", side_effect=AsyncMock(return_value=mock_redis)):
        a.running = True
        await a.forward_redis_messages()
        assert a.redis == mock_redis
        assert a.pubsub == mock_pubsub

@pytest.mark.asyncio
async def test_dashboard_bridge_handler(agent):
    ws = MagicMock()
    ws.wait_closed = AsyncMock()
    ws.remote_address = ("127.0.0.1", 1234)
    await agent.handler(ws, "/path")
    assert ws not in agent.clients # discarded in finally

@pytest.mark.asyncio
async def test_dashboard_bridge_run_loop(agent):
    agent.forward_redis_messages = AsyncMock()
    agent.running = True
    
    # Mock async context manager for websockets.serve
    class MockServe:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    
    with patch("websockets.serve", return_value=MockServe()), \
         patch("src.python.agents.dashboard_bridge.asyncio.sleep", return_value=None):
        # Trigger stop inside forward_redis_messages? 
        # Actually run() calls it.
        async def stop_soon(): agent.running = False
        agent.forward_redis_messages.side_effect = stop_soon
        await agent.run()
    agent.forward_redis_messages.assert_awaited()

@pytest.mark.asyncio
async def test_dashboard_bridge_stop(agent):
    agent.pubsub = AsyncMock()
    await agent.stop()
    agent.redis.close.assert_awaited_once()
    assert agent.running is False

def test_dashboard_bridge_main_keyboard_interrupt():
    import runpy
    m = mock_open(read_data="dashboard:\n  host: localhost\n  port: 8765\n")
    with patch("src.python.agents.dashboard_bridge.open", m), \
         patch("src.python.agents.dashboard_bridge.DashboardBridge") as mock_agent_class, \
         patch("src.python.agents.dashboard_bridge.validate_config", return_value=(True, None)), \
         patch("src.python.agents.dashboard_bridge.asyncio.run", side_effect=[KeyboardInterrupt(), None]) as mock_run:
        mock_agent_instance = mock_agent_class.return_value
        try:
            runpy.run_module("src.python.agents.dashboard_bridge", run_name="__main__")
        except SystemExit:
            pass
        assert mock_run.call_count == 2
        mock_agent_instance.run.assert_called()
        mock_agent_instance.stop.assert_called()
