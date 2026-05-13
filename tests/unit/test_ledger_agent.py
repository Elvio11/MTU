import json
import uuid
import asyncio
import pytest
import sqlite3
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from datetime import datetime, timedelta
from src.python.agents.ledger import LedgerAgent, main as ledger_main
from src.python.shared.constants import EVENT_TOKEN_DETECTED

CONFIG = {
    "system": {
        "environment": "paper"
    },
    "ledger": {
        "db_path": ":memory:",
        "audit_json_path": "data/audit_ledger.json"
    }
}

@pytest.fixture
def ledger_agent():
    # Use in-memory for testing
    agent = LedgerAgent(CONFIG)
    agent.db = sqlite3.connect(":memory:")
    agent.db.execute("""
        CREATE TABLE IF NOT EXISTS audit_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            envelope_id TEXT,
            agent_id TEXT,
            event_type TEXT,
            payload TEXT,
            timestamp_utc TEXT
        )
    """)
    # Add positions for cleanup test
    agent.db.execute("CREATE TABLE IF NOT EXISTS positions (position_id TEXT)")
    agent.db.commit()
    agent.audit_file = MagicMock()
    agent.redis = AsyncMock()
    agent.pubsub = AsyncMock()
    return agent

@pytest.mark.asyncio
async def test_ledger_connect_db(ledger_agent):
    with patch("src.python.agents.ledger.sqlite3.connect", return_value=MagicMock()) as mock_conn:
        ledger_agent.connect_db()
        assert mock_conn.called

@pytest.mark.asyncio
async def test_ledger_connect_redis(ledger_agent):
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_redis_instance = AsyncMock()
    # Explicitly use MagicMock for the pubsub call to avoid unintended coroutines
    mock_redis_instance.pubsub = MagicMock(return_value=mock_pubsub)
    
    with patch("src.python.agents.ledger.aioredis.from_url", AsyncMock(return_value=mock_redis_instance)):
        await ledger_agent.connect_redis()
        assert ledger_agent.redis is not None
        assert ledger_agent.pubsub is not None
        mock_pubsub.subscribe.assert_called()

@pytest.mark.asyncio
async def test_ledger_write_audit_log(ledger_agent):
    envelope = MagicMock()
    envelope.envelope_id = "env"
    envelope.agent_id = "agent"
    envelope.event_type = "event"
    envelope.payload = {"k": "v"}
    envelope.timestamp_utc = "2024-01-01T00:00:00Z"
    envelope.model_dump.return_value = {"dump": "data"}
    
    ledger_agent.write_audit_log(envelope)
    
    # Check SQLite
    res = ledger_agent.db.execute("SELECT count(*) FROM audit_ledger").fetchone()
    assert res[0] == 1
    # Check file
    assert ledger_agent.audit_file.write.called

@pytest.mark.asyncio
async def test_ledger_handle_event_success(ledger_agent):
    ledger_agent.write_audit_log = MagicMock()
    envelope = {
        "agent_id": "AGT-01", "event_type": EVENT_TOKEN_DETECTED,
        "payload": {}, "correlation_id": str(uuid.uuid4()),
        "envelope_id": str(uuid.uuid4()), "timestamp_utc": "2024-01-01T00:00:00Z"
    }
    await ledger_agent.handle_event("ch", json.dumps(envelope))
    assert ledger_agent.write_audit_log.called

@pytest.mark.asyncio
async def test_ledger_handle_event_error(ledger_agent):
    await ledger_agent.handle_event("ch", "invalid-json")

def test_ledger_rotate_audit_logs_success(ledger_agent):
    # Insert old record
    old_ts = (datetime.now() - timedelta(days=31)).isoformat()
    ledger_agent.db.execute("INSERT INTO audit_ledger (timestamp_utc) VALUES (?)", (old_ts,))
    # Insert stale positions
    ledger_agent.db.execute("INSERT INTO positions (position_id) VALUES ('pos_2')")
    ledger_agent.db.execute("INSERT INTO positions (position_id) VALUES ('pos_3')")
    ledger_agent.db.commit()
    
    ledger_agent.rotate_audit_logs()
    
    # Check audit deleted
    res = ledger_agent.db.execute("SELECT count(*) FROM audit_ledger WHERE timestamp_utc = ?", (old_ts,)).fetchone()
    assert res[0] == 0
    # Check positions deleted
    res = ledger_agent.db.execute("SELECT count(*) FROM positions WHERE position_id IN ('pos_2', 'pos_3')").fetchone()
    assert res[0] == 0

