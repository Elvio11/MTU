import pytest
import asyncio
import json
import time
import runpy
import yaml
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
from src.python.agents.heracles import HeraclesAgent
from src.python.shared.envelope import AgentMessageEnvelope

@pytest.fixture
def mock_redis():
    with patch("aioredis.from_url", new_callable=AsyncMock) as mock:
        mock_instance = AsyncMock()
        mock_instance.publish = AsyncMock()
        mock_instance.close = AsyncMock()
        mock.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_config():
    return {
        "trading": {
            "daily_loss_limit_sol": -1.0
        }
    }

@pytest.mark.asyncio
async def test_heracles_connect_redis(mock_redis, mock_config):
    agent = HeraclesAgent(mock_config)
    await agent.connect_redis()
    assert agent.redis is not None

@pytest.mark.asyncio
async def test_heracles_handle_health_check(mock_config):
    agent = HeraclesAgent(mock_config)
    envelope = AgentMessageEnvelope(
        agent_id="AGT-01",
        event_type="health_check",
        payload={"status": "healthy"},
        correlation_id="550e8400-e29b-41d4-a716-446655440000"
    )
    await agent.handle_health_check(envelope.model_dump_json())
    assert "AGT-01" in agent.agent_health

@pytest.mark.asyncio
async def test_heracles_handle_health_check_error(mock_config):
    agent = HeraclesAgent(mock_config)
    await agent.handle_health_check("invalid-json")

@pytest.mark.asyncio
async def test_heracles_handle_position_closed(mock_redis, mock_config):
    with patch("src.python.agents.heracles.is_paper_mode", return_value=True):
        agent = HeraclesAgent(mock_config)
        agent.redis = mock_redis
        agent.send_telegram_alert = AsyncMock()
        
        envelope = AgentMessageEnvelope(
            agent_id="AGT-06",
            event_type="position_closed",
            payload={"realised_pnl_sol": -2.0},
            correlation_id="550e8400-e29b-41d4-a716-446655440000"
        )
        
        await agent.handle_position_closed(envelope.model_dump_json())
        assert agent.daily_pnl == -2.0
        assert len(agent.paper_trades) == 1
        agent.send_telegram_alert.assert_called()

@pytest.mark.asyncio
async def test_heracles_handle_position_closed_error(mock_config):
    agent = HeraclesAgent(mock_config)
    await agent.handle_position_closed("invalid-json")

@pytest.mark.asyncio
async def test_heracles_check_agent_health(mock_redis, mock_config):
    agent = HeraclesAgent(mock_config)
    agent.redis = mock_redis
    agent.send_telegram_alert = AsyncMock()
    
    # Mock an unresponsive agent
    agent.agent_health["AGT-01"] = time.time() - 60
    
    await agent.check_agent_health()
    assert "AGT-01" not in agent.agent_health
    agent.send_telegram_alert.assert_called()

@pytest.mark.asyncio
async def test_heracles_send_telegram_alert(mock_config):
    with patch("os.getenv") as mock_env:
        mock_env.side_effect = lambda k, d=None: "test-token" if k == "TELEGRAM_BOT_TOKEN" else "test-chat-id"
        
        with patch("aiohttp.ClientSession.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value.__aenter__.return_value = AsyncMock()
            
            agent = HeraclesAgent(mock_config)
            await agent.send_telegram_alert("Test message")
            
            # Note: We can't easily check mock_get call if ClientSession is created inside
            # But we can patch aiohttp.ClientSession itself

@pytest.mark.asyncio
async def test_heracles_send_telegram_alert_real(mock_config):
    with patch("os.getenv", side_effect=["test-token", "test-chat-id"]):
        with patch("aiohttp.ClientSession") as mock_session:
            mock_session_instance = mock_session.return_value.__aenter__.return_value
            mock_session_instance.get = AsyncMock()
            
            agent = HeraclesAgent(mock_config)
            await agent.send_telegram_alert("Test message")
            mock_session_instance.get.assert_called()

@pytest.mark.asyncio
async def test_heracles_send_telegram_alert_error(mock_config):
    with patch("os.getenv", side_effect=Exception("Env error")):
        agent = HeraclesAgent(mock_config)
        await agent.send_telegram_alert("Test message")

def test_heracles_check_mainnet_readiness(mock_config):
    agent = HeraclesAgent(mock_config)
    
    # Case 1: < 50 trades
    assert agent.check_mainnet_readiness() is False
    
    # Case 2: 50 trades, win rate > 0.4
    for i in range(30):
        agent.paper_trades.append(MagicMock(payload={"realised_pnl_sol": 1.0}))
    for i in range(20):
        agent.paper_trades.append(MagicMock(payload={"realised_pnl_sol": -1.0}))
    
    # win_rate = 30/50 = 0.6 > 0.4
    # sharpe = 0.6
    assert agent.check_mainnet_readiness() is True
    
    # Case 3: 50 trades, win rate < 0.4
    agent.paper_trades = []
    for i in range(10):
        agent.paper_trades.append(MagicMock(payload={"realised_pnl_sol": 1.0}))
    for i in range(40):
        agent.paper_trades.append(MagicMock(payload={"realised_pnl_sol": -1.0}))
    # win_rate = 10/50 = 0.2 < 0.4
    # sharpe = 0.3
    assert agent.check_mainnet_readiness() is False

@pytest.mark.asyncio
async def test_heracles_run_loop(mock_redis, mock_config):
    agent = HeraclesAgent(mock_config)
    agent.redis = mock_redis
    
    # Control the loop with a patch on asyncio.sleep
    with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
        try:
            await agent.run()
        except asyncio.CancelledError:
            pass
            
    assert agent.running is True
    assert mock_redis.publish.called

@pytest.mark.asyncio
async def test_heracles_stop(mock_redis, mock_config):
    agent = HeraclesAgent(mock_config)
    agent.redis = mock_redis
    await agent.stop()
    assert agent.running is False
    mock_redis.close.assert_called_once()

def test_heracles_main_keyboard_interrupt(mock_config):
    with patch("yaml.safe_load", return_value=mock_config):
        with patch("builtins.open", mock_open(read_data="config")):
            with patch("src.python.agents.heracles.HeraclesAgent.run", side_effect=KeyboardInterrupt):
                with patch("src.python.agents.heracles.HeraclesAgent.stop", new_callable=AsyncMock) as mock_stop:
                    with patch("asyncio.run") as mock_asyncio_run:
                        mock_asyncio_run.side_effect = [KeyboardInterrupt(), None]
                        runpy.run_module("src.python.agents.heracles", run_name="__main__")
                        assert mock_asyncio_run.call_count == 2
