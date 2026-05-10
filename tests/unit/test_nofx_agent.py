import asyncio
import json
import pytest
import runpy
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.nofx import NofxAgent

CONFIG = {
    "trading": {
        "position_size_sol": 0.1,
        "slippage_bps": 100
    }
}

@pytest.fixture
def agent():
    a = NofxAgent(CONFIG)
    a.redis = AsyncMock()
    return a

@pytest.mark.asyncio
async def test_nofx_connect_redis():
    a = NofxAgent(CONFIG)
    mock_redis = MagicMock()
    mock_pubsub = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    mock_pubsub.subscribe = AsyncMock()
    
    with patch("src.python.agents.nofx.aioredis.from_url", side_effect=AsyncMock(return_value=mock_redis)):
        await a.connect_redis()
        assert a.redis == mock_redis
        assert a.pubsub == mock_pubsub

@pytest.mark.asyncio
async def test_nofx_handle_intent(agent):
    corr_id = str(uuid.uuid4())
    intent = {
        "mint": "m1",
        "action": "buy",
        "amount_sol": 0.1
    }
    envelope = json.dumps({
        "agent_id": "AGT-04",
        "event_type": "intent_dispatched",
        "payload": intent,
        "correlation_id": corr_id
    })
    await agent.handle_intent(envelope)
    agent.redis.publish.assert_called()

@pytest.mark.asyncio
async def test_nofx_run_loop(agent):
    agent.pubsub = MagicMock()
    agent.connect_redis = AsyncMock()
    corr_id = str(uuid.uuid4())
    async def get_msg_then_stop(*args, **kwargs):
        agent.running = False
        return {"data": json.dumps({"agent_id": "A", "event_type": "I", "payload": {"mint":"m1", "action":"buy"}, "correlation_id": corr_id})}
        
    agent.pubsub.get_message = AsyncMock(side_effect=get_msg_then_stop)
    agent.handle_intent = AsyncMock()
    with patch("src.python.agents.nofx.asyncio.sleep", return_value=None):
        await agent.run()
    agent.handle_intent.assert_awaited()

@pytest.mark.asyncio
async def test_nofx_stop(agent):
    agent.pubsub = AsyncMock()
    await agent.stop()
    agent.redis.close.assert_awaited_once()
    assert agent.running is False

def test_nofx_main_keyboard_interrupt():
    import runpy
    m = mock_open(read_data="system:\n  environment: paper\n")
    with patch("src.python.agents.nofx.open", m), \
         patch("src.python.agents.nofx.NofxAgent") as mock_agent_class, \
         patch("src.python.agents.nofx.validate_config", return_value=(True, None)), \
         patch("src.python.agents.nofx.asyncio.run", side_effect=[KeyboardInterrupt(), None]) as mock_run:
        mock_agent_instance = mock_agent_class.return_value
        try:
            runpy.run_module("src.python.agents.nofx", run_name="__main__")
        except SystemExit:
            pass
        assert mock_run.call_count == 2
        mock_agent_instance.run.assert_called()
        mock_agent_instance.stop.assert_called()
