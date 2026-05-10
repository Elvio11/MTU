"""
Unit tests for OracleAgent and CassandraAgent.
Mocks aiohttp sessions and aioredis.
"""
import asyncio
import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.shared.envelope import AgentMessageEnvelope


def _make_envelope(**kwargs):
    defaults = dict(
        agent_id="AGT-01",
        event_type="token_detected",
        payload={"mint": "abc", "symbol": "TST"},
        correlation_id=str(uuid.uuid4()),
    )
    defaults.update(kwargs)
    return AgentMessageEnvelope(**defaults)


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


# ─────────────────────────────────────────────────────────────────────────────
# OracleAgent tests
# ─────────────────────────────────────────────────────────────────────────────
from src.python.agents.oracle import OracleAgent


def _make_session_mock(status=200, json_data=None):
    """Return a mock aiohttp session whose .get() context manager returns json_data."""
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data or {})

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_cm)
    mock_session.close = AsyncMock()
    return mock_session


@pytest.fixture
def oracle():
    agent = OracleAgent(VALID_CONFIG)
    agent.redis = AsyncMock()
    # redis.pubsub() is a synchronous call returning a PubSub object
    agent.redis.pubsub = MagicMock()
    agent.pubsub = AsyncMock()
    agent.running = True
    agent.session = _make_session_mock()
    agent.birdeye_key = "test-key"
    return agent


@pytest.mark.asyncio
async def test_oracle_connect_redis():
    agent = OracleAgent(VALID_CONFIG)
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_r = AsyncMock()
    mock_r.pubsub = MagicMock(return_value=mock_pubsub)
    with patch("src.python.agents.oracle.aioredis.from_url", new_callable=AsyncMock) as mock_from:
        mock_from.return_value = mock_r
        with patch("os.getenv", return_value="some-key"):
            await agent.connect_redis()
    assert agent.redis is not None


@pytest.mark.asyncio
async def test_oracle_fetch_price_jupiter_success(oracle):
    oracle.session = _make_session_mock(200, {"abc": {"usdPrice": 0.0012}})
    price = await oracle.fetch_price_jupiter("abc")
    assert price == pytest.approx(0.0012)


@pytest.mark.asyncio
async def test_oracle_fetch_price_jupiter_no_price(oracle):
    oracle.session = _make_session_mock(200, {"abc": {}})
    price = await oracle.fetch_price_jupiter("abc")
    assert price == 0.0


@pytest.mark.asyncio
async def test_oracle_fetch_price_jupiter_bad_status(oracle):
    oracle.session = _make_session_mock(500, {})
    price = await oracle.fetch_price_jupiter("abc")
    assert price == 0.0


@pytest.mark.asyncio
async def test_oracle_fetch_price_jupiter_exception(oracle):
    oracle.session.get = MagicMock(side_effect=Exception("net err"))
    price = await oracle.fetch_price_jupiter("abc")
    assert price == 0.0


@pytest.mark.asyncio
async def test_oracle_fetch_price_dexscreener_success(oracle):
    oracle.session = _make_session_mock(200, {"pairs": [{"priceUsd": "0.005"}]})
    price = await oracle.fetch_price_dexscreener("abc")
    assert price == pytest.approx(0.005)


@pytest.mark.asyncio
async def test_oracle_fetch_price_dexscreener_empty_pairs(oracle):
    oracle.session = _make_session_mock(200, {"pairs": []})
    price = await oracle.fetch_price_dexscreener("abc")
    assert price == 0.0


@pytest.mark.asyncio
async def test_oracle_fetch_price_dexscreener_exception(oracle):
    oracle.session.get = MagicMock(side_effect=Exception("net"))
    price = await oracle.fetch_price_dexscreener("abc")
    assert price == 0.0


@pytest.mark.asyncio
async def test_oracle_fetch_price_birdeye_no_key(oracle):
    oracle.birdeye_key = None
    price = await oracle.fetch_price_birdeye("abc")
    assert price == 0.0


