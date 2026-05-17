import pytest
import asyncio
import json
import requests
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.anansi import AnansiAgent, main

# Valid base58 strings for Solana addresses
VALID_MINT = "So11111111111111111111111111111111111111112"

@pytest.fixture
def config():
    return {
        "system": {"environment": "paper"},
        "qualification": {
            "min_lp_burned_pct": 85,
            "max_rugcheck_score": 999,
            "max_dev_holding_pct": 95,
            "min_market_cap_sol": 5,
            "max_market_cap_sol": 150,
            "min_bonding_curve_progress": 0
        },
        "trading": {"position_size_sol": 0.1}
    }

@pytest.fixture
def agent(config):
    a = AnansiAgent(config)
    a.redis = AsyncMock()
    return a

@pytest.mark.asyncio
async def test_anansi_connect_redis(agent):
    mock_redis = AsyncMock()
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
    
    with patch("aioredis.from_url", AsyncMock(return_value=mock_redis)):
        await agent.connect_redis()
        assert agent.redis == mock_redis

@pytest.mark.asyncio
async def test_fetch_rugcheck_summary_cached(agent):
    agent._rugcheck_cache["mint123"] = {"cached": True}
    result = await agent._fetch_rugcheck_summary("mint123")
    assert result == {"cached": True}

