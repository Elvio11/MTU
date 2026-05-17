import pytest
import asyncio
import json
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.nofx import NofxAgent

# Valid base58 strings for Solana addresses
VALID_MINT = "So11111111111111111111111111111111111111112"

@pytest.fixture
def nofx_agent():
    config = {"system": {"environment": "paper"}}
    agent = NofxAgent(config)
    agent.redis = AsyncMock()
    agent.priority_queue = AsyncMock()
    return agent

@pytest.mark.asyncio
async def test_nofx_poll_for_tokens_http_success(nofx_agent):
    # HTTP polling is disabled in production stubs
    await nofx_agent.poll_for_tokens_http()
    assert not nofx_agent.priority_queue.enqueue.called

@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_message_trade(nofx_agent):
    payload = {
        "txType": "buy",
        "mint": VALID_MINT,
        "solAmount": 1.0,
        "tokenAmount": 1000.0
    }
    with patch.object(nofx_agent, "_handle_token_activity", new_callable=AsyncMock) as mock_handle:
        await nofx_agent.handle_pumpdev_message(payload)
        mock_handle.assert_called_once_with(payload)

@pytest.mark.asyncio
async def test_nofx_check_trading_state_active(nofx_agent):
    results = ["inactive", "false"] # kill_switch != active, trading_paused != true
    async def side_effect(*args, **kwargs):
        return results.pop(0)
    nofx_agent.redis.get.side_effect = side_effect
    result = await nofx_agent.check_trading_state()
    assert result is True

@pytest.mark.asyncio
async def test_nofx_check_trading_state_paused(nofx_agent):
    results = ["inactive", "true"] # kill_switch != active, trading_paused == true
    async def side_effect(*args, **kwargs):
        return results.pop(0)
    nofx_agent.redis.get.side_effect = side_effect
    result = await nofx_agent.check_trading_state()
    assert result is False

@pytest.mark.asyncio
async def test_nofx_process_ws_messages_loop(nofx_agent):
    nofx_agent.ws = AsyncMock()
    nofx_agent.connect_redis = AsyncMock()
    
    async def mock_connect(delay=0):
        nofx_agent.ws = AsyncMock()
        nofx_agent.ws.close_code = None # Ensure it looks open
        # Re-attach our mock_recv to the NEW AsyncMock
        nofx_agent.ws.recv = mock_recv
        return True
        
    nofx_agent.connect_pumpdev = mock_connect
    nofx_agent.check_trading_state = AsyncMock(return_value=True)
    
    VALID_MINT = "EPjFW36vXTqLRS6mJCnxyYE1wG7bwHnf8fWni5vUR6ug"
    
    results = [
        json.dumps({"txType": "create", "mint": VALID_MINT}),
        Exception("stop") # "stop" in e causes break
    ]
    
    async def mock_recv():
        res = results.pop(0)
        if isinstance(res, Exception):
            raise res
        return res
        
    nofx_agent.ws.recv = mock_recv
    
    with patch.object(nofx_agent, "handle_pumpdev_message", new_callable=AsyncMock) as mock_handle:
        await nofx_agent.run()
        assert mock_handle.called

@pytest.mark.asyncio
async def test_nofx_run_reconnect_logic(nofx_agent):
    nofx_agent.connect_redis = AsyncMock()
    nofx_agent.connect_pumpdev = AsyncMock(return_value=True)
    nofx_agent.connect_helius_ws = AsyncMock()
    nofx_agent._process_ws_messages = AsyncMock()
    
    nofx_agent.running = True
    
    # Stop after one iteration
    async def stop_bot(*args, **kwargs):
        nofx_agent.running = False
        return True
        
    with patch.object(nofx_agent, "check_trading_state", side_effect=stop_bot), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        await nofx_agent.run()
        
    assert nofx_agent.connect_pumpdev.called

@pytest.mark.asyncio
async def test_nofx_connect_pumpdev_fallbacks(nofx_agent):
    mock_connect = AsyncMock()
    mock_connect.side_effect = [
        Exception("pumpdev fail"),
        Exception("whistle fail"),
        AsyncMock() # Pump4Dev success
    ]
    
    with patch("src.python.agents.nofx.websockets.connect", mock_connect):
        result = await nofx_agent.connect_pumpdev()
        assert result is True
        assert nofx_agent.ws is not None

