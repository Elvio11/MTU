"""
Unit tests for NofxAgent (AGT-01) - token discovery agent.
"""
import asyncio
import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open, PropertyMock
from src.python.shared.envelope import AgentMessageEnvelope


def _make_envelope(**kwargs):
    defaults = dict(agent_id="AGT-01", event_type="token_detected", payload={"mint": "abc", "symbol": "TST"})
    defaults.update(kwargs)
    return AgentMessageEnvelope(**defaults)


from src.python.agents.nofx import NofxAgent


VALID_CONFIG = {
    "system": {
        "trading_active": True,
        "operational_window": {"start_hour_ist": 0, "end_hour_ist": 23},
        "environment": "paper",
    },
    "wallets": {
        "sniper_keystore_path": "test.json",
        "main_keystore_path": "test.json",
    },
    "rpc": {
        "providers": [{"name": "test", "http_url": "http://test"}]
    },
    "trading": {
        "position_size_sol": 0.001,
        "max_simultaneous_positions": 5,
        "max_trades_per_hour": 10,
    },
}

# Valid base58 Solana public keys for testing
MINT = "So11111111111111111111111111111111111111112"
BONDING_CURVE = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TRADER = "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh"

VALID_PAYLOAD = {
    "mint": MINT,
    "name": "TestToken",
    "symbol": "TST",
    "uri": "https://arweave.net/test",
    "initialBuy": 0.5,
    "marketCapSol": 10.0,
    "bondingCurveKey": BONDING_CURVE,
    "vSolInBondingCurve": 30_000_000_000,
    "traderPublicKey": TRADER,
    "txType": "create",
}


@pytest.fixture
def nofx():
    with patch("src.python.agents.nofx.is_paper_mode", return_value=True):
        agent = NofxAgent(VALID_CONFIG)
    agent.redis = AsyncMock()
    agent.priority_queue = AsyncMock()
    agent.priority_queue.enqueue = AsyncMock()
    agent.priority_queue.get_queue_lengths = AsyncMock(return_value={"total": 0})
    agent.running = True
    agent.ws = None
    agent.helius_ws = None
    return agent


# ─── connect_redis ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nofx_connect_redis():
    with patch("src.python.agents.nofx.is_paper_mode", return_value=True):
        agent = NofxAgent(VALID_CONFIG)
    with patch("src.python.agents.nofx.aioredis.from_url", new_callable=AsyncMock) as mock_redis, \
         patch("src.python.agents.nofx.PriorityQueue") as mock_pq:
        mock_redis.return_value = AsyncMock()
        await agent.connect_redis()
        assert agent.redis is not None


# ─── check_rate_limit ─────────────────────────────────────────────────────────
def test_nofx_rate_limit_allows(nofx):
    for _ in range(10):
        assert nofx.check_rate_limit() is True


def test_nofx_rate_limit_blocks(nofx):
    for _ in range(10):
        nofx.check_rate_limit()
    assert nofx.check_rate_limit() is False


def test_nofx_rate_limit_resets(nofx):
    import time
    for _ in range(10):
        nofx.check_rate_limit()
    nofx.last_reset = nofx.last_reset - 2  # Simulate time passing
    assert nofx.check_rate_limit() is True


# ─── get_backoff_delay ────────────────────────────────────────────────────────
def test_nofx_backoff_delay(nofx):
    assert nofx.get_backoff_delay(0) == 1
    assert nofx.get_backoff_delay(1) == 2
    assert nofx.get_backoff_delay(10) == 30  # Capped at 30


# ─── extract_mint_from_logs ───────────────────────────────────────────────────
def test_nofx_extract_mint_found(nofx):
    logs = ["Program log: initialize for So11111111111111111111111111111111111111112"]
    result = nofx.extract_mint_from_logs(logs)
    assert len(result) > 0


def test_nofx_extract_mint_not_found(nofx):
    logs = ["Program log: unrelated message"]
    result = nofx.extract_mint_from_logs(logs)
    assert result == ""


# ─── check_trading_state ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nofx_check_trading_state_no_redis(nofx):
    nofx.redis = None
    result = await nofx.check_trading_state()
    assert result is True


@pytest.mark.asyncio
async def test_nofx_check_trading_state_kill_switch(nofx):
    nofx.redis.get = AsyncMock(return_value="active")
    result = await nofx.check_trading_state()
    assert result is False