@pytest.mark.asyncio
async def test_fetch_rugcheck_summary_request(agent):
    with patch.object(agent.api_manager, "request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {"score": 500}
        result = await agent._fetch_rugcheck_summary("mint_new")
        assert result == {"score": 500}
        assert agent._rugcheck_cache["mint_new"] == {"score": 500}

@pytest.mark.asyncio
async def test_check_g1_mint_authority(agent):
    agent._rugcheck_cache["m1"] = {"token": {"mintAuthority": None}}
    assert await agent.check_g1_mint_authority("m1") is True
    
    agent._rugcheck_cache["m2"] = {"token": {"mintAuthority": "addr"}}
    assert await agent.check_g1_mint_authority("m2") is False

@pytest.mark.asyncio
async def test_check_g2_freeze_authority(agent):
    agent._rugcheck_cache["m1"] = {"token": {"freezeAuthority": None}}
    assert await agent.check_g2_freeze_authority("m1") is True
    
    agent._rugcheck_cache["m2"] = {"token": {"freezeAuthority": "addr"}}
    assert await agent.check_g2_freeze_authority("m2") is False

@pytest.mark.asyncio
async def test_check_g3_lp_lock(agent):
    agent._rugcheck_cache["m1"] = {"lp": {"burnedPct": 90}}
    assert await agent.check_g3_lp_lock("m1") is True
    
    agent._rugcheck_cache["m2"] = {"lp": {"burnedPct": 10}}
    assert await agent.check_g3_lp_lock("m2") is False

@pytest.mark.asyncio
async def test_check_g6_rugcheck_score(agent):
    agent._rugcheck_cache["m1"] = {"score": 100}
    assert await agent.check_g6_rugcheck_score("m1") is True
    
    agent._rugcheck_cache["m2"] = {"score": 2000}
    assert await agent.check_g6_rugcheck_score("m2") is False

@pytest.mark.asyncio
async def test_check_g7_liquidity_size(agent):
    assert await agent.check_g7_liquidity_size({"marketCapSol": 10}) is True
    assert await agent.check_g7_liquidity_size({"marketCapSol": 1}) is False
    assert await agent.check_g7_liquidity_size({"market_cap_usd": 2000}) is True # MC ~10 SOL

@pytest.mark.asyncio
async def test_check_g8_social_metadata(agent):
    with patch("src.python.agents.anansi.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"social": {"twitter": "t"}}
        assert await agent.check_g8_social_metadata("uri") is True
        
        mock_get.return_value.json.return_value = {"social": {}}
        assert await agent.check_g8_social_metadata("uri") is False

@pytest.mark.asyncio
async def test_check_g9_duplicate(agent):
    agent.redis.exists.return_value = False
    assert await agent.check_g9_duplicate("mint1") is True
    
    agent.redis.exists.return_value = True
    assert await agent.check_g9_duplicate("mint1") is False

@pytest.mark.asyncio
async def test_check_g12_bonding_curve(agent):
    assert await agent.check_g12_bonding_curve({"bondingCurveProgress": 50}) is True
    agent.config["qualification"]["min_bonding_curve_progress"] = 60
    assert await agent.check_g12_bonding_curve({"bondingCurveProgress": 50}) is False
    
    # Test graduated allowance
    assert await agent.check_g12_bonding_curve({"is_graduated": True, "bondingCurveProgress": 100}) is True
    assert await agent.check_g12_bonding_curve({"complete": True}) is True

@pytest.mark.asyncio
async def test_qualify_token_paper_mode(agent):
    agent.is_paper_mode = True
    corr_id = str(uuid.uuid4())
    token = {"mint": VALID_MINT, "symbol": "TKN", "marketCapSol": 10, "bondingCurveProgress": 10}
    
    agent.check_g1_mint_authority = AsyncMock(return_value=True)
    agent.check_g2_freeze_authority = AsyncMock(return_value=True)
    agent.check_g10_honeypot = AsyncMock(return_value=True)
    agent.check_g11_sentiment = AsyncMock(return_value=True)
    
    result = await agent.qualify_token(token, corr_id)
    assert result is True
    agent.redis.publish.assert_called()

@pytest.mark.asyncio
async def test_qualify_token_graduated(agent):
    agent.is_paper_mode = False
    corr_id = str(uuid.uuid4())
    token = {
        "mint": VALID_MINT, 
        "symbol": "ACT", 
        "is_graduated": True, 
        "marketCapSol": 500,
        "ta_signal": "bullish" # Graduated tokens require bullish TA
    }
    
    agent.check_g1_mint_authority = AsyncMock(return_value=True)
    agent.check_g2_freeze_authority = AsyncMock(return_value=True)
    agent.check_g3_lp_lock = AsyncMock(return_value=True)
    agent.check_g4_dev_holdings = AsyncMock(return_value=True)
    agent.check_g5_top10_concentration = AsyncMock(return_value=True)
    agent.check_g6_rugcheck_score = AsyncMock(return_value=True)
    agent.check_g7_liquidity_size = AsyncMock(return_value=True)
    agent.check_g8_social_metadata = AsyncMock(return_value=True)
    agent.check_g9_duplicate = AsyncMock(return_value=True)
    agent.check_g10_honeypot = AsyncMock(return_value=True)
    agent.check_g11_sentiment = AsyncMock(return_value=True)
    agent.check_g12_bonding_curve = AsyncMock(return_value=True) # G12 should pass for graduated
    
    result = await agent.qualify_token(token, corr_id)
    assert result is True

@pytest.mark.asyncio
async def test_handle_token_received(agent):
    agent.qualify_token = AsyncMock()
    corr_id = str(uuid.uuid4())
    envelope = {
        "agent_id": "AGT-12", # Nofx or something
        "event_type": "token_received",
        "payload": {"mint": "abc"},
        "correlation_id": corr_id,
        "envelope_id": str(uuid.uuid4()),
        "timestamp_utc": "2024-01-01T00:00:00Z"
    }
    await agent.handle_token_received(json.dumps(envelope))
    agent.qualify_token.assert_called_with({"mint": "abc"}, corr_id)

@pytest.mark.asyncio
async def test_anansi_run_loop(agent):
    agent.running = True
    agent.connect_redis = AsyncMock()
    agent.pubsub = AsyncMock()
    
    # Return a valid message once, then return None
    msg = {"data": json.dumps({
        "agent_id": "AGT-01", "event_type": "token_received", "payload": {"mint": "m"},
        "correlation_id": str(uuid.uuid4()), "envelope_id": str(uuid.uuid4()), "timestamp_utc": "2024-01-01T00:00:00Z"
    })}
    agent.pubsub.get_message.side_effect = [msg, None, None]
    agent.handle_token_received = AsyncMock()
    
    async def stop_loop(*args, **kwargs):
        agent.running = False
        return None
    
    with patch("src.python.agents.anansi.is_operational_window_active", return_value=True), \
         patch("src.python.agents.anansi.asyncio.sleep", side_effect=stop_loop):
        await agent.run()
    agent.handle_token_received.assert_awaited()

@pytest.mark.asyncio
async def test_check_g4_dev_holdings(agent):
    # Method name is check_g4_dev_holdings
    with patch.object(agent, "get_rpc_url", return_value="url"), \
         patch("src.python.agents.anansi.requests.post") as mock_post:
        
        # Mock responses for getTokenLargestAccounts and getTokenSupply
        mock_post.side_effect = [
            MagicMock(json=lambda: {"result": {"value": [{"uiAmountString": "5"}]}}), # dev 5%
            MagicMock(json=lambda: {"result": {"value": {"amount": "100", "decimals": 0}}})
        ]
        assert await agent.check_g4_dev_holdings("m1") is True
        
        mock_post.side_effect = [
            MagicMock(json=lambda: {"result": {"value": [{"uiAmountString": "96"}]}}), # dev 96%
            MagicMock(json=lambda: {"result": {"value": {"amount": "100", "decimals": 0}}})
        ]
        assert await agent.check_g4_dev_holdings("m2") is False

@pytest.mark.asyncio
async def test_check_g5_concentration(agent):
    with patch.object(agent, "get_rpc_url", return_value="url"), \
         patch("src.python.agents.anansi.requests.post") as mock_post:
        
        mock_post.side_effect = [
            MagicMock(json=lambda: {"result": {"value": [{"uiAmountString": "10"}, {"uiAmountString": "5"}]}}),
            MagicMock(json=lambda: {"result": {"value": {"amount": "100", "decimals": 0}}})
        ]
        assert await agent.check_g5_top10_concentration("m1") is True
        
        mock_post.side_effect = [
            MagicMock(json=lambda: {"result": {"value": [{"uiAmountString": "80"}, {"uiAmountString": "20"}]}}),
            MagicMock(json=lambda: {"result": {"value": {"amount": "100", "decimals": 0}}})
        ]
        assert await agent.check_g5_top10_concentration("m2") is False

@pytest.mark.asyncio
async def test_check_g10_honeypot_logic(agent):
    with patch.object(agent, "get_rpc_url", return_value="url"), \
         patch("src.python.agents.anansi.requests.post") as mock_post:
        
        # Valid safe token
        mock_post.return_value.json.return_value = {
            "result": {"value": {"data": {"parsed": {"info": {"freezeAuthority": None, "mintAuthority": None}}}}}
        }
        assert await agent.check_g10_honeypot(VALID_MINT) is True
        
        # Unsafe token
        mock_post.return_value.json.return_value = {
            "result": {"value": {"data": {"parsed": {"info": {"freezeAuthority": "addr"}}}}}
        }
        assert await agent.check_g10_honeypot(VALID_MINT) is False

@pytest.mark.asyncio
async def test_check_g11_sentiment_logic(agent):
    assert await agent.check_g11_sentiment("m") is True
    # Test failure if needed, but current implementation is hardcoded True

@pytest.mark.asyncio
async def test_qualify_token_all_gates_fail(agent):
    agent.is_paper_mode = False
    corr_id = str(uuid.uuid4())
    token = {"mint": VALID_MINT, "symbol": "T", "marketCapSol": 100}
    
    gates = [
        "check_g1_mint_authority", "check_g2_freeze_authority", "check_g3_lp_lock",
        "check_g4_dev_holdings", "check_g5_top10_concentration", "check_g6_rugcheck_score",
        "check_g7_liquidity_size", "check_g8_social_metadata", "check_g9_duplicate",
        "check_g10_honeypot", "check_g11_sentiment", "check_g12_bonding_curve"
    ]
    
    for gate in gates:
        with patch.object(agent, gate, new_callable=AsyncMock) as mock_gate:
            mock_gate.return_value = False
            res = await agent.qualify_token(token, corr_id)
            assert res is False

@pytest.mark.asyncio
async def test_handle_token_received_invalid_json(agent):
    await agent.handle_token_received("invalid")
    agent.redis.publish.assert_not_called()

@pytest.mark.asyncio
async def test_handle_token_received_missing_payload(agent):
    await agent.handle_token_received(json.dumps({"agent_id": "AGT-01"}))
    agent.redis.publish.assert_not_called()

@pytest.mark.asyncio
async def test_qualify_token_exception(agent):
    agent.check_g1_mint_authority = AsyncMock(side_effect=Exception("error"))
    res = await agent.qualify_token({"mint": VALID_MINT}, str(uuid.uuid4()))
    assert res is False

@pytest.mark.asyncio
async def test_stop_no_pubsub(agent):
    agent.pubsub = None
    await agent.stop()
    assert agent.running is False
    agent.redis.close.assert_called()

@pytest.mark.asyncio
async def test_anansi_main_keyboard_interrupt():
    m = mock_open(read_data="qualification:\n  min_market_cap_sol: 5\n")
    with patch("src.python.agents.anansi.open", m), \
         patch("src.python.agents.anansi.AnansiAgent") as mock_agent_class, \
         patch("src.python.agents.anansi.validate_config", return_value=(True, None)):
        
        mock_agent_instance = mock_agent_class.return_value
        mock_agent_instance.run = AsyncMock(side_effect=KeyboardInterrupt())
        mock_agent_instance.stop = AsyncMock()
        
        from src.python.agents.anansi import main
        await main()
            
        assert mock_agent_instance.run.called
        assert mock_agent_instance.stop.called

@pytest.mark.asyncio
async def test_anansi_main_config_error():
    m = mock_open(read_data="qualification:\n  min_market_cap_sol: 5\n")
    with patch("src.python.agents.anansi.open", m), \
         patch("src.python.agents.anansi.validate_config", return_value=(False, "error")), \
         patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        
        with pytest.raises(SystemExit) as exc:
            from src.python.agents.anansi import main
            await main()
        assert exc.value.code == 1

@pytest.mark.asyncio
async def test_check_freeze_authority_rpc(agent):
    with patch.object(agent, "get_rpc_url", return_value="url"), \
         patch("src.python.agents.anansi.requests.post") as mock_post:
        # Valid response
        mock_post.return_value.json.return_value = {
            "result": {"value": {"data": {"parsed": {"info": {"freezeAuthority": None}}}}}
        }
        assert await agent._check_freeze_authority_rpc("m") is True

        # Invalid response
        mock_post.return_value.json.return_value = {"result": None}
        assert await agent._check_freeze_authority_rpc("m") is False

        # Exception
        mock_post.side_effect = Exception("error")
        assert await agent._check_freeze_authority_rpc("m") is False

@pytest.mark.asyncio
async def test_check_lp_lock_rpc(agent):
    with patch.object(agent, "get_rpc_url", return_value="url"), \
         patch("src.python.agents.anansi.requests.post") as mock_post:
        # Valid response with LP
        mock_post.return_value.json.return_value = {
            "result": {"value": [{"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmountString": "100"}}}}}}]}
        }
        assert await agent._check_lp_lock_rpc("m") is True

        # No accounts
        mock_post.return_value.json.return_value = {"result": {"value": []}}
        assert await agent._check_lp_lock_rpc("m") is False

        # Exception
        mock_post.side_effect = Exception("error")
        assert await agent._check_lp_lock_rpc("m") is False

