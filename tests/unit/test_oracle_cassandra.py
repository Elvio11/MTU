import pytest
import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.oracle import OracleAgent, main as oracle_main
from src.python.agents.cassandra import CassandraAgent, main as cassandra_main

# Valid base58 strings for Solana addresses
VALID_MINT = "So11111111111111111111111111111111111111112"

@pytest.fixture
def oracle_agent():
    config = {"system": {"environment": "paper"}}
    agent = OracleAgent(config)
    agent.redis = AsyncMock()
    agent.session = AsyncMock()
    return agent

@pytest.fixture
def cassandra_agent():
    config = {"system": {"environment": "paper"}}
    agent = CassandraAgent(config)
    agent.redis = AsyncMock()
    agent.session = AsyncMock()
    return agent

@pytest.mark.asyncio
async def test_oracle_connect_redis(oracle_agent):
    mock_redis = AsyncMock()
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
    
    with patch("aioredis.from_url", AsyncMock(return_value=mock_redis)):
        await oracle_agent.connect_redis()
        assert oracle_agent.redis == mock_redis

@pytest.mark.asyncio
async def test_oracle_update_position_price(oracle_agent):
    oracle_agent.positions["POS-1"] = {
        "mint": VALID_MINT, 
        "entry_price_sol": 1.0,
        "last_prices": [1.0],
        "fail_count": 0
    }
    with patch.object(oracle_agent, "fetch_price_jupiter", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = 1.1
        await oracle_agent.update_position_price("POS-1", VALID_MINT)
        assert oracle_agent.positions["POS-1"]["last_prices"][-1] == 1.1

@pytest.mark.asyncio
async def test_oracle_run_loop(oracle_agent):
    oracle_agent.connect_redis = AsyncMock()
    oracle_agent.pubsub = MagicMock()
    oracle_agent.pubsub.get_message = AsyncMock(return_value=None)
    oracle_agent.update_position_price = AsyncMock()
    oracle_agent.session = AsyncMock()
    
    call_count = 0
    def active_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise Exception("stop loop")
        return True
        
    with patch("src.python.agents.oracle.is_operational_window_active", side_effect=active_side_effect), \
         patch("src.python.agents.oracle.asyncio.sleep", return_value=None), \
         patch("src.python.agents.oracle.aiohttp.ClientSession", return_value=AsyncMock()):
        try:
            await oracle_agent.run()
        except Exception as e:
            if "stop loop" not in str(e): raise
        
    oracle_agent.connect_redis.assert_awaited()

@pytest.mark.asyncio
async def test_oracle_handle_position_opened(oracle_agent):
    corr_id = str(uuid.uuid4())
    env_id = str(uuid.uuid4())
    envelope = {
        "agent_id": "AGT-01", "event_type": "position_opened",
        "payload": {"position_id": "POS-1", "mint": VALID_MINT, "entry_price_sol": 1.0},
        "correlation_id": corr_id, "envelope_id": env_id, "timestamp_utc": "2024-01-01T00:00:00Z"
    }
    await oracle_agent.handle_position_opened(json.dumps(envelope))
    assert "POS-1" in oracle_agent.positions
    
    # Test error handling
    await oracle_agent.handle_position_opened("invalid json")

@pytest.mark.asyncio
async def test_oracle_fetch_price_exceptions(oracle_agent):
    oracle_agent.api_manager.request = AsyncMock(side_effect=Exception("api error"))
    assert await oracle_agent.fetch_price_jupiter("mint") == 0.0
    assert await oracle_agent.fetch_price_dexscreener("mint") == 0.0
    assert await oracle_agent.fetch_price_birdeye("mint") == 0.0
    assert await oracle_agent.fetch_price_coingecko("mint") == 0.0

@pytest.mark.asyncio
async def test_oracle_run_loop_off_hours(oracle_agent):
    oracle_agent.connect_redis = AsyncMock()
    oracle_agent.pubsub = MagicMock()
    oracle_agent.pubsub.unsubscribe = AsyncMock()
    call_count = 0
    def side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return False
        raise Exception("stop loop")

    with patch("src.python.agents.oracle.is_operational_window_active", side_effect=side_effect), \
         patch("src.python.agents.oracle.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch("src.python.agents.oracle.aiohttp.ClientSession", return_value=AsyncMock()):
        try:
            await oracle_agent.run()
        except Exception as e:
            if "stop loop" not in str(e): raise
    
    mock_sleep.assert_any_call(60)

@pytest.mark.asyncio
async def test_oracle_run_loop_exception(oracle_agent):
    oracle_agent.connect_redis = AsyncMock()
    oracle_agent.pubsub = AsyncMock()
    oracle_agent.pubsub.get_message = AsyncMock(side_effect=[Exception("loop error"), Exception("stop loop")])
    
    with patch("src.python.agents.oracle.is_operational_window_active", return_value=True), \
         patch("src.python.agents.oracle.asyncio.sleep", new_callable=AsyncMock), \
         patch("src.python.agents.oracle.aiohttp.ClientSession", return_value=AsyncMock()):
        try:
            await oracle_agent.run()
        except Exception as e:
            if "stop loop" not in str(e): raise

@pytest.mark.asyncio
async def test_oracle_fetch_prices(oracle_agent):
    oracle_agent.api_manager.request = AsyncMock()
    oracle_agent.api_manager.request.return_value = {VALID_MINT: {"usdPrice": "1.5"}}
    assert await oracle_agent.fetch_price_jupiter(VALID_MINT) == 1.5
    oracle_agent.api_manager.request.return_value = {"pairs": [{"priceUsd": "1.6"}]}
    assert await oracle_agent.fetch_price_dexscreener(VALID_MINT) == 1.6
    oracle_agent.api_manager.request.return_value = {"success": True, "data": {"value": 1.7}}
    assert await oracle_agent.fetch_price_birdeye(VALID_MINT) == 1.7
    oracle_agent._sol_price_cache = 150.0
    oracle_agent.api_manager.request.return_value = {"solana": {"usd": 150.0}}
    assert await oracle_agent.fetch_price_coingecko(VALID_MINT) == 150.0

@pytest.mark.asyncio
async def test_oracle_update_position_price_flow(oracle_agent):
    oracle_agent.positions["P1"] = {"mint": VALID_MINT, "last_prices": [1.0], "fail_count": 0}
    oracle_agent.redis = AsyncMock()
    with patch.object(oracle_agent, "fetch_price_jupiter", return_value=1.1):
        await oracle_agent.update_position_price("P1", VALID_MINT)
        assert oracle_agent.positions["P1"]["last_prices"][-1] == 1.1
        oracle_agent.redis.publish.assert_awaited()
    oracle_agent.positions["P1"]["fail_count"] = 2
    with patch.object(oracle_agent, "fetch_price_jupiter", return_value=0.0), \
         patch.object(oracle_agent, "fetch_price_dexscreener", return_value=0.0), \
         patch.object(oracle_agent, "fetch_price_birdeye", return_value=0.0):
        await oracle_agent.update_position_price("P1", VALID_MINT)
        assert oracle_agent.positions["P1"]["fail_count"] == 3
        last_call = oracle_agent.redis.publish.call_args_list[-1]
        assert "price_unavailable" in last_call[0][1]

@pytest.mark.asyncio
async def test_oracle_fetch_ta_data(oracle_agent):
    oracle_agent.birdeye_key = "key"
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"success": True, "data": {"items": [{"c": 100, "v": 1000}]}})
    
    # Session.get should be a MagicMock that returns an object with __aenter__
    # AsyncMock for session.get makes it return a coroutine when called, which breaks async with
    oracle_agent.session.get = MagicMock()
    oracle_agent.session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    oracle_agent.session.get.return_value.__aexit__ = AsyncMock()
    
    res = await oracle_agent.fetch_ta_data(VALID_MINT)
    assert res["prices"] == [100.0]
    assert res["volumes"] == [1000.0]