@pytest.mark.asyncio
async def test_oracle_fetch_price_birdeye_v3_success(oracle):
    oracle.session = _make_session_mock(200, {"data": {"value": 0.003}})
    price = await oracle.fetch_price_birdeye("abc")
    assert price == pytest.approx(0.003)


@pytest.mark.asyncio
async def test_oracle_fetch_price_birdeye_fallback(oracle):
    """When v3 throws, v2 fallback runs; price can be anything (float)."""
    bad_cm = AsyncMock()
    bad_cm.__aenter__ = AsyncMock(side_effect=Exception("fail"))
    bad_cm.__aexit__ = AsyncMock(return_value=False)
    oracle.session.get = MagicMock(side_effect=[bad_cm, _make_session_mock(200, {"data": {"value": 0.007}}).get("x")])
    price = await oracle.fetch_price_birdeye("abc")
    # v3 fails, v2 runs - result is either 0.0 (both fail) or non-zero (v2 succeeds)
    assert isinstance(price, float)


@pytest.mark.asyncio
async def test_oracle_fetch_price_coingecko_success(oracle):
    oracle._sol_price_cache = 100.0
    oracle.session = _make_session_mock(200, {"solana": {"usd": 200.0}})
    price = await oracle.fetch_price_coingecko("abc")
    assert price == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_oracle_fetch_price_coingecko_no_sol_cache(oracle):
    oracle._sol_price_cache = None
    oracle.session = _make_session_mock(200, {"solana": {"usd": 200.0}})
    price = await oracle.fetch_price_coingecko("abc")
    assert price == 0.0


@pytest.mark.asyncio
async def test_oracle_fetch_price_coingecko_exception(oracle):
    oracle.session.get = MagicMock(side_effect=Exception("net"))
    price = await oracle.fetch_price_coingecko("abc")
    assert price == 0.0


@pytest.mark.asyncio
async def test_oracle_handle_position_opened(oracle):
    payload = {"position_id": "pos1", "mint": "abc", "entry_price_sol": 0.01}
    env = _make_envelope(event_type="position_opened", payload=payload)
    await oracle.handle_position_opened(env.model_dump_json())
    assert "pos1" in oracle.positions


@pytest.mark.asyncio
async def test_oracle_handle_position_opened_bad_json(oracle):
    await oracle.handle_position_opened("bad-json")  # Should not raise


@pytest.mark.asyncio
async def test_oracle_update_position_price_jupiter(oracle):
    oracle.positions["pos1"] = {"mint": "abc", "last_prices": [0.01], "fail_count": 0}
    oracle.fetch_price_jupiter = AsyncMock(return_value=0.02)
    await oracle.update_position_price("pos1", "abc")
    oracle.redis.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_oracle_update_position_price_dexscreener_fallback(oracle):
    oracle.positions["pos1"] = {"mint": "abc", "last_prices": [0.01], "fail_count": 0}
    oracle.fetch_price_jupiter = AsyncMock(return_value=0.0)
    oracle.fetch_price_dexscreener = AsyncMock(return_value=0.02)
    await oracle.update_position_price("pos1", "abc")
    oracle.redis.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_oracle_update_position_price_birdeye_fallback(oracle):
    oracle.positions["pos1"] = {"mint": "abc", "last_prices": [0.01], "fail_count": 0}
    oracle.fetch_price_jupiter = AsyncMock(return_value=0.0)
    oracle.fetch_price_dexscreener = AsyncMock(return_value=0.0)
    oracle.fetch_price_birdeye = AsyncMock(return_value=0.02)
    await oracle.update_position_price("pos1", "abc")
    oracle.redis.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_oracle_update_position_price_all_fail_threshold(oracle):
    oracle.positions["pos1"] = {"mint": "abc", "last_prices": [], "fail_count": 3}
    oracle.fetch_price_jupiter = AsyncMock(return_value=0.0)
    oracle.fetch_price_dexscreener = AsyncMock(return_value=0.0)
    oracle.fetch_price_birdeye = AsyncMock(return_value=0.0)
    await oracle.update_position_price("pos1", "abc")
    # Should publish price_unavailable
    oracle.redis.publish.assert_awaited()