@pytest.mark.asyncio
async def test_check_g3_lp_lock_fallback(agent):
    with patch.object(agent, "_fetch_rugcheck_summary", return_value=None), \
         patch.object(agent, "_check_lp_lock_rpc", new_callable=AsyncMock) as mock_rpc:
        mock_rpc.return_value = True
        assert await agent.check_g3_lp_lock("m") is True
        mock_rpc.assert_called()

@pytest.mark.asyncio
async def test_get_rpc_url_default(agent):
    res = await agent.get_rpc_url()
    assert isinstance(res, str)
    assert res.startswith("http")

@pytest.mark.asyncio
async def test_check_g1_mint_authority_fallback(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value=None)
    agent._check_mint_authority_rpc = AsyncMock(return_value=True)
    assert await agent.check_g1_mint_authority("m") is True
    agent._check_mint_authority_rpc.assert_called()

@pytest.mark.asyncio
async def test_check_g2_freeze_authority_fallback(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value=None)
    agent._check_freeze_authority_rpc = AsyncMock(return_value=True)
    assert await agent.check_g2_freeze_authority("m") is True
    agent._check_freeze_authority_rpc.assert_called()

@pytest.mark.asyncio
async def test_check_g2_freeze_authority_exception(agent):
    agent._fetch_rugcheck_summary = AsyncMock(side_effect=Exception("error"))
    assert await agent.check_g2_freeze_authority("m") is False

@pytest.mark.asyncio
async def test_check_g6_rugcheck_score_exception(agent):
    agent._fetch_rugcheck_summary = AsyncMock(side_effect=Exception("error"))
    assert await agent.check_g6_rugcheck_score("m") is False

@pytest.mark.asyncio
async def test_fetch_rugcheck_summary_error(agent):
    with patch.object(agent.api_manager, "request", side_effect=Exception("API Error")):
        with pytest.raises(Exception, match="API Error"):
            await agent._fetch_rugcheck_summary("m")
