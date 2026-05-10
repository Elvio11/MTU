import asyncio
import json
import pytest
import runpy
import uuid
import time
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.heracles import HeraclesAgent

CONFIG = {
    "trading": {
        "daily_loss_limit_sol": 1.0
    }
}

@pytest.fixture
def agent():
    a = HeraclesAgent(CONFIG)
    a.redis = AsyncMock()
    return a

@pytest.mark.asyncio
async def test_heracles_connect_redis():
    a = HeraclesAgent(CONFIG)
    mock_redis = AsyncMock()
    with patch("aioredis.from_url", side_effect=AsyncMock(return_value=mock_redis)):
        await a.connect_redis()
        assert a.redis == mock_redis

@pytest.mark.asyncio
async def test_heracles_handle_health_check(agent):
    corr_id = str(uuid.uuid4())
    envelope = json.dumps({
        "agent_id": "AGT-01",
        "event_type": "health_check",
        "payload": {"status": "healthy"},
        "correlation_id": corr_id
    })
    await agent.handle_health_check(envelope)
    assert "AGT-01" in agent.agent_health

@pytest.mark.asyncio
async def test_heracles_check_health_timeout(agent):
    agent.agent_health = {"AGT-01": 0} # Very old
    agent.trigger_killswitch = AsyncMock()
    await agent.check_agent_health()
    agent.trigger_killswitch.assert_awaited_once()

@pytest.mark.asyncio
async def test_heracles_run_loop(agent):
    agent.connect_redis = AsyncMock()
    agent.check_agent_health = AsyncMock()
    async def stop_after_one(*args, **kwargs):
        agent.running = False
        return None
    with patch("src.python.agents.heracles.asyncio.sleep", side_effect=stop_after_one):
        await agent.run()
    agent.check_agent_health.assert_called()
    agent.redis.publish.assert_called()

@pytest.mark.asyncio
async def test_heracles_stop(agent):
    await agent.stop()
    agent.redis.close.assert_awaited_once()
    assert agent.running is False

def test_heracles_main_keyboard_interrupt():
    import runpy
    m = mock_open(read_data="trading:\n  daily_loss_limit_sol: 1.0\n")
    with patch("src.python.agents.heracles.open", m), \
         patch("src.python.agents.heracles.HeraclesAgent") as mock_agent_class, \
         patch("src.python.agents.heracles.validate_config", return_value=(True, None)), \
         patch("src.python.agents.heracles.asyncio.run", side_effect=[KeyboardInterrupt(), None]) as mock_run:
        mock_agent_instance = mock_agent_class.return_value
        try:
            runpy.run_module("src.python.agents.heracles", run_name="__main__")
        except SystemExit:
            pass
        assert mock_run.call_count == 2
        mock_agent_instance.run.assert_called()
        mock_agent_instance.stop.assert_called()