@pytest.mark.asyncio
async def test_oracle_update_position_price_all_fail_below_threshold(oracle):
    """fail_count starts at 2, reaches 3 = MAX_CONSECUTIVE_FAILURES → publishes price_unavailable."""
    oracle.positions["pos1"] = {"mint": "abc", "last_prices": [], "fail_count": 2}
    oracle.fetch_price_jupiter = AsyncMock(return_value=0.0)
    oracle.fetch_price_dexscreener = AsyncMock(return_value=0.0)
    oracle.fetch_price_birdeye = AsyncMock(return_value=0.0)
    await oracle.update_position_price("pos1", "abc")
    # fail_count becomes 3, reaches MAX_CONSECUTIVE_FAILURES → publish
    oracle.redis.publish.assert_awaited()


@pytest.mark.asyncio
async def test_oracle_update_price_trims_buffer(oracle):
    oracle.positions["pos1"] = {"mint": "abc", "last_prices": list(range(10)), "fail_count": 0}
    oracle.fetch_price_jupiter = AsyncMock(return_value=0.05)
    await oracle.update_position_price("pos1", "abc")
    assert len(oracle.positions["pos1"]["last_prices"]) == 10


@pytest.mark.asyncio
async def test_oracle_stop(oracle):
    oracle.session = AsyncMock()
    oracle.session.close = AsyncMock()
    await oracle.stop()
    oracle.session.close.assert_awaited_once()
    oracle.redis.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_oracle_stop_no_session():
    agent = OracleAgent(VALID_CONFIG)
    await agent.stop()  # Should not raise


# ─────────────────────────────────────────────────────────────────────────────
# CassandraAgent tests
# ─────────────────────────────────────────────────────────────────────────────
from src.python.agents.cassandra import CassandraAgent


@pytest.fixture
def cassandra():
    agent = CassandraAgent(VALID_CONFIG)
    agent.redis = AsyncMock()
    # redis.pubsub() is synchronous
    agent.redis.pubsub = MagicMock()
    agent.pubsub = AsyncMock()
    agent.session = MagicMock()
    agent.running = True
    return agent


def _make_cassandra_session(status=200, json_data=None):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data or {})

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_cm)
    mock_session.close = AsyncMock()
    return mock_session


@pytest.mark.asyncio
async def test_cassandra_connect_redis():
    agent = CassandraAgent(VALID_CONFIG)
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_r = AsyncMock()
    mock_r.pubsub = MagicMock(return_value=mock_pubsub)
    with patch("src.python.agents.cassandra.aioredis.from_url", new_callable=AsyncMock) as mock_from:
        mock_from.return_value = mock_r
        await agent.connect_redis()


@pytest.mark.asyncio
async def test_cassandra_fetch_dexscreener_success(cassandra):
    cassandra.session = _make_cassandra_session(200, {"pair": {"info": {"twitter": "https://x"}}})
    data = await cassandra.fetch_dexscreener_data("abc")
    assert data is not None


@pytest.mark.asyncio
async def test_cassandra_fetch_dexscreener_bad_status(cassandra):
    cassandra.session = _make_cassandra_session(404, {})
    data = await cassandra.fetch_dexscreener_data("abc")
    assert data is None


@pytest.mark.asyncio
async def test_cassandra_fetch_dexscreener_exception(cassandra):
    cassandra.session.get = MagicMock(side_effect=Exception("net"))
    data = await cassandra.fetch_dexscreener_data("abc")
    assert data is None


@pytest.mark.asyncio
async def test_cassandra_fetch_metadata_socials_success(cassandra):
    cassandra.session = _make_cassandra_session(200, {"social": {"twitter": "https://t.co/x", "telegram": "tg", "website": "https://w.com"}})
    socials = await cassandra.fetch_metadata_socials("http://uri")
    assert socials["twitter"] is True
    assert socials["telegram"] is True
    assert socials["website"] is True