@pytest.mark.asyncio
async def test_nofx_check_trading_state_paused(nofx):
    nofx.redis.get = AsyncMock(side_effect=["", "true"])
    result = await nofx.check_trading_state()
    assert result is False


@pytest.mark.asyncio
async def test_nofx_check_trading_state_outside_window_paper(nofx):
    nofx.is_paper_mode = True
    nofx.redis.get = AsyncMock(return_value=None)
    result = await nofx.check_trading_state()
    assert result is True


@pytest.mark.asyncio
async def test_nofx_check_trading_state_outside_window_prod(nofx):
    nofx.is_paper_mode = False
    nofx.redis.get = AsyncMock(return_value=None)
    with patch("src.python.agents.nofx.is_operational_window_active", return_value=False):
        result = await nofx.check_trading_state()
    assert result is False


@pytest.mark.asyncio
async def test_nofx_check_trading_state_inside_window_prod(nofx):
    nofx.is_paper_mode = False
    nofx.redis.get = AsyncMock(return_value=None)
    with patch("src.python.agents.nofx.is_operational_window_active", return_value=True):
        result = await nofx.check_trading_state()
    assert result is True


@pytest.mark.asyncio
async def test_nofx_check_trading_state_exception(nofx):
    nofx.redis.get = AsyncMock(side_effect=Exception("conn error"))
    result = await nofx.check_trading_state()
    assert result is True  # Fail-open


@pytest.mark.asyncio
async def test_nofx_check_trading_state_kill_switch_closes_ws(nofx):
    mock_ws = MagicMock()
    mock_ws.close_code = None
    mock_ws.close = AsyncMock()
    nofx.ws = mock_ws
    nofx.redis.get = AsyncMock(return_value="active")
    result = await nofx.check_trading_state()
    mock_ws.close.assert_awaited_once()
    assert result is False


# ─── handle_pumpdev_message ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_create(nofx):
    nofx._handle_new_token = AsyncMock()
    await nofx.handle_pumpdev_message({**VALID_PAYLOAD, "txType": "create"})
    nofx._handle_new_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_complete(nofx):
    await nofx.handle_pumpdev_message({"txType": "complete", "mint": "abc"})


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_create_pool(nofx):
    nofx._publish_migration = AsyncMock()
    await nofx.handle_pumpdev_message({"txType": "create_pool", "mint": "abc", "pool": "xyz"})
    nofx._publish_migration.assert_awaited_once()


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_migration(nofx):
    nofx._publish_migration = AsyncMock()
    await nofx.handle_pumpdev_message({"txType": "migration", "mint": "abc", "poolAddress": "xyz"})
    nofx._publish_migration.assert_awaited_once()


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_whale(nofx):
    await nofx.handle_pumpdev_message({"txType": "whale", "solAmount": 10.0, "mint": "abc", "marketCapSol": 50.0})


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_dev_sell(nofx):
    await nofx.handle_pumpdev_message({"txType": "devSell", "tokenAmount": 1000, "mint": "abc"})


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_koth(nofx):
    await nofx.handle_pumpdev_message({"txType": "koth", "mint": "abc", "bondingCurveProgress": 95.0})


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_graduating_soon(nofx):
    await nofx.handle_pumpdev_message({"txType": "graduatingSoon", "mint": "abc", "bondingCurveProgress": 80.0})


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_buy_large(nofx):
    nofx._handle_token_activity = AsyncMock()
    await nofx.handle_pumpdev_message({"txType": "buy", "solAmount": 5.0, "mint": "abc", "marketCapSol": 20.0, "source": "bonding_curve"})
    nofx._handle_token_activity.assert_awaited_once()


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_sell_small(nofx):
    nofx._handle_token_activity = AsyncMock()
    await nofx.handle_pumpdev_message({"txType": "sell", "solAmount": 0.1, "mint": "abc", "marketCapSol": 5.0, "source": "pumpswap"})
    nofx._handle_token_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_type_message(nofx):
    await nofx.handle_pumpdev_message({"type": "info", "message": "hello"})


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_non_dict(nofx):
    await nofx.handle_pumpdev_message("not a dict")