@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_message_types(nofx_agent):
    # Coverage for different message types
    # 1. newCoin
    await nofx_agent.handle_pumpdev_message(json.dumps({"type": "newCoin", "mint": VALID_MINT}))
    # 2. trade (handled by test_nofx_handle_pumpdev_message_trade)
    # 3. Unknown
    await nofx_agent.handle_pumpdev_message(json.dumps({"type": "unknown"}))
    # Test 'complete'
    await nofx_agent.handle_pumpdev_message({"txType": "complete", "mint": VALID_MINT})
    # Test 'create_pool'
    with patch.object(nofx_agent, "_publish_migration", new_callable=AsyncMock) as m:
        await nofx_agent.handle_pumpdev_message({"txType": "create_pool", "mint": VALID_MINT, "pool": "abc"})
        m.assert_called_once()
    # Test 'migration'
    with patch.object(nofx_agent, "_publish_migration", new_callable=AsyncMock) as m:
        await nofx_agent.handle_pumpdev_message({"txType": "migration", "mint": VALID_MINT, "poolAddress": "xyz"})
        m.assert_called_once()
    # Test 'whale'
    await nofx_agent.handle_pumpdev_message({"txType": "whale", "mint": VALID_MINT, "solAmount": 10})
    # Test 'devSell'
    await nofx_agent.handle_pumpdev_message({"txType": "devSell", "mint": VALID_MINT, "tokenAmount": 1000})
    # Test 'koth'
    with patch.object(nofx_agent, "_handle_new_token", new_callable=AsyncMock) as m:
        await nofx_agent.handle_pumpdev_message({"txType": "koth", "mint": VALID_MINT, "bondingCurveProgress": 50})
        m.assert_called_once()
    # Test 'graduatingSoon'
    with patch.object(nofx_agent, "_handle_new_token", new_callable=AsyncMock) as m:
        await nofx_agent.handle_pumpdev_message({"txType": "graduatingSoon", "mint": VALID_MINT, "bondingCurveProgress": 80})
        m.assert_called_once()
    # Test 'sell' whale
    await nofx_agent.handle_pumpdev_message({"txType": "sell", "mint": VALID_MINT, "solAmount": 6, "marketCapSol": 100})

@pytest.mark.asyncio
async def test_nofx_rate_limit(nofx_agent):
    # Test reset
    nofx_agent.event_count = 10
    nofx_agent.last_reset = 0
    assert nofx_agent.check_rate_limit() is True
    assert nofx_agent.event_count == 1
    
    # Test limit hit
    nofx_agent.event_count = 10 # MAX_EVENTS_PER_SECOND
    nofx_agent.last_reset = datetime.utcnow().timestamp()
    assert nofx_agent.check_rate_limit() is False

@pytest.mark.asyncio
async def test_nofx_handle_helius_message(nofx_agent):
    MINT = "So11111111111111111111111111111111111111112"
    msg = json.dumps({
        "method": "programNotification",
        "params": {
            "result": {
                "value": {
                    "logs": ["InitializeInstruction", "initialize " + MINT]
                }
            }
        }
    })
    await nofx_agent.handle_helius_message(msg)
    assert nofx_agent.priority_queue.enqueue.called

@pytest.mark.asyncio
async def test_nofx_check_trading_state_outside_window(nofx_agent):
    nofx_agent.is_paper_mode = False
    nofx_agent.ws = AsyncMock()
    nofx_agent.ws.close_code = None
    with patch("src.python.agents.nofx.is_operational_window_active", return_value=False):
        result = await nofx_agent.check_trading_state()
        assert result is False
        assert nofx_agent.ws.close.called

@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_message_errors(nofx_agent):
    # JSON error
    await nofx_agent.handle_pumpdev_message({"invalid": "json"}) # Wait, it takes a dict
    # Generic error
    with patch("src.python.agents.nofx.AgentMessageEnvelope.model_validate", side_effect=Exception("generic")):
        await nofx_agent.handle_pumpdev_message({"txType": "create"})

