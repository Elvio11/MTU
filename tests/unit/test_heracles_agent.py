import pytest
import asyncio
import time
import uuid
import yaml
import os
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.heracles import HeraclesAgent, main

@pytest.fixture
def agent():
    config = {
        "trading": {
            "daily_loss_limit_sol": -1.0
        }
    }
    a = HeraclesAgent(config)
    a.redis = AsyncMock()
    return a

@pytest.fixture
def mock_envelope():
    from src.python.shared.envelope import AgentMessageEnvelope
    return AgentMessageEnvelope(
        agent_id="AGT-01",
        event_type="health_check",
        payload={"status": "healthy"},
        correlation_id=str(uuid.uuid4())
    )

@pytest.mark.asyncio
async def test_heracles_connect_redis(agent):
    mock_redis = AsyncMock()
    with patch("aioredis.from_url", AsyncMock(return_value=mock_redis)):
        await agent.connect_redis()
        assert agent.redis == mock_redis

@pytest.mark.asyncio
async def test_heracles_handle_health_check(agent, mock_envelope):
    await agent.handle_health_check(mock_envelope.model_dump_json())
    assert "AGT-01" in agent.agent_health

@pytest.mark.asyncio
async def test_heracles_handle_position_closed(agent, mock_envelope):
    mock_envelope.payload = {"realised_pnl_sol": -0.5}
    await agent.handle_position_closed(mock_envelope.model_dump_json())
    assert agent.daily_pnl == -0.5

@pytest.mark.asyncio
async def test_heracles_handle_position_closed_limit(agent, mock_envelope):
    agent.trigger_killswitch = AsyncMock()
    mock_envelope.payload = {"realised_pnl_sol": -2.0}
    await agent.handle_position_closed(mock_envelope.model_dump_json())
    assert agent.daily_pnl == -2.0
    agent.trigger_killswitch.assert_called_once()

@pytest.mark.asyncio
async def test_heracles_check_agent_health(agent):
    agent.agent_health = {"AGT-01": time.time() - 40} # Expired
    agent.trigger_killswitch = AsyncMock()
    await agent.check_agent_health()
    agent.trigger_killswitch.assert_called_once()
    assert "AGT-01" not in agent.agent_health

@pytest.mark.asyncio
async def test_heracles_trigger_killswitch(agent):
    await agent.trigger_killswitch("test reason")
    agent.redis.publish.assert_called_once()

@pytest.mark.asyncio
async def test_heracles_run_loop(agent):
    agent.running = True
    def stop_loop(*args, **kwargs):
        agent.running = False
        return True

    with patch("src.python.agents.heracles.is_operational_window_active", side_effect=stop_loop), \
         patch("src.python.agents.heracles.asyncio.sleep", new_callable=AsyncMock):
        await agent.run()
    assert agent.running is False

@pytest.mark.asyncio
async def test_heracles_stop(agent):
    await agent.stop()
    assert agent.running is False
    agent.redis.close.assert_awaited_once()

@pytest.mark.asyncio
async def test_heracles_handle_health_check_exception(agent):
    await agent.handle_health_check("invalid")

@pytest.mark.asyncio
async def test_heracles_handle_position_closed_paper_mode(agent, mock_envelope):
    from src.python.shared.envelope import AgentMessageEnvelope
    with patch("src.python.agents.heracles.is_paper_mode", return_value=True):
        mock_envelope.payload = {"realised_pnl_sol": 0.1}
        await agent.handle_position_closed(mock_envelope.model_dump_json())
        assert len(agent.paper_trades) == 1
        assert agent.daily_pnl == 0.1

@pytest.mark.asyncio
async def test_heracles_handle_position_closed_exception(agent):
    await agent.handle_position_closed("invalid")

@pytest.mark.asyncio
async def test_heracles_main_config_error():
    m = mock_open()
    with patch("src.python.agents.heracles.open", m), \
         patch("src.python.agents.heracles.yaml.safe_load", side_effect=Exception("load error")), \
         patch("sys.exit", side_effect=SystemExit(1)):
        with pytest.raises(SystemExit):
            await main()

@pytest.mark.asyncio
async def test_heracles_main_keyboard_interrupt():
    m = mock_open(read_data="trading:\n  daily_loss_limit_sol: 1.0\n")
    with patch("src.python.agents.heracles.open", m), \
         patch("src.python.agents.heracles.validate_config", return_value=(True, None)), \
         patch("src.python.agents.heracles.HeraclesAgent.run", side_effect=KeyboardInterrupt), \
         patch("src.python.agents.heracles.HeraclesAgent.stop", return_value=None) as mock_stop:
        await main()
        assert mock_stop.called
