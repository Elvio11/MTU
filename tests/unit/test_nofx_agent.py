import pytest
import asyncio
import json
import time
import websockets
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.nofx import NofxAgent, main

# Valid base58 strings for Solana addresses
VALID_MINT = "So11111111111111111111111111111111111111112"
VALID_CREATOR = "399S82D8Y2oMhfdfN8oB6N6XQZ8x4B6N6XQZ8x4B6N6X"

@pytest.fixture
def nofx_agent():
    config = {"system": {"environment": "paper"}}
    agent = NofxAgent(config)
    agent.redis = AsyncMock()
    agent.priority_queue = AsyncMock()
    return agent

@pytest.mark.asyncio
async def test_nofx_connect_redis(nofx_agent):
    mock_redis = AsyncMock()
    async def mock_coro(*args, **kwargs): return mock_redis
    with patch("aioredis.from_url", side_effect=mock_coro):
        await nofx_agent.connect_redis()
        assert nofx_agent.redis == mock_redis
        assert nofx_agent.priority_queue is not None

@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_message_create(nofx_agent):
    payload = {
        "txType": "create",
        "mint": VALID_MINT,
        "name": "N1",
        "symbol": "S1",
        "uri": "https://example.com/meta",
        "marketCapSol": 1.0,
        "vSolInBondingCurve": 30e9,
        "bondingCurveKey": VALID_MINT,
        "traderPublicKey": VALID_CREATOR
    }
    await nofx_agent.handle_pumpdev_message(payload)
    nofx_agent.priority_queue.enqueue.assert_called()

@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_message_migration(nofx_agent):
    payload = {
        "txType": "migration",
        "mint": VALID_MINT,
        "poolAddress": VALID_MINT,
        "signature": "S1"
    }
    await nofx_agent.handle_pumpdev_message(payload)
    nofx_agent.priority_queue.enqueue.assert_called()
    assert VALID_MINT in nofx_agent._seen_mints

@pytest.mark.asyncio
async def test_nofx_handle_helius_message(nofx_agent):
    msg = json.dumps({
        "method": "programNotification",
        "params": {
            "result": {
                "value": {
                    "logs": ["InitializeInstruction", f"initialize {VALID_MINT}"]
                }
            }
        }
    })
    await nofx_agent.handle_helius_message(msg)
    nofx_agent.priority_queue.enqueue.assert_called()

@pytest.mark.asyncio
async def test_nofx_check_trading_state_kill_switch(nofx_agent):
    nofx_agent.redis.get.return_value = "active"
    nofx_agent.ws = AsyncMock()
    nofx_agent.ws.close_code = None
    
    result = await nofx_agent.check_trading_state()
    assert result is False
    nofx_agent.ws.close.assert_called()