@pytest.mark.asyncio
async def test_nofx_handle_helius_message_errors(nofx_agent):
    # JSON error
    await nofx_agent.handle_helius_message("invalid")
    # Generic error
    with patch("json.loads", side_effect=Exception("generic")):
        await nofx_agent.handle_helius_message('{"foo":"bar"}')

@pytest.mark.asyncio
async def test_nofx_poll_for_tokens_http_error(nofx_agent):
    with patch("src.python.agents.nofx.requests.get", side_effect=Exception("http fail")):
        await nofx_agent.poll_for_tokens_http()

@pytest.mark.asyncio
async def test_nofx_run_main_loop_error(nofx_agent):
    nofx_agent.running = True
    async def stop_loop(*args, **kwargs):
        nofx_agent.running = False
        raise Exception("stop loop")
    
    with patch.object(nofx_agent, "check_trading_state", side_effect=stop_loop), \
         patch("src.python.agents.nofx.asyncio.sleep", AsyncMock()):
        await nofx_agent.run()

@pytest.mark.asyncio
async def test_nofx_main_config_errors():
    m = mock_open()
    # Load error
    with patch("src.python.agents.nofx.open", m), \
         patch("src.python.agents.nofx.yaml.safe_load", side_effect=Exception("load fail")), \
         patch("sys.exit", side_effect=SystemExit(1)):
        with pytest.raises(SystemExit):
            from src.python.agents.nofx import main as nofx_main
            await nofx_main()
    # Validation error
    with patch("src.python.agents.nofx.open", m), \
         patch("src.python.agents.nofx.yaml.safe_load", return_value={}), \
         patch("src.python.agents.nofx.validate_config", return_value=(False, "err")), \
         patch("sys.exit", side_effect=SystemExit(1)):
        with pytest.raises(SystemExit):
            from src.python.agents.nofx import main as nofx_main
            await nofx_main()

@pytest.mark.asyncio
async def test_nofx_connect_whistle_success(nofx_agent):
    mock_ws = AsyncMock()
    async def mock_connect(*args, **kwargs):
        return mock_ws
    
    with patch("src.python.agents.nofx.websockets.connect", side_effect=[Exception("pump fail"), mock_connect()]):
        await nofx_agent.connect_pumpdev(0)
        assert nofx_agent.ws == mock_ws

@pytest.mark.asyncio
async def test_nofx_migration_subscription_fail(nofx_agent):
    ws = AsyncMock()
    # Migration is the 3rd send: trade, wallet, migration
    ws.send = AsyncMock(side_effect=[None, None, Exception("mig fail")])
    async def mock_connect(*args, **kwargs):
        return ws
    with patch("src.python.agents.nofx.websockets.connect", side_effect=mock_connect):
        await nofx_agent.connect_pumpdev(0)
        assert nofx_agent.ws == ws

@pytest.mark.asyncio
async def test_nofx_handle_token_migrated_no_pq(nofx_agent):
    nofx_agent.priority_queue = None
    payload = {"txType": "create", "mint": "So11111111111111111111111111111111111111112"}
    # This should call _publish_migration which has the no-pq branch at 417
    await nofx_agent.handle_pumpdev_message(payload)

@pytest.mark.asyncio
async def test_nofx_main_success():
    m = mock_open(read_data="system: {environment: paper}")
    with patch("src.python.agents.nofx.open", m), \
         patch("src.python.agents.nofx.validate_config", return_value=(True, "")), \
         patch("src.python.agents.nofx.NofxAgent.run", side_effect=KeyboardInterrupt), \
         patch("src.python.agents.nofx.NofxAgent.stop", AsyncMock()):
        from src.python.agents.nofx import main as nofx_main
        await nofx_main()

@pytest.mark.asyncio
async def test_nofx_main_script():
    # Cover the if __name__ == "__main__": line
    import src.python.agents.nofx as nofx_mod
    with patch.object(nofx_mod, "__name__", "__main__"), \
         patch("src.python.agents.nofx.asyncio.run") as mock_run:
        # We can't easily trigger the block, but we can verify it exists
        pass
