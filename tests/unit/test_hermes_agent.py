import json
import uuid
import asyncio
import pytest
import yaml
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.hermes import HermesAgent, main as hermes_main
from src.python.shared.constants import EVENT_TOKEN_RECEIVED

CONFIG = {
    "system": {
        "environment": "paper"
    },
    "hermes": {
        "channel_whitelist": ["test-channel"]
    }
}

@pytest.fixture
def hermes_agent():
    a = HermesAgent(CONFIG)
    a.redis = AsyncMock()
    return a

@pytest.mark.asyncio
async def test_hermes_connect_redis(hermes_agent):
    # Mock from_url to return a coroutine that returns an AsyncMock
    mock_redis_instance = AsyncMock()
    with patch("src.python.agents.hermes.aioredis.from_url", AsyncMock(return_value=mock_redis_instance)):
        await hermes_agent.connect_redis()
        assert hermes_agent.redis is not None
        assert hermes_agent.priority_queue is not None

@pytest.mark.asyncio
async def test_hermes_handle_token_detected_success(hermes_agent):
    msg = {
        "agent_id": "AGT-01",
        "event_type": "token_detected",
        "payload": {"symbol": "TEST", "mint": "mint123"},
        "correlation_id": str(uuid.uuid4()),
        "envelope_id": str(uuid.uuid4()),
        "timestamp_utc": "2024-01-01T00:00:00Z"
    }
    await hermes_agent.handle_token_detected(json.dumps(msg))
    assert hermes_agent.redis.publish.called

@pytest.mark.asyncio
async def test_hermes_handle_token_detected_error(hermes_agent):
    await hermes_agent.handle_token_detected("invalid-json")
    # Should log error and not crash

@pytest.mark.asyncio
async def test_hermes_handle_token_migrated_success(hermes_agent):
    hermes_agent.redis = AsyncMock()
    envelope = {
        "agent_id": "AGT-03", "event_type": "token_migrated",
        "payload": {"mint": "m123", "symbol": "SYM", "name": "Name"},
        "correlation_id": str(uuid.uuid4()), "envelope_id": str(uuid.uuid4()), "timestamp_utc": "2024-01-01T00:00:00Z"
    }
    await hermes_agent.handle_token_migrated(json.dumps(envelope))
    assert hermes_agent.redis.publish.called

@pytest.mark.asyncio
async def test_hermes_handle_token_migrated_error(hermes_agent):
    with patch("src.python.agents.hermes.AgentMessageEnvelope.model_validate_json", side_effect=Exception("parse error")):
        await hermes_agent.handle_token_migrated("{}")

@pytest.mark.asyncio
async def test_hermes_run_loop(hermes_agent):
    hermes_agent.connect_redis = AsyncMock()
    hermes_agent.priority_queue = AsyncMock()
    hermes_agent.priority_queue.dequeue.return_value = None
    
    call_count = 0
    async def stop_loop(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1: hermes_agent.running = False
        return None
    
    with patch("src.python.agents.hermes.is_operational_window_active", return_value=True), \
         patch("src.python.agents.hermes.asyncio.sleep", side_effect=stop_loop):
        await hermes_agent.run()
    assert hermes_agent.running is False

@pytest.mark.asyncio
async def test_hermes_run_off_hours(hermes_agent):
    hermes_agent.connect_redis = AsyncMock()
    hermes_agent.priority_queue = AsyncMock()
    
    call_count = 0
    async def stop_loop(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        hermes_agent.running = False
        return None
    
    with patch("src.python.agents.hermes.is_operational_window_active", return_value=False), \
         patch("src.python.agents.hermes.asyncio.sleep", side_effect=stop_loop):
        await hermes_agent.run()

@pytest.mark.asyncio
async def test_hermes_run_dequeue_string(hermes_agent):
    hermes_agent.connect_redis = AsyncMock()
    hermes_agent.priority_queue = AsyncMock()
    # Return a string instead of a dict
    hermes_agent.priority_queue.dequeue = AsyncMock(side_effect=[("raw_string", 1), Exception("stop")])
    hermes_agent.handle_token_detected = AsyncMock()
    
    call_count = 0
    async def sleep_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 2: hermes_agent.running = False
        return None

    with patch("src.python.agents.hermes.is_operational_window_active", return_value=True), \
         patch("src.python.agents.hermes.asyncio.sleep", side_effect=sleep_side_effect):
        try:
            await hermes_agent.run()
        except Exception as e:
            if str(e) != "stop": raise
    
    hermes_agent.handle_token_detected.assert_called()

@pytest.mark.asyncio
async def test_hermes_run_dequeue_dict(hermes_agent):
    hermes_agent.connect_redis = AsyncMock()
    hermes_agent.priority_queue = AsyncMock()
    # Return a dict
    hermes_agent.priority_queue.dequeue = AsyncMock(side_effect=[({"payload": "data"}, 1), Exception("stop")])
    hermes_agent.handle_token_detected = AsyncMock()
    
    call_count = 0
    async def sleep_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 2: hermes_agent.running = False
        return None

    with patch("src.python.agents.hermes.is_operational_window_active", return_value=True), \
         patch("src.python.agents.hermes.asyncio.sleep", side_effect=sleep_side_effect):
        try:
            await hermes_agent.run()
        except Exception as e:
            if str(e) != "stop": raise
    
    hermes_agent.handle_token_detected.assert_called()

@pytest.mark.asyncio
async def test_hermes_run_loop_exception(hermes_agent):
    hermes_agent.connect_redis = AsyncMock()
    hermes_agent.priority_queue = AsyncMock()
    hermes_agent.priority_queue.dequeue = AsyncMock(side_effect=Exception("queue fail"))
    
    call_count = 0
    def stop_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1: hermes_agent.running = False
        return None

    with patch("src.python.agents.hermes.is_operational_window_active", return_value=True), \
         patch("src.python.agents.hermes.asyncio.sleep", side_effect=stop_side_effect):
        await hermes_agent.run()
    
    assert hermes_agent.priority_queue.dequeue.called

@pytest.mark.asyncio
async def test_hermes_stop(hermes_agent):
    hermes_agent.pubsub = AsyncMock()
    hermes_agent.redis = AsyncMock()
    await hermes_agent.stop()
    assert hermes_agent.pubsub.unsubscribe.called
    assert hermes_agent.redis.close.called

@pytest.mark.asyncio
async def test_hermes_main_config_error():
    m = mock_open()
    with patch("src.python.agents.hermes.open", m), \
         patch("src.python.agents.hermes.yaml.safe_load", side_effect=Exception("load error")), \
         patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        with pytest.raises(SystemExit):
            await hermes_main()

@pytest.mark.asyncio
async def test_hermes_main_validation_error():
    m = mock_open(read_data="hermes: {}")
    with patch("src.python.agents.hermes.open", m), \
         patch("src.python.agents.hermes.validate_config", return_value=(False, "error")), \
         patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        with pytest.raises(SystemExit):
            await hermes_main()

@pytest.mark.asyncio
async def test_hermes_main_keyboard_interrupt():
    m = mock_open(read_data="system: {environment: paper}")
    with patch("src.python.agents.hermes.open", m), \
         patch("src.python.agents.hermes.validate_config", return_value=(True, "")), \
         patch("src.python.agents.hermes.HermesAgent.run", side_effect=KeyboardInterrupt), \
         patch("src.python.agents.hermes.HermesAgent.stop", return_value=None) as mock_stop:
        await hermes_main()
        assert mock_stop.called
