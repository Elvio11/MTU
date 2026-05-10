import pytest
import asyncio
import json
import runpy
from unittest.mock import MagicMock, AsyncMock, patch
from src.python.agents.hermes import HermesAgent
from src.python.shared.envelope import AgentMessageEnvelope

@pytest.fixture
def mock_redis():
    with patch("aioredis.from_url", new_callable=AsyncMock) as mock:
        mock_instance = AsyncMock()
        mock_instance.publish = AsyncMock()
        mock_instance.lpush = AsyncMock()
        mock_instance.close = AsyncMock()
        mock.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_priority_queue():
    with patch("src.python.agents.hermes.PriorityQueue") as mock:
        mock_instance = MagicMock()
        mock_instance.dequeue = AsyncMock()
        mock.return_value = mock_instance
        yield mock_instance

@pytest.mark.asyncio
async def test_hermes_connect_redis(mock_redis):
    agent = HermesAgent()
    await agent.connect_redis()
    assert agent.redis is not None
    assert agent.priority_queue is not None

@pytest.mark.asyncio
async def test_hermes_handle_token_detected(mock_redis):
    agent = HermesAgent()
    agent.redis = mock_redis
    
    envelope = AgentMessageEnvelope(
        agent_id="AGT-01",
        event_type="token_detected",
        payload={"mint": "test-mint", "symbol": "TEST"},
        correlation_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    await agent.handle_token_detected(envelope.model_dump_json())
    
    assert mock_redis.publish.call_count == 2
    assert mock_redis.lpush.call_count == 2

@pytest.mark.asyncio
async def test_hermes_handle_token_detected_error(mock_redis):
    agent = HermesAgent()
    # Invalid JSON should trigger exception handling
    await agent.handle_token_detected("invalid-json")

@pytest.mark.asyncio
async def test_hermes_handle_token_migrated(mock_redis):
    agent = HermesAgent()
    agent.redis = mock_redis
    
    envelope = AgentMessageEnvelope(
        agent_id="AGT-01",
        event_type="token_migrated",
        payload={"mint": "test-mint", "name": "Test Token", "symbol": "TEST"},
        correlation_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    await agent.handle_token_migrated(envelope.model_dump_json())
    
    assert mock_redis.publish.call_count == 2
    assert mock_redis.lpush.call_count == 2

@pytest.mark.asyncio
async def test_hermes_handle_token_migrated_error(mock_redis):
    agent = HermesAgent()
    # Invalid JSON should trigger exception handling
    await agent.handle_token_migrated("invalid-json")

@pytest.mark.asyncio
async def test_hermes_run_loop(mock_redis, mock_priority_queue):
    agent = HermesAgent()
    
    envelope = AgentMessageEnvelope(
        agent_id="AGT-01",
        event_type="token_detected",
        payload={"mint": "test-mint", "symbol": "TEST"},
        correlation_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # Mock dequeue to return a message then None
    mock_priority_queue.dequeue.side_effect = [
        (envelope.model_dump(), 1),
        (envelope.model_dump_json(), 2), # Test string path too
        None,
        asyncio.CancelledError()
    ]
    
    agent.handle_token_detected = AsyncMock()
    
    try:
        await asyncio.wait_for(agent.run(), timeout=0.2)
    except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
        pass
        
@pytest.mark.asyncio
async def test_hermes_run_loop_exception(mock_redis, mock_priority_queue):
    agent = HermesAgent()
    
    # Mock dequeue to raise an exception once, then CancelledError
    mock_priority_queue.dequeue.side_effect = [
        Exception("Test error"),
        asyncio.CancelledError()
    ]
    
    try:
        await asyncio.wait_for(agent.run(), timeout=0.1)
    except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
        pass
        
    assert agent.running is True
    await agent.stop()

@pytest.mark.asyncio
async def test_hermes_stop(mock_redis):
    agent = HermesAgent()
    agent.redis = mock_redis
    agent.pubsub = AsyncMock()
    
    await agent.stop()
    assert agent.running is False
    agent.pubsub.unsubscribe.assert_called_once()
    mock_redis.close.assert_called_once()

def test_hermes_main_keyboard_interrupt():
    with patch("src.python.agents.hermes.HermesAgent.run", side_effect=KeyboardInterrupt):
        with patch("src.python.agents.hermes.HermesAgent.stop", new_callable=AsyncMock) as mock_stop:
            with patch("asyncio.run") as mock_asyncio_run:
                mock_asyncio_run.side_effect = [KeyboardInterrupt(), None]
                runpy.run_module("src.python.agents.hermes", run_name="__main__")
                assert mock_asyncio_run.call_count == 2
