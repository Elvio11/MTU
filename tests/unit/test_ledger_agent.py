import pytest
import asyncio
import json
import sqlite3
import runpy
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
from src.python.agents.ledger import LedgerAgent
from src.python.shared.envelope import AgentMessageEnvelope, EventType

@pytest.fixture
def mock_redis():
    with patch("aioredis.from_url", new_callable=AsyncMock) as mock:
        mock_instance = AsyncMock()
        mock_pubsub = MagicMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.get_message = AsyncMock()
        # Ensure pubsub() is a regular mock call, not a coroutine
        mock_instance.pubsub = MagicMock(return_value=mock_pubsub)
        mock_instance.close = AsyncMock()
        mock.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_sqlite():
    with patch("sqlite3.connect") as mock:
        mock_conn = MagicMock()
        mock.return_value = mock_conn
        yield mock_conn

@pytest.mark.asyncio
async def test_ledger_connect_db(mock_sqlite):
    agent = LedgerAgent()
    agent.connect_db()
    assert agent.db is not None
    agent.db.execute.assert_called()
    agent.db.commit.assert_called()

@pytest.mark.asyncio
async def test_ledger_connect_redis(mock_redis):
    agent = LedgerAgent()
    await agent.connect_redis()
    assert agent.redis is not None
    agent.redis.pubsub.assert_called_once()
    agent.pubsub.subscribe.assert_called_once()

@pytest.mark.asyncio
async def test_ledger_write_audit_log(mock_sqlite):
    agent = LedgerAgent()
    agent.db = mock_sqlite
    agent.audit_file = MagicMock()
    
    envelope = AgentMessageEnvelope(
        agent_id="AGT-09",
        event_type="token_detected",
        payload={"test": "data"},
        correlation_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    agent.write_audit_log(envelope)
    
    mock_sqlite.execute.assert_called_once()
    mock_sqlite.commit.assert_called_once()
    agent.audit_file.write.assert_called_once()
    agent.audit_file.flush.assert_called_once()

@pytest.mark.asyncio
async def test_ledger_handle_event():
    agent = LedgerAgent()
    agent.write_audit_log = MagicMock()
    
    envelope = AgentMessageEnvelope(
        agent_id="AGT-09",
        event_type="token_detected",
        payload={"test": "data"},
        correlation_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    await agent.handle_event("test-channel", envelope.model_dump_json())
    agent.write_audit_log.assert_called_once()

@pytest.mark.asyncio
async def test_ledger_handle_event_error():
    agent = LedgerAgent()
    # Invalid JSON should trigger exception handling
    await agent.handle_event("test-channel", "invalid-json")
    # Should not raise exception but print error

@pytest.mark.asyncio
async def test_ledger_run_loop(mock_redis, mock_sqlite):
    agent = LedgerAgent()
    
    # Mock open for audit file
    m_open = mock_open()
    
    envelope = AgentMessageEnvelope(
        agent_id="AGT-09",
        event_type="token_detected",
        payload={"test": "data"},
        correlation_id="550e8400-e29b-41d4-a716-446655440000"
    )
    
    # Mock pubsub.get_message to return a message then None
    mock_pubsub = mock_redis.pubsub.return_value
    mock_pubsub.get_message.side_effect = [
        {"channel": "test", "data": envelope.model_dump_json()},
        None,
        asyncio.CancelledError() # To stop the loop
    ]
    
    with patch("builtins.open", m_open):
        try:
            await asyncio.wait_for(agent.run(), timeout=0.1)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            pass
            
    assert agent.running is True
    await agent.stop()

@pytest.mark.asyncio
async def test_ledger_stop(mock_redis, mock_sqlite):
    agent = LedgerAgent()
    agent.db = mock_sqlite
    agent.redis = mock_redis
    agent.audit_file = MagicMock()
    
    await agent.stop()
    assert agent.running is False
    mock_sqlite.close.assert_called_once()
    agent.audit_file.close.assert_called_once()
    mock_redis.close.assert_called_once()

@pytest.mark.asyncio
async def test_ledger_run_loop_exception(mock_redis, mock_sqlite):
    agent = LedgerAgent()
    m_open = mock_open()
    
    # Mock pubsub.get_message to raise an exception once, then CancelledError
    mock_pubsub = mock_redis.pubsub.return_value
    mock_pubsub.get_message.side_effect = [
        Exception("Test error"),
        asyncio.CancelledError()
    ]
    
    with patch("builtins.open", m_open):
        try:
            await asyncio.wait_for(agent.run(), timeout=0.1)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            pass
    
    assert agent.running is True
    await agent.stop()

def test_ledger_main_keyboard_interrupt():
    with patch("src.python.agents.ledger.LedgerAgent.run", side_effect=KeyboardInterrupt):
        with patch("src.python.agents.ledger.LedgerAgent.stop", new_callable=AsyncMock) as mock_stop:
            with patch("asyncio.run") as mock_asyncio_run:
                # First call to asyncio.run(agent.run()) raises KeyboardInterrupt
                # Second call should be asyncio.run(agent.stop())
                mock_asyncio_run.side_effect = [KeyboardInterrupt(), None]
                
                runpy.run_module("src.python.agents.ledger", run_name="__main__")
                
                assert mock_asyncio_run.call_count == 2