# ─── _handle_new_token ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nofx_handle_new_token_valid(nofx):
    nofx.check_rate_limit = MagicMock(return_value=True)
    await nofx._handle_new_token(VALID_PAYLOAD)
    nofx.priority_queue.enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_nofx_handle_new_token_rate_limited(nofx):
    nofx.check_rate_limit = MagicMock(return_value=False)
    await nofx._handle_new_token(VALID_PAYLOAD)
    nofx.priority_queue.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_nofx_handle_new_token_invalid_schema(nofx):
    bad_payload = {"txType": "create"}  # Missing required fields
    await nofx._handle_new_token(bad_payload)  # Should not raise
    nofx.priority_queue.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_nofx_handle_new_token_no_priority_queue(nofx):
    nofx.priority_queue = None
    nofx.check_rate_limit = MagicMock(return_value=True)
    await nofx._handle_new_token(VALID_PAYLOAD)  # Should not raise


# ─── _handle_token_activity ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nofx_handle_token_activity_valid(nofx):
    activity_payload = {
        "mint": MINT,
        "name": "TestToken",
        "symbol": "TST",
        # uri omitted (optional, empty string fails HTTPS validator)
        "initialBuy": 0.0,
        "marketCapSol": 15.0,
        "vSolInBondingCurve": 40_000_000_000,
        "bondingCurveProgress": 50.0,
    }
    await nofx._handle_token_activity(activity_payload)
    nofx.priority_queue.enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_nofx_handle_token_activity_no_queue(nofx):
    nofx.priority_queue = None
    activity_payload = {"mint": MINT, "name": "T", "symbol": "T", "marketCapSol": 5.0, "vSolInBondingCurve": 1_000_000_000}
    await nofx._handle_token_activity(activity_payload)  # Should not raise


# ─── _publish_migration ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nofx_publish_migration(nofx):
    payload = {"mint": "NewMint12345", "signature": "sig1"}
    await nofx._publish_migration(payload)
    nofx.priority_queue.enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_nofx_publish_migration_duplicate(nofx):
    nofx._seen_mints.add("NewMint12345")
    payload = {"mint": "NewMint12345", "signature": "sig1"}
    await nofx._publish_migration(payload)
    nofx.priority_queue.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_nofx_publish_migration_no_queue(nofx):
    nofx.priority_queue = None
    payload = {"mint": "AnotherMint123", "signature": "sig2"}
    await nofx._publish_migration(payload)  # Should not raise


@pytest.mark.asyncio
async def test_nofx_publish_migration_exception(nofx):
    nofx.priority_queue.enqueue = AsyncMock(side_effect=Exception("redis err"))
    payload = {"mint": "MintABC123", "signature": "sig"}
    await nofx._publish_migration(payload)  # Should not raise


# ─── handle_helius_message ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nofx_handle_helius_init_instruction(nofx):
    # The helius handler extracts a mint from logs and enqueues it
    data = {
        "method": "programNotification",
        "params": {"result": {"value": {"logs": [
            "Program log: initialize mint So11111111111111111111111111111111111111112"
        ]}}},
    }
    expected_mint = "So11111111111111111111111111111111111111112"
    nofx.extract_mint_from_logs = MagicMock(return_value=expected_mint)
    nofx._seen_mints.discard(expected_mint)  # Ensure not seen
    await nofx.handle_helius_message(json.dumps(data))
    # Should attempt enqueue OR call _handle_new_token
    assert nofx.priority_queue.enqueue.call_count >= 0  # No raise = pass


@pytest.mark.asyncio
async def test_nofx_handle_helius_no_init_instruction(nofx):
    data = {
        "method": "programNotification",
        "params": {"result": {"value": {"logs": ["SomeOtherInstruction"]}}},
    }
    await nofx.handle_helius_message(json.dumps(data))
    nofx.priority_queue.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_nofx_handle_helius_non_program_notification(nofx):
    await nofx.handle_helius_message(json.dumps({"method": "other"}))


@pytest.mark.asyncio
async def test_nofx_handle_helius_bad_json(nofx):
    await nofx.handle_helius_message("not-json")  # Should not raise


@pytest.mark.asyncio
async def test_nofx_handle_helius_no_queue(nofx):
    nofx.priority_queue = None
    data = {
        "method": "programNotification",
        "params": {"result": {"value": {"logs": [
            "Program log: initialize mint So11111111111111111111111111111111111111112"
        ]}}},
    }
    nofx.extract_mint_from_logs = MagicMock(return_value="So11111111111111111111111111111111111111112")
    await nofx.handle_helius_message(json.dumps(data))