@pytest.mark.asyncio
async def test_oracle_perform_ta_analysis(oracle_agent):
    oracle_agent.fetch_ta_data = AsyncMock(return_value={
        "prices": [10.0] * 20, # Flat
        "volumes": [1000.0] * 20
    })
    token = {"mint": VALID_MINT}
    res = await oracle_agent.perform_ta_analysis(token)
    assert res["signal"] == "neutral"
    
    # Test oversold
    with patch("src.python.agents.oracle.calculate_rsi", return_value=20.0):
        res = await oracle_agent.perform_ta_analysis(token)
        assert res["signal"] == "bullish"
    
    # Test volume breakout
    with patch("src.python.agents.oracle.calculate_rsi", return_value=50.0), \
         patch("src.python.agents.oracle.calculate_volume_trend", return_value=2.0):
        res = await oracle_agent.perform_ta_analysis(token)
        assert res["signal"] == "bullish"

@pytest.mark.asyncio
async def test_oracle_fetch_ohlcv_birdeye(oracle_agent):
    oracle_agent.birdeye_key = "key"
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"success": True, "data": {"items": [{"value": 100}]}})
    oracle_agent.session.get = MagicMock()
    oracle_agent.session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    
    res = await oracle_agent.fetch_ohlcv_birdeye(VALID_MINT)
    assert res == [100.0]