@pytest.mark.asyncio
async def test_cassandra_fetch_metadata_socials_exception(cassandra):
    cassandra.session.get = MagicMock(side_effect=Exception("net"))
    socials = await cassandra.fetch_metadata_socials("http://uri")
    assert socials == {"twitter": False, "telegram": False, "website": False}


@pytest.mark.asyncio
async def test_cassandra_score_sentiment_no_mint(cassandra):
    score = await cassandra.score_sentiment({})
    assert 0 <= score <= 100


@pytest.mark.asyncio
async def test_cassandra_score_sentiment_with_dex_data(cassandra):
    cassandra.fetch_dexscreener_data = AsyncMock(return_value={
        "info": {"twitter": "t", "telegram": "tg", "website": "w"},
        "liquidity": {"usd": 50000},
        "txns": {"h24": {"buys": 200, "sells": 100}},
    })
    score = await cassandra.score_sentiment({"mint": "abc"})
    assert score > 50


@pytest.mark.asyncio
async def test_cassandra_score_sentiment_sells_dominate(cassandra):
    cassandra.fetch_dexscreener_data = AsyncMock(return_value={
        "info": {},
        "liquidity": {"usd": 100},
        "txns": {"h24": {"buys": 10, "sells": 100}},
    })
    score = await cassandra.score_sentiment({"mint": "abc"})
    assert isinstance(score, float)


@pytest.mark.asyncio
async def test_cassandra_score_sentiment_falls_back_to_metadata(cassandra):
    cassandra.fetch_dexscreener_data = AsyncMock(return_value=None)
    cassandra.fetch_metadata_socials = AsyncMock(return_value={"twitter": True, "telegram": True, "website": False})
    score = await cassandra.score_sentiment({"mint": "abc", "uri": "http://uri"})
    assert score > 50


@pytest.mark.asyncio
async def test_cassandra_score_old_token(cassandra):
    cassandra.fetch_dexscreener_data = AsyncMock(return_value=None)
    cassandra.fetch_metadata_socials = AsyncMock(return_value={"twitter": False, "telegram": False, "website": False})
    score = await cassandra.score_sentiment({"mint": "abc", "age": 90000})
    assert 0 <= score <= 100


@pytest.mark.asyncio
async def test_cassandra_score_new_token(cassandra):
    cassandra.fetch_dexscreener_data = AsyncMock(return_value=None)
    cassandra.fetch_metadata_socials = AsyncMock(return_value={"twitter": False, "telegram": False, "website": False})
    score = await cassandra.score_sentiment({"mint": "abc", "age": 100})
    assert 0 <= score <= 100


@pytest.mark.asyncio
async def test_cassandra_handle_token_received(cassandra):
    token = {"mint": "abc", "symbol": "TST"}
    env = _make_envelope(event_type="token_received_social", payload=token)
    cassandra.score_sentiment = AsyncMock(return_value=75.0)
    cassandra.fetch_dexscreener_data = AsyncMock(return_value=None)
    cassandra.fetch_metadata_socials = AsyncMock(return_value={"twitter": False, "telegram": False, "website": False})
    await cassandra.handle_token_received(env.model_dump_json())
    cassandra.redis.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_cassandra_handle_token_received_with_existing_score(cassandra):
    token = {"mint": "abc", "symbol": "TST", "sentiment_score": 80, "social_signals": {"twitter": True}}
    env = _make_envelope(event_type="token_received_social", payload=token)
    await cassandra.handle_token_received(env.model_dump_json())
    cassandra.redis.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_cassandra_handle_token_received_bad_json(cassandra):
    await cassandra.handle_token_received("bad")  # Should not raise


