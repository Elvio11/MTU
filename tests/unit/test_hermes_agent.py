import asyncio
import json
import pytest
import runpy
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.hermes import HermesAgent

CONFIG = {
    "hermes": {
        "channel_whitelist": ["mtus:channel:token_received"]
    }
}

@pytest.fixture
def agent():
    a = HermesAgent(CONFIG)
    a.redis = AsyncMock()
    return a

@pytest.mark.asyncio
async def test_hermes_connect_redis():
    a = HermesAgent(CONFIG)
    mock_redis = MagicMock()
    mock_pubsub = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    mock_pubsub.subscribe = AsyncMock()
    
    with patch("aioredis.from_url", side_effect=AsyncMock(return_value=mock_redis)):
        await a.connect_redis()
        assert a.redis == mock_redis
        assert a.pubsub == mock_pubsub

@pytest.mark.asyncio
async def test_hermes_relay_message(agent):
    envelope = {
        "agent_id": "AGT-01",
        "event_type": "token_received",
        "payload": {"mint": "m1"},
        "correlation_id": str(uuid.uuid4())
    }
    msg = {"data": json.dumps(envelope), "channel": "mtus:channel:token_received"}
    await agent.relay_message(msg)
    agent.redis.publish.assert_called()

@pytest.mark.asyncio
async def test_hermes_run_loop(agent):
    agent.pubsub = MagicMock()
    agent.connect_redis = AsyncMock()
    corr_id = str(uuid.uuid4())
    async def get_msg_then_stop(*args, **kwargs):
        agent.running = False
        return {"data": json.dumps({"agent_id": "A", "event_type": "T", "payload": {}, "correlation_id": corr_id}), "channel": "c"}
        
    agent.pubsub.get_message = AsyncMock(side_effect=get_msg_then_stop)
    agent.relay_message = AsyncMock()
    with patch("src.python.agents.hermes.asyncio.sleep", return_value=None):
        await agent.run()
    agent.relay_message.assert_awaited()

@pytest.mark.asyncio
async def test_hermes_stop(agent):
    agent.pubsub = AsyncMock()
    await agent.stop()
    agent.redis.close.assert_awaited_once()
    assert agent.running is False

def test_hermes_main_keyboard_interrupt():
    import runpy
    m = mock_open(read_data="hermes:\n  channel_whitelist: []\n")
    with patch("src.python.agents.hermes.open", m), \
         patch("src.python.agents.hermes.HermesAgent") as mock_agent_class, \
         patch("src.python.agents.hermes.validate_config", return_value=(True, None)), \
         patch("src.python.agents.hermes.asyncio.run", side_effect=[KeyboardInterrupt(), None]) as mock_run:
        mock_agent_instance = mock_agent_class.return_value
        try:
            runpy.run_module("src.python.agents.hermes", run_name="__main__")
        except SystemExit:
            pass
        assert mock_run.call_count == 2
        mock_agent_instance.run.assert_called()
        mock_agent_instance.stop.assert_called()