@pytest.mark.asyncio
async def test_nofx_run_loop_reconnect(nofx_agent):
    nofx_agent.check_trading_state = AsyncMock(return_value=True)
    nofx_agent.poll_for_tokens_http = AsyncMock()
    
    # Mock connect_pumpdev to return False initially then True
    # But we want to trigger the poll_for_tokens_http
    nofx_agent.ws = None
    
    call_count = 0
    async def mock_connect_pumpdev(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            nofx_agent.running = False
        return False

    with patch.object(nofx_agent, "connect_pumpdev", side_effect=mock_connect_pumpdev), \
         patch.object(nofx_agent, "connect_redis", new_callable=AsyncMock), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        await nofx_agent.run()
    
    assert nofx_agent.poll_for_tokens_http.called

@pytest.mark.asyncio
async def test_nofx_stop(nofx_agent):
    nofx_agent.ws = AsyncMock()
    nofx_agent.helius_ws = AsyncMock()
    await nofx_agent.stop()
    assert nofx_agent.running is False
    nofx_agent.ws.close.assert_called()

@pytest.mark.asyncio
async def test_nofx_connect_pumpdev_fallback(nofx_agent):
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    
    # websockets.connect should return an awaitable (coroutine)
    async def mock_connect_coro(*args, **kwargs):
        return mock_ws
    
    # The side_effect needs to return the coroutine objects themselves or the function that returns them
    # If we pass a list, it returns the items. If an item is a function, it doesn't call it unless we use a function as side_effect.
    
    def side_effect(*args, **kwargs):
        if side_effect.call_count == 0:
            side_effect.call_count += 1
            raise Exception("fail1")
        if side_effect.call_count == 1:
            side_effect.call_count += 1
            raise Exception("fail2")
        return mock_connect_coro()
    
    side_effect.call_count = 0
    
    with patch("websockets.connect", side_effect=side_effect):
        result = await nofx_agent.connect_pumpdev()
        assert result is True
        assert nofx_agent.ws == mock_ws
@pytest.mark.asyncio
async def test_nofx_main_keyboard_interrupt():
    m = mock_open(read_data="system:\n  environment: paper\n")
    with patch("src.python.agents.nofx.open", m), \
         patch("src.python.agents.nofx.NofxAgent") as mock_agent_class, \
         patch("src.python.agents.nofx.validate_config", return_value=(True, None)):
        
        mock_agent_instance = mock_agent_class.return_value
        mock_agent_instance.run = AsyncMock(side_effect=KeyboardInterrupt())
        mock_agent_instance.stop = AsyncMock()
        
        await main()
        assert mock_agent_instance.run.called
        assert mock_agent_instance.stop.called

@pytest.mark.asyncio
async def test_nofx_main_config_error():
    m = mock_open(read_data="system:\n  environment: paper\n")
    with patch("src.python.agents.nofx.open", m), \
         patch("src.python.agents.nofx.validate_config", return_value=(False, "error")), \
         patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        
        with pytest.raises(SystemExit) as exc:
            await main()
        assert exc.value.code == 1
@pytest.mark.asyncio
async def test_nofx_poll_for_tokens_http(nofx_agent):
    # HTTP polling is disabled in production stubs
    await nofx_agent.poll_for_tokens_http()
    assert not nofx_agent.priority_queue.enqueue.called


@pytest.mark.asyncio
async def test_nofx_handle_helius_message_invalid(nofx_agent):
    # Invalid method
    await nofx_agent.handle_helius_message(json.dumps({"method": "wrong"}))
    assert not nofx_agent.priority_queue.enqueue.called

    # Missing params
    await nofx_agent.handle_helius_message(json.dumps({"method": "programNotification"}))
    assert not nofx_agent.priority_queue.enqueue.called


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_message_no_type(nofx_agent):
    await nofx_agent.handle_pumpdev_message({"no": "type"})
    assert not nofx_agent.priority_queue.enqueue.called


@pytest.mark.asyncio
async def test_nofx_connect_redis_error(nofx_agent):
    with patch("aioredis.from_url", side_effect=Exception("Redis error")):
        with pytest.raises(Exception, match="Redis error"):
            await nofx_agent.connect_redis()

@pytest.mark.asyncio
async def test_nofx_connect_helius_ws_error(nofx_agent):
    # Helius ws is disabled in production stubs, returns True
    result = await nofx_agent.connect_helius_ws()
    assert result is True

@pytest.mark.asyncio
async def test_nofx_poll_for_tokens_http_error(nofx_agent):
    with patch("src.python.agents.nofx.requests.get", side_effect=Exception("HTTP error")):
        await nofx_agent.poll_for_tokens_http()
        assert not nofx_agent.priority_queue.enqueue.called

@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_message_invalid(nofx_agent):
    # Missing required field 'marketCapSol'
    payload = {
        "txType": "create",
        "mint": VALID_MINT,
        "name": "N1",
        "symbol": "S1"
    }
    await nofx_agent.handle_pumpdev_message(payload)
    assert not nofx_agent.priority_queue.enqueue.called

@pytest.mark.asyncio
async def test_nofx_handle_helius_message_logic(nofx_agent):
    # Test initialize with invalid log
    msg = json.dumps({
        "method": "programNotification",
        "params": {"result": {"value": {"logs": ["not matching"]}}}
    })
    await nofx_agent.handle_helius_message(msg)
    assert not nofx_agent.priority_queue.enqueue.called

    # Test initialize with valid log but error in validation
    msg = json.dumps({
        "method": "programNotification",
        "params": {"result": {"value": {"logs": ["initialize !!!"]}}}
    })
    await nofx_agent.handle_helius_message(msg)
    assert not nofx_agent.priority_queue.enqueue.called

@pytest.mark.asyncio
async def test_nofx_main_run_exception():
    m = mock_open(read_data="system:\n  environment: paper\n")
    with patch("src.python.agents.nofx.open", m), \
         patch("src.python.agents.nofx.validate_config", return_value=(True, None)), \
         patch("src.python.agents.nofx.NofxAgent") as mock_agent_class:
        mock_agent = mock_agent_class.return_value
        mock_agent.run = AsyncMock(side_effect=Exception("Run Error"))
        with pytest.raises(Exception, match="Run Error"):
            await main()
        assert mock_agent.run.called

@pytest.mark.asyncio
async def test_nofx_run_loop_operational_window(nofx_agent):
    nofx_agent.running = True
    call_count = 0
    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            nofx_agent.running = False
        return False
        
    with patch("src.python.agents.nofx.is_operational_window_active", side_effect=side_effect), \
         patch.object(nofx_agent, "connect_redis", new_callable=AsyncMock), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        await nofx_agent.run()
    assert call_count >= 1

def test_nofx_get_backoff_delay(nofx_agent):
    assert nofx_agent.get_backoff_delay(0) == 1
    assert nofx_agent.get_backoff_delay(1) == 2
    assert nofx_agent.get_backoff_delay(10) == 30 # capped at RECONNECT_MAX_DELAY

@pytest.mark.asyncio
async def test_nofx_connect_helius_ws_success(nofx_agent):
    # Helius ws is disabled in production stubs, returns True
    result = await nofx_agent.connect_helius_ws()
    assert result is True
    assert nofx_agent.helius_ws is None

@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_message_types(nofx_agent):
    # complete
    await nofx_agent.handle_pumpdev_message({"txType": "complete", "mint": VALID_MINT})
    # create_pool
    with patch.object(nofx_agent, "_publish_migration", new_callable=AsyncMock) as mock_pub:
        await nofx_agent.handle_pumpdev_message({"txType": "create_pool", "mint": VALID_MINT, "pool": VALID_MINT})
        mock_pub.assert_called()
    # whale
    await nofx_agent.handle_pumpdev_message({"txType": "whale", "solAmount": 10, "mint": VALID_MINT, "marketCapSol": 100})
    # buy (should call _handle_token_activity if solAmount >= 1)
    with patch.object(nofx_agent, "_handle_token_activity", new_callable=AsyncMock) as mock_act:
        await nofx_agent.handle_pumpdev_message({"txType": "buy", "mint": VALID_MINT, "solAmount": 1.5})
        mock_act.assert_called()

@pytest.mark.asyncio
async def test_nofx_handle_token_activity(nofx_agent):
    # Valid
    payload = {"mint": VALID_MINT, "name": "N1", "symbol": "S1"}
    await nofx_agent._handle_token_activity(payload)
    nofx_agent.priority_queue.enqueue.assert_called()

    # Invalid (missing mint)
    nofx_agent.priority_queue.enqueue.reset_mock()
    await nofx_agent._handle_token_activity({})
    assert not nofx_agent.priority_queue.enqueue.called

@pytest.mark.asyncio
async def test_nofx_publish_migration(nofx_agent):
    # Success
    nofx_agent._seen_mints = set()
    payload = {"mint": VALID_MINT, "signature": "SIG1"}
    await nofx_agent._publish_migration(payload)
    nofx_agent.priority_queue.enqueue.assert_called()

    # Already seen
    nofx_agent.priority_queue.enqueue.reset_mock()
    await nofx_agent._publish_migration(payload)
    assert not nofx_agent.priority_queue.enqueue.called

@pytest.mark.asyncio
async def test_nofx_connect_pumpdev_delay(nofx_agent):
    with patch("websockets.connect", new_callable=AsyncMock), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await nofx_agent.connect_pumpdev(delay=5)
        mock_sleep.assert_called_with(5)

@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_message_more_types(nofx_agent):
    # devSell
    await nofx_agent.handle_pumpdev_message({"txType": "devSell", "tokenAmount": 1000, "mint": VALID_MINT})
    # koth
    with patch.object(nofx_agent, "_handle_new_token", new_callable=AsyncMock) as mock_new:
        await nofx_agent.handle_pumpdev_message({"txType": "koth", "mint": VALID_MINT, "bondingCurveProgress": 90})
        mock_new.assert_called()
    # graduatingSoon
    with patch.object(nofx_agent, "_handle_new_token", new_callable=AsyncMock) as mock_new:
        await nofx_agent.handle_pumpdev_message({"txType": "graduatingSoon", "mint": VALID_MINT, "bondingCurveProgress": 95})
        mock_new.assert_called()
    # whale (large amount)
    await nofx_agent.handle_pumpdev_message({"txType": "buy", "solAmount": 6, "mint": VALID_MINT, "marketCapSol": 200})
    # other type
    await nofx_agent.handle_pumpdev_message({"type": "info", "message": "hello"})
    # not a dict
    await nofx_agent.handle_pumpdev_message("not a dict")

@pytest.mark.asyncio
async def test_nofx_rate_limit(nofx_agent):
    nofx_agent.last_event_time = time.time()
    nofx_agent.event_count = 100 # exceeded
    with patch.object(nofx_agent, "check_rate_limit", return_value=False):
        await nofx_agent._handle_new_token({"mint": VALID_MINT, "name": "N1", "symbol": "S1", "marketCapSol": 10})
        assert not nofx_agent.priority_queue.enqueue.called

@pytest.mark.asyncio
async def test_nofx_no_priority_queue(nofx_agent):
    nofx_agent.priority_queue = None
    payload = {
        "mint": VALID_MINT,
        "name": "N1",
        "symbol": "S1",
        "marketCapSol": 1.0,
        "txType": "create"
    }
    await nofx_agent._handle_new_token(payload)
    # Should print warning but not crash

@pytest.mark.asyncio
async def test_nofx_connect_pumpdev_fallback_all_fail(nofx_agent):
    with patch("websockets.connect", side_effect=Exception("all fail")):
        result = await nofx_agent.connect_pumpdev()
        assert result is False

@pytest.mark.asyncio
async def test_nofx_publish_migration_error(nofx_agent):
    nofx_agent._seen_mints = set()
    with patch("src.python.agents.nofx.AgentMessageEnvelope", side_effect=Exception("Env Error")):
        await nofx_agent._publish_migration({"mint": VALID_MINT})
        # Should catch and log