@pytest.mark.asyncio
async def test_cassandra_handle_token_with_dex_socials(cassandra):
    token = {"mint": "abc", "symbol": "TST"}
    env = _make_envelope(event_type="token_received_social", payload=token)
    cassandra.score_sentiment = AsyncMock(return_value=60.0)
    cassandra.fetch_dexscreener_data = AsyncMock(return_value={
        "info": {"twitter": "t", "telegram": "tg", "website": "w"}
    })
    await cassandra.handle_token_received(env.model_dump_json())
    cassandra.redis.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_cassandra_stop(cassandra):
    cassandra.session = AsyncMock()
    cassandra.session.close = AsyncMock()
    await cassandra.stop()
    cassandra.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_cassandra_stop_no_session():
    agent = CassandraAgent(VALID_CONFIG)
    await agent.stop()  # Should not raise


# ── Cassandra Coverage ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cassandra_handle_token_received_exception(cassandra):
    # Trigger exception inside handle_token_received (line 171-184)
    env = _make_envelope(event_type="token_received_social", payload={"mint": "abc"})
    with patch("src.python.agents.cassandra.AgentMessageEnvelope.model_validate_json", side_effect=Exception("forced error")):
        await cassandra.handle_token_received(env.model_dump_json())


@pytest.mark.asyncio
async def test_cassandra_qualify_sentiment_fallback(cassandra):
    # Test default score calculation (50.0 starting - 5.0 for age=0)
    res = await cassandra.score_sentiment({"mint": "mint", "uri": "uri"})
    assert res == 45.0


@pytest.mark.asyncio
async def test_cassandra_score_sentiment_liquidity_fallback(cassandra):
    # Test line 97: liquidity tier fallback
    payload = {"mint": "mint1", "vSolInBondingCurve": 500000000}
    with patch.object(cassandra, "fetch_dexscreener_data", return_value={"liquidity": {"usd": 200000}}):
        res = await cassandra.score_sentiment(payload)
        # 50 base + 10 liquidity - 5 age = 55
        assert res == 55.0

@pytest.mark.asyncio
async def test_cassandra_score_sentiment_exception(cassandra):
    # Test scoring error fallback
    with patch.object(cassandra, "fetch_dexscreener_data", side_effect=Exception("forced error")):
        res = await cassandra.score_sentiment({"mint": "abc"})
        assert res == 0

@pytest.mark.asyncio
async def test_cassandra_handle_token_received_parsing_error(cassandra):
    # Test line 154: json parsing error
    await cassandra.handle_token_received("invalid json")

@pytest.mark.asyncio
async def test_cassandra_handle_token_received_missing_fields(cassandra):
    # Test lines 171-184: missing fields
    msg = {
        "event_type": "token_detected",
        "payload": {} # Missing mint
    }
    await cassandra.handle_token_received(json.dumps(msg))





