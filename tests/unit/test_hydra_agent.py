import asyncio
import json
import pytest
import os
import yaml
import runpy
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.hydra import HydraAgent
from src.python.shared.constants import CHANNEL_TOKEN_RECEIVED, EVENT_TOKEN_RECEIVED

CONFIG = {
    "hydra": {
        "polling_interval_seconds": 1,
        "min_bonding_curve_progress": 35.0
    }
}

@pytest.fixture
def agent():
    a = HydraAgent(CONFIG)
    a.redis = AsyncMock()
    return a

@pytest.mark.asyncio
async def test_hydra_connect_redis():
    a = HydraAgent(CONFIG)
    mock_redis = AsyncMock()
    with patch("src.python.agents.hydra.aioredis.from_url", side_effect=AsyncMock(return_value=mock_redis)):
        await a.connect_redis()
        assert a.redis == mock_redis

@pytest.mark.asyncio
async def test_hydra_fetch_trending_success(agent):
    with patch("src.python.agents.hydra.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [{"mint": "m1", "progress": 40}])
        tokens = await agent.fetch_trending_pumpfun()
        assert len(tokens) == 1
        assert tokens[0]["mint"] == "m1"

@pytest.mark.asyncio
async def test_hydra_fetch_trending_failure(agent):
    with patch("src.python.agents.hydra.requests.get", side_effect=Exception("api error")):
        tokens = await agent.fetch_trending_pumpfun()
        assert tokens == []

@pytest.mark.asyncio
async def test_hydra_process_token_qualified(agent):
    token = {"mint": "m1", "progress": 40.0, "symbol": "T1", "usd_market_cap": 10000}
    await agent.process_token(token)
    agent.redis.publish.assert_awaited_once()
    args, kwargs = agent.redis.publish.call_args
    assert args[0] == CHANNEL_TOKEN_RECEIVED
    msg = json.loads(args[1])
    assert msg["event_type"] == EVENT_TOKEN_RECEIVED
    assert msg["payload"]["mint"] == "m1"

@pytest.mark.asyncio
async def test_hydra_run_loop(agent):
    agent.connect_redis = AsyncMock()
    async def fetch_then_stop():
        agent.running = False
        return [{"mint": "m1", "progress": 40}]
    agent.fetch_trending_pumpfun = AsyncMock(side_effect=fetch_then_stop)
    agent.process_token = AsyncMock()
    with patch("src.python.agents.hydra.asyncio.sleep", return_value=None):
        await agent.run()
    agent.process_token.assert_awaited()

@pytest.mark.asyncio
async def test_hydra_stop(agent):
    await agent.stop()
    agent.redis.close.assert_awaited_once()
    assert agent.running is False

def test_hydra_main_keyboard_interrupt():
    import runpy
    m = mock_open(read_data="system:\n  environment: paper\n")
    with patch("src.python.agents.hydra.open", m), \
         patch("src.python.agents.hydra.HydraAgent") as mock_agent_class, \
         patch("src.python.shared.config_validator.load_schema", return_value=({}, None)), \
         patch("src.python.agents.hydra.asyncio.run", side_effect=[KeyboardInterrupt(), None]) as mock_run:
        mock_agent_instance = mock_agent_class.return_value
        try:
            runpy.run_module("src.python.agents.hydra", run_name="__main__")
        except SystemExit:
            pass
        assert mock_run.call_count == 2
        mock_agent_instance.run.assert_called_once()
        mock_agent_instance.stop.assert_called_once()
