import pytest
import os
import sys
import json
import runpy
import yaml
import uuid
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
import asyncio
from src.python.agents.anansi import AnansiAgent

@pytest.mark.asyncio
async def test_anansi_agent_init():
    config = {"system": {"environment": "paper"}}
    agent = AnansiAgent(config)
    assert agent.config == config
    assert agent.is_paper_mode is True

@pytest.mark.asyncio
async def test_anansi_agent_connect_redis():
    config = {"system": {"environment": "paper"}}
    agent = AnansiAgent(config)
    
    mock_redis = MagicMock()
    mock_pubsub = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    mock_pubsub.subscribe = AsyncMock()
    
    with patch("src.python.agents.anansi.aioredis.from_url", side_effect=AsyncMock(return_value=mock_redis)):
        await agent.connect_redis()
        assert agent.redis == mock_redis
        assert agent.pubsub == mock_pubsub
        mock_pubsub.subscribe.assert_awaited_once()

@pytest.mark.asyncio
async def test_anansi_agent_qualify_token_paper_success():
    config = {"system": {"environment": "paper"}, "qualification": {"min_market_cap_sol": 1, "max_market_cap_sol": 100, "min_bonding_curve_progress": 10}}
    agent = AnansiAgent(config)
    agent.redis = AsyncMock()
    
    token_payload = {
        "mint": "fake_mint",
        "symbol": "FAKE",
        "marketCapSol": 50,
        "bondingCurveProgress": 20
    }
    
    corr_id = str(uuid.uuid4())
    with patch.object(agent, "check_g1_mint_authority", return_value=True), \
         patch.object(agent, "check_g2_freeze_authority", return_value=True), \
         patch.object(agent, "check_g10_honeypot", return_value=True), \
         patch.object(agent, "check_g11_sentiment", return_value=True):
        
        result = await agent.qualify_token(token_payload, corr_id)
        assert result is True
        agent.redis.publish.assert_called()

@pytest.mark.asyncio
async def test_anansi_agent_qualify_token_paper_fail():
    config = {"system": {"environment": "paper"}, "qualification": {"min_market_cap_sol": 100}}
    agent = AnansiAgent(config)
    agent.redis = AsyncMock()
    
    token_payload = {
        "mint": "fake_mint",
        "symbol": "FAKE",
        "marketCapSol": 50, # Fails min_mcap
        "bondingCurveProgress": 20
    }
    
    corr_id = str(uuid.uuid4())
    result = await agent.qualify_token(token_payload, corr_id)
    assert result is False

@pytest.mark.asyncio
async def test_anansi_run_loop():
    config = {"system": {"environment": "paper"}}
    agent = AnansiAgent(config)
    agent.redis = AsyncMock()
    agent.pubsub = MagicMock()
    agent.connect_redis = AsyncMock()
    corr_id = str(uuid.uuid4())
    
    async def get_msg_then_stop(*args, **kwargs):
        agent.running = False
        return {"data": json.dumps({"agent_id": "AGT-01", "event_type": "token_received", "payload": {"mint": "fake"}, "correlation_id": corr_id})}
        
    agent.pubsub.get_message = AsyncMock(side_effect=get_msg_then_stop)
    
    with patch.object(agent, "qualify_token", return_value=True) as mock_qualify, \
         patch("src.python.agents.anansi.asyncio.sleep", return_value=None):
        await agent.run()
        mock_qualify.assert_called_once()

@pytest.mark.asyncio
async def test_anansi_stop():
    config = {"system": {"environment": "paper"}}
    agent = AnansiAgent(config)
    agent.redis = AsyncMock()
    agent.pubsub = AsyncMock()
    
    await agent.stop()
    agent.pubsub.unsubscribe.assert_awaited_once()
    agent.redis.close.assert_awaited_once()

def test_anansi_main_keyboard_interrupt():
    import runpy
    m = mock_open(read_data="system:\n  environment: paper\n")
    with patch("src.python.agents.anansi.open", m), \
         patch("src.python.agents.anansi.AnansiAgent") as mock_agent_class, \
         patch("src.python.agents.anansi.validate_config", return_value=(True, None)), \
         patch("src.python.agents.anansi.asyncio.run", side_effect=[KeyboardInterrupt(), None]) as mock_run:
        
        mock_agent_instance = mock_agent_class.return_value
        try:
            runpy.run_module("src.python.agents.anansi", run_name="__main__")
        except SystemExit:
            pass
        
        assert mock_run.call_count == 2
        mock_agent_instance.run.assert_called()
        mock_agent_instance.stop.assert_called()

def test_anansi_main_entry_point_error_loading_capsys(capsys):
    import runpy
    import builtins
    original_open = builtins.open
    def mocked_open(file, *args, **kwargs):
        if str(file).endswith("config.yaml"):
            raise Exception("load error")
        return original_open(file, *args, **kwargs)
    
    with patch("builtins.open", side_effect=mocked_open):
        with pytest.raises(SystemExit):
            runpy.run_module("src.python.agents.anansi", run_name="__main__")
        captured = capsys.readouterr()
        assert "[CONFIG] Error loading config: load error" in captured.out