@pytest.mark.asyncio
async def test_oracle_handle_token_received(oracle_agent):
    oracle_agent.redis = AsyncMock()
    oracle_agent.perform_ta_analysis = AsyncMock(return_value={"signal": "bullish", "rsi": 50, "volume_trend": 1.0})
    
    token = {"mint": VALID_MINT, "symbol": "TKN", "is_graduated": True}
    c_id = str(uuid.uuid4())
    e_id = str(uuid.uuid4())
    envelope = {
        "agent_id": "AGT-01",
        "event_type": "token_received",
        "payload": token,
        "correlation_id": c_id,
        "envelope_id": e_id,
        "timestamp_utc": "2024-01-01T00:00:00Z"
    }
    
    await oracle_agent.handle_token_received(json.dumps(envelope))
    oracle_agent.redis.publish.assert_awaited()
    # Check published message
    published = json.loads(oracle_agent.redis.publish.call_args[0][1])
    assert published["event_type"] == "token_ta_scored"
    assert published["payload"]["ta_signal"] == "bullish"

@pytest.mark.asyncio
async def test_cassandra_run_loop(cassandra_agent):
    cassandra_agent.connect_redis = AsyncMock()
    cassandra_agent.pubsub = MagicMock()
    cassandra_agent.pubsub.get_message = AsyncMock(return_value=None)
    cassandra_agent.session = AsyncMock()
    call_count = 0
    def active_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise Exception("stop loop")
        return True
    with patch("src.python.agents.cassandra.is_operational_window_active", side_effect=active_side_effect), \
         patch("src.python.agents.cassandra.asyncio.sleep", return_value=None), \
         patch("src.python.agents.cassandra.aiohttp.ClientSession", return_value=AsyncMock()):
        try:
            await cassandra_agent.run()
        except Exception as e:
            if "stop loop" not in str(e): raise
    cassandra_agent.connect_redis.assert_awaited()

@pytest.mark.asyncio
async def test_cassandra_fetch_dexscreener_error(cassandra_agent):
    cassandra_agent.api_manager.request = AsyncMock(side_effect=Exception("api down"))
    result = await cassandra_agent.fetch_dexscreener_data("mint")
    assert result is None

@pytest.mark.asyncio
async def test_cassandra_fetch_metadata_socials_error(cassandra_agent):
    cassandra_agent.api_manager.request = AsyncMock(side_effect=Exception("api down"))
    result = await cassandra_agent.fetch_metadata_socials("uri")
    assert result == {"twitter": False, "telegram": False, "website": False}

