import asyncio
import json
import pytest
import runpy
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.ledger import LedgerAgent

CONFIG = {
    "ledger": {
        "log_path": "logs/trades.jsonl"
    }
}

@pytest.fixture
def agent():
    a = LedgerAgent(CONFIG)
    a.redis = AsyncMock()
    return a

@pytest.mark.asyncio
async def test_ledger_connect_redis():
    a = LedgerAgent(CONFIG)
    mock_redis = MagicMock()
    mock_pubsub = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    mock_pubsub.subscribe = AsyncMock()
    
    with patch("src.python.agents.ledger.aioredis.from_url", side_effect=AsyncMock(return_value=mock_redis)):
        await a.connect_redis()
        assert a.redis == mock_redis
        assert a.pubsub == mock_pubsub

@pytest.mark.asyncio
async def test_ledger_handle_trade_executed(agent):
    corr_id = str(uuid.uuid4())
    trade_info = {
        "mint": "m1",
        "action": "buy",
        "amount_sol": 0.1,
        "signature": "sig1"
    }
    envelope = json.dumps({
        "agent_id": "AGT-05",
        "event_type": "trade_executed",
        "payload": trade_info,
        "correlation_id": corr_id
    })
    
    m = mock_open()
    with patch("src.python.agents.ledger.open", m):
        await agent.handle_trade_executed(envelope)
        m().write.assert_called()

@pytest.mark.asyncio
async def test_ledger_run_loop(agent):
    agent.pubsub = MagicMock()
    agent.connect_redis = AsyncMock()
    corr_id = str(uuid.uuid4())
    async def get_msg_then_stop(*args, **kwargs):
        agent.running = False
        return {"data": json.dumps({"agent_id": "A", "event_type": "T", "payload": {}, "correlation_id": corr_id})}
        
    agent.pubsub.get_message = AsyncMock(side_effect=get_msg_then_stop)
    agent.handle_trade_executed = AsyncMock()
    with patch("src.python.agents.ledger.asyncio.sleep", return_value=None):
        await agent.run()
    agent.handle_trade_executed.assert_awaited()

@pytest.mark.asyncio
async def test_ledger_stop(agent):
    agent.pubsub = AsyncMock()
    await agent.stop()
    agent.redis.close.assert_awaited_once()
    assert agent.running is False

def test_ledger_main_keyboard_interrupt():
    import runpy
    m = mock_open(read_data="system:\n  environment: paper\n")
    with patch("src.python.agents.ledger.open", m), \
         patch("src.python.agents.ledger.LedgerAgent") as mock_agent_class, \
         patch("src.python.agents.ledger.validate_config", return_value=(True, None)), \
         patch("src.python.agents.ledger.asyncio.run", side_effect=[KeyboardInterrupt(), None]) as mock_run:
        mock_agent_instance = mock_agent_class.return_value
        try:
            runpy.run_module("src.python.agents.ledger", run_name="__main__")
        except SystemExit:
            pass
        assert mock_run.call_count == 2
        mock_agent_instance.run.assert_called()
        mock_agent_instance.stop.assert_called()