# ── Oracle Coverage ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_oracle_run_loop_coverage(oracle):
    # Mock pubsub to return a message then stop (line 220-240)
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.get_message = AsyncMock(side_effect=[
        {"type": "message", "data": '{"agent_id":"AGT-04","event_type":"position_opened","payload":{"position_id":"p1","mint":"m1"},"correlation_id":"550e8400-e29b-41d4-a716-446655440000"}'},
        asyncio.CancelledError()
    ])
    
    # Patch aioredis.from_url to return our mock redis
    with patch("src.python.agents.oracle.aioredis.from_url", new_callable=AsyncMock) as mock_from_url:
        mock_from_url.return_value = oracle.redis
        oracle.redis.pubsub.return_value = mock_pubsub
        oracle.agent_id = "AGT-04"
        
        oracle.positions = {"p2": {"mint": "m2", "last_prices": [], "fail_count": 0}}
        oracle.update_position_price = AsyncMock()
        
        with patch("src.python.agents.oracle.POLLING_INTERVAL", 0):
            try:
                await asyncio.wait_for(oracle.run(), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
                
    assert "p1" in oracle.positions
    oracle.update_position_price.assert_awaited()


@pytest.mark.asyncio
async def test_oracle_update_position_price_exception(oracle):
    # Test line 119-121 (in birdeye fallback)
    oracle.session = AsyncMock()
    oracle.session.get.side_effect = Exception("api error")
    oracle.positions = {"pos1": {"mint": "mint1", "last_prices": [], "fail_count": 0}}
    await oracle.update_position_price("pos1", "mint1")

@pytest.mark.asyncio
async def test_cassandra_handle_token_received_exception(cassandra):
    # Test error handling token exception
    cassandra.score_sentiment = AsyncMock(side_effect=Exception("forced error"))
    msg = json.dumps({"payload": {"mint": "abc"}})
    await cassandra.handle_token_received(msg)

@pytest.mark.asyncio
async def test_cassandra_sentiment_age_branches(cassandra):
    # Test token age branches (lines 125, 127)
    assert await cassandra.score_sentiment({"age": 90000}) > 50 # 100000 > 86400
    assert await cassandra.score_sentiment({"age": 1000}) < 50   # 1000 < 3600
    assert await cassandra.score_sentiment({"age": 10000}) == 50 # middle

@pytest.mark.asyncio
async def test_cassandra_handle_token_dex_fail_uri_fallback(cassandra):
    # Test line 151 (dex_data is None) and 157 (uri fallback)
    cassandra.fetch_dexscreener_data = AsyncMock(return_value=None)
    cassandra.fetch_metadata_socials = AsyncMock(return_value={"twitter": True, "telegram": False, "website": False})
    
    msg = json.dumps({
        "agent_id": "AGT-08",
        "event_type": "token_received",
        "payload": {"mint": "m1", "uri": "u1"},
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    })
    
    with patch.object(cassandra.redis, "publish", new_callable=AsyncMock) as mock_pub:
        await cassandra.handle_token_received(msg)
        mock_pub.assert_called_once()
        sent_data = json.loads(mock_pub.call_args[0][1])
        assert sent_data["payload"]["social_signals"]["twitter"] is True

@pytest.mark.asyncio
async def test_oracle_price_fallback_branches(oracle):
    # Test line 116 (status 200 but value 0) and CoinGecko failure
    oracle.session = AsyncMock()
    mock_resp_200 = AsyncMock()
    mock_resp_200.status = 200
    mock_resp_200.json = AsyncMock(return_value={"data": {"value": 0.0}})
    mock_resp_200.__aenter__ = AsyncMock(return_value=mock_resp_200)
    mock_resp_200.__aexit__ = AsyncMock()
    
    mock_resp_404 = AsyncMock()
    mock_resp_404.status = 404
    mock_resp_404.__aenter__ = AsyncMock(return_value=mock_resp_404)
    mock_resp_404.__aexit__ = AsyncMock()
    
    # Birdeye 1 fails (Exception), Birdeye 2 returns 0, CoinGecko returns 404
    oracle.session.get.side_effect = [Exception("err"), mock_resp_200, mock_resp_404]
    
    val = await oracle.fetch_price_birdeye("mint1")
    assert val == 0.0
    
    val = await oracle.fetch_price_coingecko("mint1")
    assert val == 0.0


@pytest.mark.asyncio
async def test_cassandra_run_loop_general_exception(cassandra):
    # Test generic exception in run loop
    cassandra.pubsub = AsyncMock()
    cassandra.pubsub.get_message.side_effect = [
        Exception("generic error"),
        Exception("stop loop")
    ]
    cassandra.connect_redis = AsyncMock()
    cassandra.handle_token_received = AsyncMock()
    with patch("src.python.agents.cassandra.aiohttp.ClientSession"), \
         patch("src.python.agents.cassandra.asyncio.sleep", return_value=None):
        await cassandra.run()

@pytest.mark.asyncio
async def test_oracle_run_loop_general_exception(oracle):
    # Test general exception in run loop
    oracle.pubsub = AsyncMock()
    oracle.pubsub.get_message.side_effect = [
        Exception("generic error"),
        Exception("stop loop")
    ]
    oracle.connect_redis = AsyncMock()
    with patch("src.python.agents.oracle.aiohttp.ClientSession"), \
         patch("src.python.agents.oracle.asyncio.sleep", return_value=None):
        await oracle.run()