def test_ledger_rotate_audit_logs_exception(ledger_agent):
    ledger_agent.db = MagicMock()
    ledger_agent.db.execute.side_effect = Exception("db error")
    ledger_agent.rotate_audit_logs()

@pytest.mark.asyncio
async def test_ledger_run_loop(ledger_agent):
    ledger_agent.connect_db = MagicMock()
    ledger_agent.connect_redis = AsyncMock()
    ledger_agent.rotate_audit_logs = MagicMock()
    
    call_count = 0
    async def stop_loop(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1: ledger_agent.running = False
        return None
    
    with patch("src.python.agents.ledger.is_operational_window_active", return_value=True), \
         patch("src.python.agents.ledger.asyncio.sleep", side_effect=stop_loop), \
         patch("src.python.agents.ledger.open", mock_open()), \
         patch("src.python.agents.ledger.time.time", return_value=time.time()):
        await ledger_agent.run()
    assert ledger_agent.running is False

@pytest.mark.asyncio
async def test_ledger_run_window_logic(ledger_agent):
    ledger_agent.connect_db = MagicMock()
    ledger_agent.connect_redis = AsyncMock()
    ledger_agent.pubsub = AsyncMock()
    
    states = [False, True] # Off, then On
    def active_side_effect():
        if not states: return True
        return states.pop(0)

    call_count = 0
    async def sleep_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 2: ledger_agent.running = False
        return None

    with patch("src.python.agents.ledger.is_operational_window_active", side_effect=active_side_effect), \
         patch("src.python.agents.ledger.asyncio.sleep", side_effect=sleep_side_effect), \
         patch("src.python.agents.ledger.open", mock_open()):
        await ledger_agent.run()
    
    assert ledger_agent.pubsub.unsubscribe.called
    assert ledger_agent.pubsub.subscribe.called

@pytest.mark.asyncio
async def test_ledger_run_exception(ledger_agent):
    ledger_agent.connect_db = MagicMock()
    ledger_agent.rotate_audit_logs = MagicMock()
    
    call_count = 0
    async def stop_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1: ledger_agent.running = False
        return None

    # Trigger exception INSIDE the loop to hit the try/except
    with patch("src.python.agents.ledger.is_operational_window_active", side_effect=Exception("loop fail")), \
         patch("src.python.agents.ledger.asyncio.sleep", side_effect=stop_side_effect), \
         patch("src.python.agents.ledger.open", mock_open()):
        await ledger_agent.run()

@pytest.mark.asyncio
async def test_ledger_stop(ledger_agent):
    ledger_agent.db = MagicMock()
    ledger_agent.audit_file = MagicMock()
    ledger_agent.redis = AsyncMock()
    await ledger_agent.stop()
    assert ledger_agent.db.close.called
    assert ledger_agent.audit_file.close.called
    assert ledger_agent.redis.close.called

@pytest.mark.asyncio
async def test_ledger_main_config_error():
    m = mock_open()
    with patch("src.python.agents.ledger.open", m), \
         patch("src.python.agents.ledger.yaml.safe_load", side_effect=Exception("load error")), \
         patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        with pytest.raises(SystemExit):
            await ledger_main()

@pytest.mark.asyncio
async def test_ledger_main_validation_error():
    m = mock_open(read_data="ledger: {}")
    with patch("src.python.agents.ledger.open", m), \
         patch("src.python.agents.ledger.validate_config", return_value=(False, "error")), \
         patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        with pytest.raises(SystemExit):
            await ledger_main()

@pytest.mark.asyncio
async def test_ledger_main_keyboard_interrupt():
    m = mock_open(read_data="system: {environment: paper}")
    with patch("src.python.agents.ledger.open", m), \
         patch("src.python.agents.ledger.validate_config", return_value=(True, "")), \
         patch("src.python.agents.ledger.LedgerAgent.run", side_effect=KeyboardInterrupt), \
         patch("src.python.agents.ledger.LedgerAgent.stop", return_value=None) as mock_stop:
        await ledger_main()
        assert mock_stop.called