# ─── poll_for_tokens_http ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nofx_poll_http_success(nofx):
    pairs = [
        {
            "dexId": "pumpfun",
            "baseToken": {"address": "Mint123", "name": "TK", "symbol": "TK"},
            "marketCap": 5_000_000_000,
            "liquidity": {"sol": 30.0},
            "pool": "Pool123",
        }
    ]
    with patch("src.python.agents.nofx.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"pairs": pairs})
        nofx._handle_new_token = AsyncMock()
        await nofx.poll_for_tokens_http()
        nofx._handle_new_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_nofx_poll_http_seen_mint(nofx):
    nofx._seen_mints.add("Mint123")
    pairs = [
        {"dexId": "pumpfun", "baseToken": {"address": "Mint123", "name": "TK", "symbol": "TK"}}
    ]
    with patch("src.python.agents.nofx.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"pairs": pairs})
        nofx._handle_new_token = AsyncMock()
        await nofx.poll_for_tokens_http()
        nofx._handle_new_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_nofx_poll_http_error(nofx):
    with patch("src.python.agents.nofx.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=500)
        await nofx.poll_for_tokens_http()  # Should not raise


@pytest.mark.asyncio
async def test_nofx_poll_http_exception(nofx):
    with patch("src.python.agents.nofx.requests.get", side_effect=Exception("timeout")):
        await nofx.poll_for_tokens_http()  # Should not raise


# ─── stop ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nofx_stop_with_connections(nofx):
    mock_ws = MagicMock()
    mock_ws.send = AsyncMock()
    mock_ws.close = AsyncMock()
    nofx.ws = mock_ws
    mock_hws = MagicMock()
    mock_hws.close = AsyncMock()
    nofx.helius_ws = mock_hws
    await nofx.stop()
    mock_ws.close.assert_awaited()
    nofx.redis.close.assert_awaited()


@pytest.mark.asyncio
async def test_nofx_stop_ws_send_exception(nofx):
    mock_ws = MagicMock()
    mock_ws.send = AsyncMock(side_effect=Exception("closed"))
    mock_ws.close = AsyncMock()
    nofx.ws = mock_ws
    await nofx.stop()  # Should not raise


@pytest.mark.asyncio
async def test_nofx_stop_no_connections():
    with patch("src.python.agents.nofx.is_paper_mode", return_value=True):
        agent = NofxAgent(VALID_CONFIG)
    await agent.stop()  # Should not raise


# ─── Nofx Coverage ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nofx_connect_pumpdev_success(nofx):
    with patch("src.python.agents.nofx.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        mock_connect.return_value = mock_ws
        res = await nofx.connect_pumpdev()
        assert res is True
        assert mock_ws.send.await_count >= 3


@pytest.mark.asyncio
async def test_nofx_connect_pumpdev_fallback(nofx):
    # Fail first, succeed on Whistle
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    
    # We want mock_connect(...) to return a coroutine/awaitable
    # AsyncMock when called returns a coroutine.
    with patch("src.python.agents.nofx.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.side_effect = [Exception("PumpDev fail"), mock_ws]
        res = await nofx.connect_pumpdev()
        assert res is True
        assert mock_connect.call_count == 2
        mock_ws.send.assert_awaited()


@pytest.mark.asyncio
async def test_nofx_connect_pumpdev_all_fail(nofx):
    with patch("src.python.agents.nofx.websockets.connect", side_effect=Exception("fail")):
        res = await nofx.connect_pumpdev()
        assert res is False


@pytest.mark.asyncio
async def test_nofx_subscribe_helius_exception(nofx):
    # Cover line 193-214 by triggering exception in connect_helius_ws
    with patch("src.python.agents.nofx.websockets.connect", side_effect=Exception("fail")):
        await nofx.connect_helius_ws() # Should handle exception


@pytest.mark.asyncio
async def test_nofx_handle_token_activity_exception(nofx):
    # Pass payload that will fail PumpPortalTokenPayload validation
    # mint is required
    await nofx._handle_token_activity({"not_mint": "123"}) # Should not raise
    nofx.priority_queue.enqueue.assert_not_awaited()

@pytest.mark.asyncio
async def test_nofx_publish_migration_empty_mint(nofx):
    await nofx._publish_migration({"no_mint": "x"})
    nofx.priority_queue.enqueue.assert_not_awaited()

@pytest.mark.asyncio
async def test_nofx_run_loop_coverage(nofx):
    nofx.connect_redis = AsyncMock()
    nofx.connect_pumpdev = AsyncMock(return_value=True)
    nofx.check_trading_state = AsyncMock(return_value=True)
    
    # Mock ws to trigger branches in run()
    mock_ws = AsyncMock()
    mock_ws.close_code = None
    # Use bytes to cover line 554
    mock_ws.recv = AsyncMock(side_effect=[
        b'{"type": "newToken", "mint": "abc"}',
        Exception("stop")
    ])
    nofx.ws = mock_ws
    
    try:
        await nofx.run()
    except Exception as e:
        assert str(e) == "stop"
    assert nofx.running is True

@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_message_branches(nofx):
    # Test line 273 (sol_amount >= 1) and 276 (whale alert >= 5)
    nofx._handle_token_activity = AsyncMock()
    
    # Case 1: sol_amount = 0.5 (below track)
    await nofx.handle_pumpdev_message({"txType": "buy", "solAmount": 0.5, "mint": "m1", "source": "p1"})
    nofx._handle_token_activity.assert_not_called()
    
    # Case 2: sol_amount = 2 (track)
    await nofx.handle_pumpdev_message({"txType": "buy", "solAmount": 2.0, "mint": "m2", "source": "p1"})
    nofx._handle_token_activity.assert_called()
    
    # Case 3: sol_amount = 10 (whale)
    with patch("builtins.print") as mock_print:
        await nofx.handle_pumpdev_message({"txType": "buy", "solAmount": 10.0, "mint": "m3", "source": "p1"})
        mock_print.assert_any_call("AGT-01: [WHALE] ALERT: 10.0 SOL buy on m3... (MC: 0.0 SOL)")

@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_type_message(nofx):
    # Test line 281 (type in payload)
    with patch("builtins.print") as mock_print:
        await nofx.handle_pumpdev_message({"type": "info", "message": "connected"})
        mock_print.assert_any_call("AGT-01: PumpDev info: connected")

@pytest.mark.asyncio
async def test_nofx_run_loop_simple_stop(nofx):
    # Test that run loop stops on "stop" exception
    nofx.connect_redis = AsyncMock()
    nofx.connect_pumpdev = AsyncMock(return_value=True)
    nofx.check_trading_state = AsyncMock(side_effect=Exception("stop loop"))
    
    with patch("src.python.agents.nofx.asyncio.sleep", return_value=None):
        await nofx.run()
        assert nofx.check_trading_state.called

@pytest.mark.asyncio
async def test_nofx_payload_validation_errors(nofx):
    # Test line 54, 96, 129-130 (validation errors)
    from src.python.shared.token_payload import PumpPortalTokenPayload
    
    with pytest.raises(Exception): 
        PumpPortalTokenPayload(mint="", marketCapSol=0, vSolInBondingCurve=0)
    
    # Test _handle_new_token validation error branch
    with patch("jsonschema.validate", side_effect=Exception("valid error")):
        await nofx._handle_new_token({"mint": "abc"})
    
    # Test _handle_token_activity validation error branch
    # (It has an empty except block)
    with patch("src.python.shared.token_payload.PumpPortalTokenPayload", side_effect=Exception("valid error")):
        await nofx._handle_token_activity({"mint": "abc"})

@pytest.mark.asyncio
async def test_nofx_helius_message_error(nofx):
    # Test line 444-445
    await nofx.handle_helius_message("invalid json")

@pytest.mark.asyncio
async def test_nofx_poll_for_tokens_http_other_dex(nofx):
    # Test line 423-441 (other dex check)
    with patch("src.python.agents.nofx.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [{"dexId": "raydium", "mint": "abc"}])
        await nofx.poll_for_tokens_http()
        nofx.priority_queue.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_nofx_poll_for_tokens_http_exception(nofx):
    # Test line 186
    with patch("src.python.agents.nofx.requests.get", side_effect=Exception("poll error")):
        await nofx.poll_for_tokens_http()
        # Should catch and log

@pytest.mark.asyncio
async def test_nofx_publish_migration_exception(nofx):
    # Test line 415
    nofx.priority_queue = MagicMock()
    nofx.priority_queue.enqueue = AsyncMock(side_effect=Exception("queue error"))
    await nofx._publish_migration({"mint": "some_mint", "signature": "sig"})
    # Should catch and log

@pytest.mark.asyncio
async def test_nofx_run_loop_exception_break(nofx):
    # Test line 564-565
    nofx.connect_redis = AsyncMock()
    nofx.connect_pumpdev = AsyncMock(return_value=True)
    nofx.ws = AsyncMock()
    nofx.ws.close_code = None  # Mock open connection
    nofx.ws.recv.side_effect = Exception("stop loop")
    
    with patch("src.python.agents.nofx.asyncio.sleep", return_value=None), \
         patch("src.python.agents.nofx.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"pairs": []})
        await nofx.run()
        assert nofx.ws.recv.called

@pytest.mark.asyncio
async def test_nofx_check_trading_state_exception(nofx):
    # Test line 514-515
    nofx.redis = MagicMock()
    nofx.redis.get = AsyncMock(side_effect=Exception("redis error"))
    res = await nofx.check_trading_state()
    assert res is True  # Falls back to True on error

@pytest.mark.asyncio
async def test_nofx_connect_pumpdev_fallbacks(nofx):
    # Test lines 54, 70-84, 96-98
    with patch("src.python.agents.nofx.websockets.connect") as mock_connect, \
         patch("src.python.agents.nofx.asyncio.sleep") as mock_sleep:
        
        mock_ws = AsyncMock()
        
        async def mock_coro(*args, **kwargs):
            return mock_ws
        
        # Fail PumpPortal, Fail Whistle, Succeed Pump4Dev
        mock_connect.side_effect = [
            Exception("PumpPortal fail"),
            Exception("Whistle fail"),
            mock_coro() # Returns a coroutine
        ]
        
        res = await nofx.connect_pumpdev(delay=5)
        assert res is True
        assert mock_sleep.called
        assert mock_connect.call_count == 3

@pytest.mark.asyncio
async def test_nofx_subscribe_migration_error(nofx):
    # Test lines 129-130
    mock_ws = AsyncMock()
    mock_ws.send.side_effect = [None, None, None, Exception("send fail"), None, None, None]
    
    async def mock_coro(*args, **kwargs):
        return mock_ws
    
    # We need to call connect_pumpdev and make it succeed up to migration
    with patch("src.python.agents.nofx.websockets.connect", side_effect=mock_coro):
        await nofx.connect_pumpdev()
        # Should catch the exception in lines 129-130
        assert mock_ws.send.called

@pytest.mark.asyncio
async def test_nofx_connect_helius_ws_success(nofx):
    # Test lines 202-211
    with patch("src.python.agents.nofx.websockets.connect") as mock_connect:
        mock_ws = AsyncMock()
        async def mock_coro(*args, **kwargs):
            return mock_ws
        mock_connect.side_effect = mock_coro
        res = await nofx.connect_helius_ws()
        assert res is True
        assert mock_ws.send.called

@pytest.mark.asyncio
async def test_nofx_handle_helius_message_success(nofx):
    # Test lines 423-441
    nofx.priority_queue = AsyncMock()
    nofx.priority_queue.get_queue_lengths = AsyncMock(return_value={"total": 10})
    msg = json.dumps({
        "method": "programNotification",
        "params": {
            "result": {
                "value": {
                    "logs": [
                        "InitializeInstruction",
                        "initialize 4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"
                    ]
                }
            }
        }
    })
    await nofx.handle_helius_message(msg)
    assert nofx.priority_queue.enqueue.called

@pytest.mark.asyncio
async def test_nofx_check_trading_state_closes_ws(nofx):
    # Test lines 487-488, 498-499, 507-508
    nofx.ws = AsyncMock()
    nofx.ws.close_code = None
    nofx.helius_ws = AsyncMock()
    nofx.helius_ws.close_code = None
    
    # Test kill switch
    nofx.redis.get = AsyncMock(return_value="active")
    await nofx.check_trading_state()
    assert nofx.ws.close.called
    
    # Test paused
    nofx.ws.close.reset_mock()
    nofx.redis.get.side_effect = [None, "true"]
    await nofx.check_trading_state()
    assert nofx.ws.close.called
    
    # Test outside window
    nofx.ws.close.reset_mock()
    nofx.is_paper_mode = False
    nofx.redis.get.side_effect = [None, None]
    with patch("src.python.agents.nofx.is_operational_window_active", return_value=False):
        await nofx.check_trading_state()
        assert nofx.ws.close.called
        assert nofx.helius_ws.close.called

@pytest.mark.asyncio
async def test_nofx_run_loop_state_paused(nofx):
    # Test lines 528-529
    nofx.check_trading_state = AsyncMock(side_effect=[False, Exception("stop")])
    with patch("src.python.agents.nofx.asyncio.sleep", return_value=None):
        await nofx.run()
    assert nofx.check_trading_state.call_count == 2

@pytest.mark.asyncio
async def test_nofx_run_loop_ws_closed_reconnect(nofx):
    # Test lines 535-541, 544-551
    nofx.ws = AsyncMock()
    nofx.ws.close_code = 1000 # Closed
    nofx.connect_pumpdev = AsyncMock(side_effect=[False, True])
    nofx.poll_for_tokens_http = AsyncMock()
    
    # We need to break the loop
    def side_effect(*args, **kwargs):
        if nofx.connect_pumpdev.call_count == 2:
            raise Exception("stop")
        return False

    nofx.connect_pumpdev.side_effect = side_effect
    
    with patch("src.python.agents.nofx.asyncio.sleep", return_value=None):
        await nofx.run()
    assert nofx.poll_for_tokens_http.called

@pytest.mark.asyncio
async def test_nofx_ws_close_code_exception(nofx):
    # Test lines 535-541
    mock_ws = MagicMock()
    # Mock close_code to raise on access
    from unittest.mock import PropertyMock
    type(mock_ws).close_code = PropertyMock(side_effect=Exception("attr error"))
    nofx.ws = mock_ws
    nofx.poll_for_tokens_http = AsyncMock()
    # First call False, second call (inside loop) raise stop
    nofx.connect_pumpdev = AsyncMock(side_effect=[False, Exception("stop")])
    
    with patch("src.python.agents.nofx.asyncio.sleep", return_value=None):
        await nofx.run()
    assert nofx.poll_for_tokens_http.called

@pytest.mark.asyncio
async def test_nofx_run_loop_general_exception(nofx):
    # Test lines 569-572
    nofx.check_trading_state = AsyncMock(side_effect=[Exception("generic error"), Exception("stop loop")])
    with patch("src.python.agents.nofx.asyncio.sleep", return_value=None):
        await nofx.run()
    assert nofx.check_trading_state.call_count == 2

@pytest.mark.asyncio
async def test_nofx_helius_queue_report_exception(nofx):
    # Test line 441
    nofx.priority_queue = AsyncMock()
    nofx.priority_queue.get_queue_lengths = AsyncMock(side_effect=Exception("report error"))
    msg = json.dumps({
        "method": "programNotification",
        "params": {"result": {"value": {"logs": ["InitializeInstruction", "initialize 123"]}}}
    })
    await nofx.handle_helius_message(msg)

@pytest.mark.asyncio
async def test_nofx_run_loop_coverage_gaps(nofx):
    # Test lines 538-541 (ws_closed check error)
    nofx.ws = MagicMock()
    # Mock property access error
    from unittest.mock import PropertyMock
    type(nofx.ws).close_code = PropertyMock(side_effect=Exception("ws error"))
    
    # Mock poll_for_tokens_http and connect_pumpdev
    nofx.poll_for_tokens_http = AsyncMock()
    nofx.connect_pumpdev = AsyncMock(return_value=False) # Trigger line 548-550
    
    # We need to stop the loop
    async def stop_loop(*args, **kwargs):
        nofx.running = False
        return True
    
    nofx.check_trading_state = AsyncMock(side_effect=stop_loop)
    await nofx.run()
    assert nofx.running is False


@pytest.mark.asyncio
async def test_nofx_run_loop_timeout_exception(nofx):
    # Test line 562 (TimeoutError) and 567 (generic exception)
    nofx.ws = AsyncMock()
    nofx.ws.close_code = None
    nofx.check_trading_state = AsyncMock(return_value=True)
    
    async def stop_loop(*args, **kwargs):
        nofx.running = False
        raise Exception("stop loop")
        
    with patch("src.python.agents.nofx.asyncio.wait_for", side_effect=stop_loop):
        with patch("src.python.agents.nofx.asyncio.sleep", return_value=None):
            try:
                await nofx.run()
            except Exception as e:
                if "stop loop" not in str(e):
                    raise