@pytest.mark.asyncio
async def test_cassandra_score_sentiment_branches(cassandra_agent):
    token = {"mint": "m1", "uri": "u1", "age": 86401}
    dex_data = {"info": {"twitter": "t"}, "liquidity": {"usd": 150000}, "txns": {"h24": {"buys": 200, "sells": 50}}}
    cassandra_agent.fetch_dexscreener_data = AsyncMock(return_value=dex_data)
    score = await cassandra_agent.score_sentiment(token)
    assert score == 90
    token = {"mint": "m2", "uri": "u2", "age": 500}
    dex_data = {"info": {}, "liquidity": {"usd": 20000}, "txns": {"h24": {"buys": 10, "sells": 100}}}
    cassandra_agent.fetch_dexscreener_data = AsyncMock(return_value=dex_data)
    cassandra_agent.fetch_metadata_socials = AsyncMock(return_value={"twitter": True, "telegram": False, "website": False})
    score = await cassandra_agent.score_sentiment(token)
    assert score == 60

@pytest.mark.asyncio
async def test_cassandra_run_loop_off_hours(cassandra_agent):
    cassandra_agent.connect_redis = AsyncMock()
    cassandra_agent.pubsub = MagicMock()
    cassandra_agent.pubsub.unsubscribe = AsyncMock()
    call_count = 0
    def side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return False
        raise Exception("stop loop")
    with patch("src.python.agents.cassandra.is_operational_window_active", side_effect=side_effect), \
         patch("src.python.agents.cassandra.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch("src.python.agents.cassandra.aiohttp.ClientSession", return_value=AsyncMock()):
        try:
            await cassandra_agent.run()
        except Exception as e:
            if "stop loop" not in str(e): raise
    mock_sleep.assert_any_call(60)

@pytest.mark.asyncio
async def test_cassandra_handle_token_received_exception(cassandra_agent):
    with patch("src.python.shared.envelope.AgentMessageEnvelope.model_validate_json", side_effect=Exception("invalid")):
        await cassandra_agent.handle_token_received("{}")

@pytest.mark.asyncio
async def test_cassandra_handle_token_received(cassandra_agent):
    cassandra_agent.redis = AsyncMock()
    corr_id = str(uuid.uuid4())
    env_id = str(uuid.uuid4())
    envelope = {
        "agent_id": "AGT-01", "event_type": "token_received",
        "payload": {"mint": VALID_MINT, "symbol": "T", "uri": "https://uri.com"},
        "correlation_id": corr_id, "envelope_id": env_id, "timestamp_utc": "2024-01-01T00:00:00Z"
    }
    with patch.object(cassandra_agent, "score_sentiment", return_value=85.0):
        await cassandra_agent.handle_token_received(json.dumps(envelope))
        cassandra_agent.redis.publish.assert_awaited()
    await cassandra_agent.handle_token_received("invalid")

@pytest.mark.asyncio
async def test_oracle_stop(oracle_agent):
    await oracle_agent.stop()
    assert oracle_agent.running is False
    oracle_agent.redis.close.assert_awaited()

@pytest.mark.asyncio
async def test_cassandra_stop(cassandra_agent):
    await cassandra_agent.stop()
    assert cassandra_agent.running is False
    cassandra_agent.redis.close.assert_awaited()
@pytest.mark.asyncio
async def test_oracle_main_keyboard_interrupt():
    m = mock_open(read_data="system:\n  environment: paper\n")
    with patch("src.python.agents.oracle.open", m), \
         patch("src.python.agents.oracle.OracleAgent") as mock_agent_class, \
         patch("src.python.agents.oracle.validate_config", return_value=(True, None)):
        
        mock_agent_instance = mock_agent_class.return_value
        mock_agent_instance.run = AsyncMock(side_effect=KeyboardInterrupt())
        mock_agent_instance.stop = AsyncMock()
        
        await oracle_main()
        assert mock_agent_instance.run.called
        assert mock_agent_instance.stop.called

@pytest.mark.asyncio
async def test_cassandra_main_keyboard_interrupt():
    m = mock_open(read_data="system:\n  environment: paper\n")
    with patch("src.python.agents.cassandra.open", m), \
         patch("src.python.agents.cassandra.CassandraAgent") as mock_agent_class, \
         patch("src.python.agents.cassandra.validate_config", return_value=(True, None)):
        
        mock_agent_instance = mock_agent_class.return_value
        mock_agent_instance.run = AsyncMock(side_effect=KeyboardInterrupt())
        mock_agent_instance.stop = AsyncMock()
        
        await cassandra_main()
        assert mock_agent_instance.run.called
        assert mock_agent_instance.stop.called

@pytest.mark.asyncio
async def test_oracle_main_config_error():
    m = mock_open(read_data="system:\n  environment: production\n")
    with patch("src.python.agents.oracle.open", m), \
         patch("src.python.agents.oracle.validate_config", return_value=(False, "error")), \
         patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        
        with pytest.raises(SystemExit) as exc:
            from src.python.agents.oracle import main
            await main()
        assert exc.value.code == 1

@pytest.mark.asyncio
async def test_cassandra_main_config_error():
    m = mock_open(read_data="system:\n  environment: paper\n")
    with patch("src.python.agents.cassandra.open", m), \
         patch("src.python.agents.cassandra.validate_config", return_value=(False, "error")), \
         patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        
        with pytest.raises(SystemExit) as exc:
            await cassandra_main()
        assert exc.value.code == 1

@pytest.mark.asyncio
async def test_cassandra_fetch_dexscreener_success(cassandra_agent):
    cassandra_agent.api_manager.request = AsyncMock(return_value={"pair": {"liquidity": 100}})
    res = await cassandra_agent.fetch_dexscreener_data("m")
    assert res == {"liquidity": 100}

@pytest.mark.asyncio
async def test_cassandra_fetch_metadata_socials_alt_keys(cassandra_agent):
    cassandra_agent.api_manager.request = AsyncMock(return_value={"Social": {"x": "twitter_link"}})
    res = await cassandra_agent.fetch_metadata_socials("u")
    assert res["twitter"] is True

@pytest.mark.asyncio
async def test_cassandra_score_sentiment_exception(cassandra_agent):
    # This will trigger the AGT-08: Scoring error: line
    with patch.object(cassandra_agent, "fetch_dexscreener_data", side_effect=Exception("scoring fail")):
        res = await cassandra_agent.score_sentiment({"mint": "m"})
        assert res == 0.0

@pytest.mark.asyncio
async def test_cassandra_handle_token_received_full(cassandra_agent):
    cassandra_agent.redis = AsyncMock()
    # Mock dexscreener info for handle_token_received
    cassandra_agent.fetch_dexscreener_data = AsyncMock(return_value={"info": {"twitter": "t", "telegram": "tg", "website": "w"}})
    envelope = {
        "agent_id": "AGT-01", "event_type": "token_received",
        "payload": {"mint": "m", "symbol": "S"},
        "correlation_id": str(uuid.uuid4()), "envelope_id": str(uuid.uuid4()), "timestamp_utc": "2024-01-01T00:00:00Z"
    }
    await cassandra_agent.handle_token_received(json.dumps(envelope))
    assert cassandra_agent.redis.publish.called

@pytest.mark.asyncio
async def test_cassandra_run_loop_resubscribe(cassandra_agent):
    cassandra_agent.connect_redis = AsyncMock()
    cassandra_agent.pubsub = MagicMock()
    cassandra_agent.pubsub.subscribe = AsyncMock()
    cassandra_agent.pubsub.unsubscribe = AsyncMock()
    cassandra_agent.pubsub.get_message = AsyncMock(return_value=None)
    
    call_count = 0
    def active_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1: return False # Off-hours, unsubscribe
        if call_count == 2: return True  # Window opens, resubscribe
        raise Exception("stop loop")

    with patch("src.python.agents.cassandra.is_operational_window_active", side_effect=active_side_effect), \
         patch("src.python.agents.cassandra.asyncio.sleep", return_value=None), \
         patch("src.python.agents.cassandra.aiohttp.ClientSession", return_value=AsyncMock()):
        try:
            await cassandra_agent.run()
        except Exception as e:
            if "stop loop" not in str(e): raise
    
    assert cassandra_agent.pubsub.subscribe.called

@pytest.mark.asyncio
async def test_oracle_fetch_price_coingecko_error(oracle_agent):
    oracle_agent.api_manager.request = AsyncMock(return_value=None)
    res = await oracle_agent.fetch_price_coingecko("m")
    assert res == 0.0
