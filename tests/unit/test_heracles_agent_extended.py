import pytest
import asyncio
import os
import yaml
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.heracles import HeraclesAgent, main as heracles_main

CONFIG = {
    "trading": {
        "daily_loss_limit_sol": -1.0
    }
}

@pytest.fixture
def agent():
    a = HeraclesAgent(CONFIG)
    a.redis = AsyncMock()
    return a

@pytest.mark.asyncio
async def test_heracles_telegram_error(agent):
    with patch("os.getenv", side_effect=lambda k, d=None: "token" if k=="TELEGRAM_BOT_TOKEN" else "chat_id" if k=="TELEGRAM_ADMIN_CHAT_ID" else d):
        agent.api_manager.request = AsyncMock(side_effect=Exception("telegram fail"))
        await agent.send_telegram_alert("test")
        # Should catch and print

@pytest.mark.asyncio
async def test_heracles_check_mainnet_readiness(agent):
    # Less than 50 trades
    agent.paper_trades = [MagicMock()] * 10
    assert agent.check_mainnet_readiness() is False
    
    # 50 trades, low win rate
    mock_trade = MagicMock()
    mock_trade.payload = {"realised_pnl_sol": -0.1}
    agent.paper_trades = [mock_trade] * 50
    assert agent.check_mainnet_readiness() is False
    
    # 50 trades, high win rate
    mock_win = MagicMock()
    mock_win.payload = {"realised_pnl_sol": 1.0}
    agent.paper_trades = [mock_win] * 50
    # win_rate = 1.0, sharpe = 0.6
    assert agent.check_mainnet_readiness() is True

@pytest.mark.asyncio
async def test_heracles_run_operational_window(agent):
    agent.running = True
    call_count = 0
    async def sleep_side_effect(seconds):
        nonlocal call_count
        call_count += 1
        agent.running = False
        return None

    with patch("src.python.agents.heracles.is_operational_window_active", return_value=False), \
         patch("src.python.agents.heracles.asyncio.sleep", side_effect=sleep_side_effect) as mock_sleep, \
         patch.object(agent, "connect_redis", AsyncMock()):
        await agent.run()
        assert mock_sleep.called
        assert mock_sleep.call_args[0][0] == 60

@pytest.mark.asyncio
async def test_heracles_run_loop_error(agent):
    agent.running = True
    async def run_side_effect():
        agent.running = False
        raise Exception("loop fail")

    with patch.object(agent, "check_agent_health", side_effect=run_side_effect), \
         patch.object(agent, "connect_redis", AsyncMock()), \
         patch("src.python.agents.heracles.asyncio.sleep", AsyncMock()):
        await agent.run()

@pytest.mark.asyncio
async def test_heracles_main_validation_error():
    m = mock_open(read_data="trading: {}")
    with patch("src.python.agents.heracles.open", m), \
         patch("src.python.agents.heracles.yaml.safe_load", return_value={}), \
         patch("src.python.agents.heracles.validate_config", return_value=(False, "invalid")), \
         patch("sys.exit", side_effect=SystemExit(1)):
        with pytest.raises(SystemExit):
            await heracles_main()

@pytest.mark.asyncio
async def test_heracles_main_success():
    m = mock_open(read_data="trading: {}")
    with patch("src.python.agents.heracles.open", m), \
         patch("src.python.agents.heracles.validate_config", return_value=(True, "")), \
         patch("src.python.agents.heracles.HeraclesAgent.run", side_effect=KeyboardInterrupt), \
         patch("src.python.agents.heracles.HeraclesAgent.stop", AsyncMock()):
        await heracles_main()
