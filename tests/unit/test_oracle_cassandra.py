import pytest
import os
import sys
import json
import runpy
import uuid
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
import asyncio
from src.python.agents.oracle import OracleAgent
from src.python.agents.cassandra import CassandraAgent

# --- Oracle Tests ---

@pytest.mark.asyncio
async def test_oracle_agent_init():
    config = {"system": {"environment": "paper"}}
    agent = OracleAgent(config)
    assert agent.config == config

@pytest.mark.asyncio
async def test_oracle_agent_connect_redis():
    config = {"system": {"environment": "paper"}}
    agent = OracleAgent(config)
    
    mock_redis = MagicMock()
    mock_pubsub = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    mock_pubsub.subscribe = AsyncMock()
    
    with patch("src.python.agents.oracle.aioredis.from_url", side_effect=AsyncMock(return_value=mock_redis)):
        await agent.connect_redis()
        assert agent.redis == mock_redis
        assert agent.pubsub == mock_pubsub

@pytest.mark.asyncio
async def test_oracle_handle_position_opened():
    config = {"system": {"environment": "paper"}}
    agent = OracleAgent(config)
    agent.redis = AsyncMock()
    
    payload = {
        "mint": "fake_mint",
        "symbol": "FAKE",
        "position_id": "pos_1",
        "entry_price": 0.1
    }
    corr_id = str(uuid.uuid4())
    envelope = json.dumps({
        "agent_id": "AGT-07",
        "event_type": "position_opened",
        "payload": payload,
        "correlation_id": corr_id
    })
    
    await agent.handle_position_opened(envelope)
    assert "pos_1" in agent.positions

@pytest.mark.asyncio
async def test_oracle_run_loop():
    config = {"system": {"environment": "paper"}}
    agent = OracleAgent(config)
    agent.redis = AsyncMock()
    agent.pubsub = MagicMock()
    agent.connect_redis = AsyncMock()
    corr_id = str(uuid.uuid4())
    
    async def get_msg_then_stop(*args, **kwargs):
        agent.running = False
        return {"data": json.dumps({"agent_id": "AGT-07", "event_type": "position_opened", "payload": {"mint": "fake", "position_id": "pos_1"}, "correlation_id": corr_id})}
        
    agent.pubsub.get_message = AsyncMock(side_effect=get_msg_then_stop)
    
    with patch.object(agent, "handle_position_opened", return_value=None) as mock_handle, \
         patch.object(agent, "update_position_price", return_value=None), \
         patch("src.python.agents.oracle.asyncio.sleep", return_value=None):
        await agent.run()
        mock_handle.assert_called_once()

# --- Cassandra Tests ---

@pytest.mark.asyncio
async def test_cassandra_agent_init():
    config = {"system": {"environment": "paper"}}
    agent = CassandraAgent(config)
    assert agent.config == config

@pytest.mark.asyncio
async def test_cassandra_agent_connect_redis():
    config = {"system": {"environment": "paper"}}
    agent = CassandraAgent(config)
    
    mock_redis = MagicMock()
    mock_pubsub = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    mock_pubsub.subscribe = AsyncMock()
    
    with patch("src.python.agents.cassandra.aioredis.from_url", side_effect=AsyncMock(return_value=mock_redis)):
        await agent.connect_redis()
        assert agent.redis == mock_redis
        assert agent.pubsub == mock_pubsub

@pytest.mark.asyncio
async def test_cassandra_handle_token_received():
    config = {"system": {"environment": "paper"}}
    agent = CassandraAgent(config)
    agent.redis = AsyncMock()
    
    payload = {
        "mint": "fake_mint",
        "symbol": "FAKE"
    }
    corr_id = str(uuid.uuid4())
    envelope = json.dumps({
        "agent_id": "AGT-03",
        "event_type": "token_received",
        "payload": payload,
        "correlation_id": corr_id
    })
    
    with patch.object(agent, "score_sentiment", return_value=80), \
         patch.object(agent, "score_social_signals", return_value=70):
        await agent.handle_token_received(envelope)
        agent.redis.publish.assert_called()

@pytest.mark.asyncio
async def test_cassandra_run_loop():
    config = {"system": {"environment": "paper"}}
    agent = CassandraAgent(config)
    agent.redis = AsyncMock()
    agent.pubsub = MagicMock()
    agent.connect_redis = AsyncMock()
    corr_id = str(uuid.uuid4())
    
    async def get_msg_then_stop(*args, **kwargs):
        agent.running = False
        return {"data": json.dumps({"agent_id": "AGT-03", "event_type": "token_received", "payload": {"mint": "fake"}, "correlation_id": corr_id})}
        
    agent.pubsub.get_message = AsyncMock(side_effect=get_msg_then_stop)
    
    with patch.object(agent, "handle_token_received", return_value=None) as mock_handle, \
         patch("src.python.agents.cassandra.asyncio.sleep", return_value=None):
        await agent.run()
        mock_handle.assert_called_once()

# --- Entry Point Tests ---

def test_cassandra_main_keyboard_interrupt():
    import runpy
    m = mock_open(read_data="system:\n  environment: paper\n")
    with patch("src.python.agents.cassandra.open", m), \
         patch("src.python.agents.cassandra.CassandraAgent") as mock_agent_class, \
         patch("src.python.agents.cassandra.validate_config", return_value=(True, None)), \
         patch("src.python.agents.cassandra.asyncio.run", side_effect=[KeyboardInterrupt(), None]) as mock_run:
        
        mock_agent_instance = mock_agent_class.return_value
        try:
            runpy.run_module("src.python.agents.cassandra", run_name="__main__")
        except SystemExit:
            pass
        
        assert mock_run.call_count == 2
        mock_agent_instance.run.assert_called()
        mock_agent_instance.stop.assert_called()

def test_oracle_main_keyboard_interrupt():
    import runpy
    m = mock_open(read_data="system:\n  environment: paper\n")
    with patch("src.python.agents.oracle.open", m), \
         patch("src.python.agents.oracle.OracleAgent") as mock_agent_class, \
         patch("src.python.agents.oracle.validate_config", return_value=(True, None)), \
         patch("src.python.agents.oracle.asyncio.run", side_effect=[KeyboardInterrupt(), None]) as mock_run:
        
        mock_agent_instance = mock_agent_class.return_value
        try:
            runpy.run_module("src.python.agents.oracle", run_name="__main__")
        except SystemExit:
            pass
        
        assert mock_run.call_count == 2
        mock_agent_instance.run.assert_called()
        mock_agent_instance.stop.assert_called()
