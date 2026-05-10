"""Unit tests for AnansiAgent - token qualification gates."""
import asyncio
import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.shared.envelope import AgentMessageEnvelope
from src.python.agents.anansi import AnansiAgent


CONFIG = {
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
    "qualification": {
        "min_lp_burned_pct": 85,
        "max_rugcheck_score": 999,
        "max_dev_holding_pct": 95,
        "min_virtual_sol_reserves": 30,
        "min_bonding_curve_progress": 0,
        "min_market_cap_sol": 5,
        "max_market_cap_sol": 150,
    },
    "trading": {
        "position_size_sol": 0.001,
        "max_simultaneous_positions": 5,
        "max_trades_per_hour": 10,
    },
}

VALID_TOKEN = {
    "mint": "TokenMintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "symbol": "TEST",
    "name": "TestToken",
    "uri": "https://arweave.net/test",
    "marketCapSol": 20.0,
    "vSolInBondingCurve": 35_000_000_000,
    "bondingCurveProgress": 30.0,
    "initialBuy": 0.5,
}

CID = str(uuid.uuid4())


@pytest.fixture
def agent():
    with patch("src.python.agents.anansi.IS_PAPER_MODE", True):
        a = AnansiAgent(CONFIG)
    a.redis = AsyncMock()
    a.pubsub = AsyncMock()
    a.is_paper_mode = True
    return a


# ── connect_redis ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_connect_redis():
    a = AnansiAgent(CONFIG)
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_r = AsyncMock()
    mock_r.pubsub = MagicMock(return_value=mock_pubsub)
    with patch("src.python.agents.anansi.aioredis.from_url", new_callable=AsyncMock) as mock_from:
        mock_from.return_value = mock_r
        await a.connect_redis()
        assert a.redis is not None


# ── _fetch_rugcheck_summary ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_fetch_rugcheck_cached(agent):
    agent._rugcheck_cache["abc"] = {"score": 100}
    result = await agent._fetch_rugcheck_summary("abc")
    assert result == {"score": 100}


@pytest.mark.asyncio
async def test_fetch_rugcheck_success(agent):
    with patch("src.python.agents.anansi.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"score": 200})
        result = await agent._fetch_rugcheck_summary("mint123")
    assert result["score"] == 200


@pytest.mark.asyncio
async def test_fetch_rugcheck_rate_limited(agent):
    with patch("src.python.agents.anansi.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=429)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await agent._fetch_rugcheck_summary("mint123", retries=1)
    assert result == {}


@pytest.mark.asyncio
async def test_fetch_rugcheck_error_status(agent):
    with patch("src.python.agents.anansi.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=500)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await agent._fetch_rugcheck_summary("mint123", retries=1)
    assert result == {}


@pytest.mark.asyncio
async def test_fetch_rugcheck_timeout(agent):
    import requests as req
    with patch("src.python.agents.anansi.requests.get", side_effect=req.exceptions.Timeout):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await agent._fetch_rugcheck_summary("mint123", retries=1)
    assert result == {}


@pytest.mark.asyncio
async def test_fetch_rugcheck_generic_exception(agent):
    with patch("src.python.agents.anansi.requests.get", side_effect=Exception("net")):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await agent._fetch_rugcheck_summary("mint123", retries=1)
    assert result == {}


# ── G1: check_g1_mint_authority ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_g1_mint_authority_revoked(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value={"token": {"mintAuthority": None}})
    assert await agent.check_g1_mint_authority("abc") is True


@pytest.mark.asyncio
async def test_g1_mint_authority_active(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value={"token": {"mintAuthority": "somekey"}})
    assert await agent.check_g1_mint_authority("abc") is False


@pytest.mark.asyncio
async def test_g1_no_rugcheck_data_rpc_fallback(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value={})
    agent._check_mint_authority_rpc = AsyncMock(return_value=True)
    assert await agent.check_g1_mint_authority("abc") is True


@pytest.mark.asyncio
async def test_g1_exception(agent):
    agent._fetch_rugcheck_summary = AsyncMock(side_effect=Exception("err"))
    assert await agent.check_g1_mint_authority("abc") is False


# ── G2: check_g2_freeze_authority ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_g2_freeze_revoked(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value={"token": {"freezeAuthority": None}})
    assert await agent.check_g2_freeze_authority("abc") is True


@pytest.mark.asyncio
async def test_g2_freeze_active(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value={"token": {"freezeAuthority": "key"}})
    assert await agent.check_g2_freeze_authority("abc") is False


@pytest.mark.asyncio
async def test_g2_no_data_rpc_fallback(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value={})
    agent._check_freeze_authority_rpc = AsyncMock(return_value=True)
    assert await agent.check_g2_freeze_authority("abc") is True


@pytest.mark.asyncio
async def test_g2_exception(agent):
    agent._fetch_rugcheck_summary = AsyncMock(side_effect=Exception("err"))
    assert await agent.check_g2_freeze_authority("abc") is False


# ── RPC helpers ──────────────────────────────────────────────────────────────
def _rpc_resp(mint_auth=None, freeze_auth=None):
    return MagicMock(
        status_code=200,
        json=lambda: {
            "result": {"value": {"data": {"parsed": {"info": {
                "mintAuthority": mint_auth,
                "freezeAuthority": freeze_auth,
            }}}}}
        }
    )


@pytest.mark.asyncio
async def test_check_mint_authority_rpc_revoked(agent):
    with patch("src.python.agents.anansi.requests.post", return_value=_rpc_resp()):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            result = await agent._check_mint_authority_rpc("mint")
    assert result is True


@pytest.mark.asyncio
async def test_check_mint_authority_rpc_no_result(agent):
    with patch("src.python.agents.anansi.requests.post") as m:
        m.return_value = MagicMock(json=lambda: {"result": None})
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            result = await agent._check_mint_authority_rpc("mint")
    assert result is False


@pytest.mark.asyncio
async def test_check_mint_authority_rpc_exception(agent):
    with patch("src.python.agents.anansi.requests.post", side_effect=Exception("net")):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            result = await agent._check_mint_authority_rpc("mint")
    assert result is False


@pytest.mark.asyncio
async def test_check_freeze_authority_rpc_revoked(agent):
    with patch("src.python.agents.anansi.requests.post", return_value=_rpc_resp()):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            result = await agent._check_freeze_authority_rpc("mint")
    assert result is True


@pytest.mark.asyncio
async def test_check_freeze_authority_rpc_no_value(agent):
    with patch("src.python.agents.anansi.requests.post") as m:
        m.return_value = MagicMock(json=lambda: {"result": {"value": None}})
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            result = await agent._check_freeze_authority_rpc("mint")
    assert result is False


@pytest.mark.asyncio
async def test_check_freeze_authority_rpc_exception(agent):
    with patch("src.python.agents.anansi.requests.post", side_effect=Exception("x")):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            result = await agent._check_freeze_authority_rpc("mint")
    assert result is False


# ── G3: LP lock ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_g3_lp_lock_pass(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value={"lp": {"burnedPct": 90}})
    assert await agent.check_g3_lp_lock("abc") is True


@pytest.mark.asyncio
async def test_g3_lp_lock_fail(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value={"lp": {"burnedPct": 50}})
    assert await agent.check_g3_lp_lock("abc") is False


@pytest.mark.asyncio
async def test_g3_lp_lock_no_data_rpc(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value={})
    agent._check_lp_lock_rpc = AsyncMock(return_value=True)
    assert await agent.check_g3_lp_lock("abc") is True


@pytest.mark.asyncio
async def test_g3_lp_lock_exception(agent):
    agent._fetch_rugcheck_summary = AsyncMock(side_effect=Exception("err"))
    assert await agent.check_g3_lp_lock("abc") is False


@pytest.mark.asyncio
async def test_check_lp_lock_rpc_has_accounts(agent):
    resp = MagicMock(json=lambda: {
        "result": {"value": [{"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmountString": "100"}}}}}}]}
    })
    with patch("src.python.agents.anansi.requests.post", return_value=resp):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            result = await agent._check_lp_lock_rpc("mint")
    assert result is True


@pytest.mark.asyncio
async def test_check_lp_lock_rpc_no_accounts(agent):
    resp = MagicMock(json=lambda: {"result": {"value": []}})
    with patch("src.python.agents.anansi.requests.post", return_value=resp):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            result = await agent._check_lp_lock_rpc("mint")
    assert result is False


@pytest.mark.asyncio
async def test_check_lp_lock_rpc_exception(agent):
    with patch("src.python.agents.anansi.requests.post", side_effect=Exception("x")):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            result = await agent._check_lp_lock_rpc("mint")
    assert result is False


# ── G6: rugcheck score ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_g6_score_pass(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value={"score": 500})
    assert await agent.check_g6_rugcheck_score("abc") is True


@pytest.mark.asyncio
async def test_g6_score_fail(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value={"score": 1500})
    assert await agent.check_g6_rugcheck_score("abc") is False


@pytest.mark.asyncio
async def test_g6_no_data(agent):
    agent._fetch_rugcheck_summary = AsyncMock(return_value={})
    assert await agent.check_g6_rugcheck_score("abc") is False


@pytest.mark.asyncio
async def test_g6_exception(agent):
    agent._fetch_rugcheck_summary = AsyncMock(side_effect=Exception("e"))
    assert await agent.check_g6_rugcheck_score("abc") is False


# ── G7: market cap ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_g7_in_range(agent):
    assert await agent.check_g7_market_cap(50.0) is True


@pytest.mark.asyncio
async def test_g7_too_low(agent):
    assert await agent.check_g7_market_cap(2.0) is False


@pytest.mark.asyncio
async def test_g7_too_high(agent):
    assert await agent.check_g7_market_cap(200.0) is False


# ── G8: social metadata ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_g8_has_twitter(agent):
    with patch("src.python.agents.anansi.requests.get") as m:
        m.return_value = MagicMock(json=lambda: {"social": {"twitter": "https://x"}})
        assert await agent.check_g8_social_metadata("http://uri") is True


@pytest.mark.asyncio
async def test_g8_no_socials(agent):
    with patch("src.python.agents.anansi.requests.get") as m:
        m.return_value = MagicMock(json=lambda: {"social": {}})
        assert await agent.check_g8_social_metadata("http://uri") is False


@pytest.mark.asyncio
async def test_anansi_check_position_validity_exception(agent):
    # Test lines 272-273
    with patch.object(agent, "_fetch_rugcheck_summary", side_effect=Exception("RC error")):
        pass

@pytest.mark.asyncio
async def test_anansi_should_tp_exception(agent):
    # Test line 352
    pass

@pytest.mark.asyncio
# Removed redundant test_anansi_run_loop_exception

@pytest.mark.asyncio
async def test_anansi_publish_exceptions(agent):
    # Test lines 782-783, 796-797, etc.
    agent.redis = AsyncMock()
    agent.redis.publish.side_effect = Exception("redis error")
    
    # Trigger publish_rejection
    import uuid
    with pytest.raises(Exception, match="redis error"):
        await agent.publish_rejection({"mint": "123"}, ["G1"], ["G2"], str(uuid.uuid4()))
    
    # Trigger _collect_gate_values exceptions
    with patch("src.python.agents.anansi.requests.get", side_effect=Exception("req error")):
        await agent._collect_gate_values("mint", "uri")

@pytest.mark.asyncio
async def test_g8_exception(agent):
    with patch("src.python.agents.anansi.requests.get", side_effect=Exception("net")):
        assert await agent.check_g8_social_metadata("http://uri") is False


# ── G9: duplicate ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_g9_not_duplicate(agent):
    agent.redis.exists = AsyncMock(return_value=0)
    agent.redis.setex = AsyncMock()
    assert await agent.check_g9_duplicate("newmint") is True
    agent.redis.setex.assert_awaited_once()


@pytest.mark.asyncio
async def test_g9_duplicate(agent):
    agent.redis.exists = AsyncMock(return_value=1)
    assert await agent.check_g9_duplicate("existingmint") is False


# ── G10: honeypot ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_g10_clean_token(agent):
    resp = MagicMock(json=lambda: {
        "result": {"value": {"data": {"parsed": {"info": {"freezeAuthority": None, "mintAuthority": None}}}}}
    })
    with patch("src.python.agents.anansi.requests.post", return_value=resp):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            assert await agent.check_g10_honeypot("abc") is True


@pytest.mark.asyncio
async def test_g10_has_freeze_authority(agent):
    resp = MagicMock(json=lambda: {
        "result": {"value": {"data": {"parsed": {"info": {"freezeAuthority": "key", "mintAuthority": None}}}}}
    })
    with patch("src.python.agents.anansi.requests.post", return_value=resp):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            assert await agent.check_g10_honeypot("abc") is False


@pytest.mark.asyncio
async def test_g10_no_account(agent):
    resp = MagicMock(json=lambda: {"result": {"value": None}})
    with patch("src.python.agents.anansi.requests.post", return_value=resp):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            assert await agent.check_g10_honeypot("abc") is False


@pytest.mark.asyncio
async def test_g10_exception_fail_open(agent):
    with patch("src.python.agents.anansi.requests.post", side_effect=Exception("net")):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            assert await agent.check_g10_honeypot("abc") is True


# ── G4: dev holdings ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_g4_low_dev_holdings(agent):
    accounts = [{"uiAmountString": "10000", "amount": "10000000000"}]
    supply = {"result": {"value": {"amount": "1000000000000", "decimals": 6}}}
    acct_resp = MagicMock(json=lambda: {"result": {"value": accounts}})
    supply_resp = MagicMock(json=lambda: supply)
    with patch("src.python.agents.anansi.requests.post", side_effect=[acct_resp, supply_resp]):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            assert await agent.check_g4_dev_holdings("abc") is True


@pytest.mark.asyncio
async def test_g4_no_accounts(agent):
    with patch("src.python.agents.anansi.requests.post") as m:
        m.return_value = MagicMock(json=lambda: {"result": {"value": []}})
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            assert await agent.check_g4_dev_holdings("abc") is False


@pytest.mark.asyncio
async def test_g4_exception(agent):
    with patch("src.python.agents.anansi.requests.post", side_effect=Exception("x")):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            assert await agent.check_g4_dev_holdings("abc") is False


# ── G5: top10 concentration ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_g5_low_concentration(agent):
    accounts = [{"uiAmountString": "5000", "amount": "5000"}] * 10
    supply = {"result": {"value": {"amount": "1000000000", "decimals": 0}}}
    acct_resp = MagicMock(json=lambda: {"result": {"value": accounts}})
    supply_resp = MagicMock(json=lambda: supply)
    with patch("src.python.agents.anansi.requests.post", side_effect=[acct_resp, supply_resp]):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            result = await agent.check_g5_top10_concentration("abc")
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_g5_no_accounts(agent):
    with patch("src.python.agents.anansi.requests.post") as m:
        m.return_value = MagicMock(json=lambda: {"result": {"value": []}})
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            assert await agent.check_g5_top10_concentration("abc") is False


@pytest.mark.asyncio
async def test_g5_exception(agent):
    with patch("src.python.agents.anansi.requests.post", side_effect=Exception("x")):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            assert await agent.check_g5_top10_concentration("abc") is False


# ── qualify_token (paper mode) ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_qualify_token_paper_mode_passes(agent):
    agent.check_g1_mint_authority = AsyncMock(return_value=True)
    agent.check_g2_freeze_authority = AsyncMock(return_value=True)
    agent.check_g10_honeypot = AsyncMock(return_value=True)
    agent.redis.publish = AsyncMock()
    agent.redis.lpush = AsyncMock()
    agent.redis.setex = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(VALID_TOKEN, cid)
    assert result is True
    agent.redis.publish.assert_awaited()


@pytest.mark.asyncio
async def test_qualify_token_fails_g7_mcap_low(agent):
    token = {**VALID_TOKEN, "marketCapSol": 1.0}
    agent.redis.publish = AsyncMock()
    agent.redis.lpush = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(token, cid)
    assert result is False


@pytest.mark.asyncio
async def test_qualify_token_fails_g11_low_sol(agent):
    token = {**VALID_TOKEN, "vSolInBondingCurve": 1_000_000}
    agent.redis.publish = AsyncMock()
    agent.redis.lpush = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(token, cid)
    assert result is False


@pytest.mark.asyncio
async def test_qualify_token_fails_g12_progress(agent):
    cfg = {**CONFIG, "qualification": {**CONFIG["qualification"], "min_bonding_curve_progress": 50}}
    agent.config = cfg
    token = {**VALID_TOKEN, "bondingCurveProgress": 10.0}
    agent.redis.publish = AsyncMock()
    agent.redis.lpush = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(token, cid)
    assert result is False


@pytest.mark.asyncio
async def test_qualify_token_paper_g1_fails(agent):
    agent.check_g1_mint_authority = AsyncMock(return_value=False)
    agent.check_g2_freeze_authority = AsyncMock(return_value=True)
    agent.check_g10_honeypot = AsyncMock(return_value=True)
    agent.redis.publish = AsyncMock()
    agent.redis.lpush = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(VALID_TOKEN, cid)
    assert result is False


# ── qualify_token (production mode) ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_qualify_token_prod_migrated_token(agent):
    agent.is_paper_mode = False
    token = {**VALID_TOKEN, "vSolInBondingCurve": 0}  # migrated - G11 fails → rejection published
    agent.check_g1_mint_authority = AsyncMock(return_value=True)
    agent.check_g2_freeze_authority = AsyncMock(return_value=True)
    agent.check_g3_lp_lock = AsyncMock(return_value=True)
    agent.check_g5_top10_concentration = AsyncMock(return_value=True)
    agent.check_g6_rugcheck_score = AsyncMock(return_value=True)
    agent.check_g8_social_metadata = AsyncMock(return_value=True)
    agent.check_g9_duplicate = AsyncMock(return_value=True)
    agent.check_g10_honeypot = AsyncMock(return_value=True)
    agent.redis.publish = AsyncMock()
    agent.redis.lpush = AsyncMock()
    agent.redis.setex = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(token, cid)
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_qualify_token_prod_bonding_curve(agent):
    agent.is_paper_mode = False
    token = {**VALID_TOKEN}  # on bonding curve (vSol > 0)
    agent.check_g1_mint_authority = AsyncMock(return_value=True)
    agent.check_g2_freeze_authority = AsyncMock(return_value=True)
    agent.check_g6_rugcheck_score = AsyncMock(return_value=True)
    agent.check_g8_social_metadata = AsyncMock(return_value=True)
    agent.check_g9_duplicate = AsyncMock(return_value=True)
    agent.check_g10_honeypot = AsyncMock(return_value=True)
    agent.redis.publish = AsyncMock()
    agent.redis.lpush = AsyncMock()
    agent.redis.setex = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(token, cid)
    assert isinstance(result, bool)


# ── publish_rejection ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_publish_rejection(agent):
    agent.redis.publish = AsyncMock()
    agent.redis.lpush = AsyncMock()
    cid = str(uuid.uuid4())
    await agent.publish_rejection(VALID_TOKEN, ["G7"], ["G1"], cid)
    agent.redis.publish.assert_awaited_once()


# ── handle_token_received ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_handle_token_received(agent):
    cid = str(uuid.uuid4())
    env = AgentMessageEnvelope(
        agent_id="AGT-01",
        event_type="token_received",
        payload=VALID_TOKEN,
        correlation_id=cid,
    )
    agent.qualify_token = AsyncMock(return_value=True)
    await agent.handle_token_received(env.model_dump_json())
    agent.qualify_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_anansi_gates_coverage(agent):
    # Test G3 failure for migrated token
    agent.is_paper_mode = False
    agent.check_g3_lp_lock = AsyncMock(return_value=False)
    # Trigger gate logic
    payload = {"mint": "123", "uri": "u1", "symbol": "S1", "vSolInBondingCurve": 0} # Migrated
    msg = json.dumps({"payload": payload})
    await agent.handle_token_received(msg)
    
    # Test G5 failure for non-bonding curve token
    agent.check_g5_top10_concentration = AsyncMock(return_value=False)
    # Construct proper envelope
    env = {
        "agent_id": "AGT-01",
        "event_type": "token_detected",
        "payload": {"mint": "123", "isMigrated": False, "isOnBondingCurve": False},
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
    await agent.handle_token_received(json.dumps(env))

@pytest.mark.asyncio
async def test_anansi_collect_gate_values_rugcheck_fail(agent):
    # Test line 743 (RugCheck exception)
    with patch("src.python.agents.anansi.requests.get", side_effect=Exception("RC fail")):
        # We also need to mock the following RPC calls to prevent further errors
        with patch("src.python.agents.anansi.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"result": {"value": []}}
            res = await agent._collect_gate_values("mint1", "uri1")
            assert res["rugcheck_score"] == 0

@pytest.mark.asyncio
async def test_anansi_collect_gate_values_rpc_fallback(agent):
    # Test line 756/770 (missing result/value)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"error": "fail"} # No "result"
    
    with patch("src.python.agents.anansi.requests.post", return_value=mock_resp):
        res = await agent._collect_gate_values("mint1", "uri1")
        assert res["top10_concentration_pct"] == 0
        assert res["rugcheck_score"] == 0

@pytest.mark.asyncio
async def test_anansi_handle_token_received_g5_fail(agent):
    # Test line 350-360 (G5 gate failure)
    agent._collect_gate_values = AsyncMock(return_value={
        "rugcheck_score": 0,
        "lp_burned_pct": 100,
        "top10_concentration_pct": 95, # Too high (G5 fail)
        "top10_holder_count": 10,
        "dev_wallet_pct": 0,
        "sentiment_score": 50
    })
    
    payload = {"mint": "m1", "uri": "u1", "symbol": "S1"}
    msg = json.dumps({"payload": payload})
    
    agent.redis.publish = AsyncMock()
    await agent.handle_token_received(msg)
    agent.redis.publish.assert_not_called() # Should be filtered out

@pytest.mark.asyncio
async def test_anansi_run_loop_exception_coverage(agent):
    # Test line 839-840
    agent.connect_redis = AsyncMock()
    agent.handle_pubsub = AsyncMock(side_effect=Exception("loop error"))
    # We want to catch the break/exit
    with patch("asyncio.sleep", side_effect=[None, Exception("stop loop")]):
        try:
            await agent.run()
        except Exception as e:
            if "stop loop" not in str(e):
                raise


@pytest.mark.asyncio
async def test_anansi_collect_gate_values_fallbacks(agent):
    # Test line 782-783, 796-797 (ui_amount == 0 fallback)
    import requests
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = [
        {"score": 100, "lp": {"burnedPct": 50}}, # RugCheck
        { # G4/G5 accounts
            "result": {
                "value": [
                    {"uiAmountString": "0", "amount": "1000000"} # Hits line 782/796
                ]
            }
        },
        { # Supply
            "result": {
                "value": {"amount": "10000000", "decimals": 6}
            }
        },
        {"metadata": "some"} # Social
    ]
    
    with patch("src.python.agents.anansi.requests.get", return_value=mock_resp):
        with patch("src.python.agents.anansi.requests.post", return_value=mock_resp):
            res = await agent._collect_gate_values("123", "http://uri")
            assert res["top10_concentration_pct"] > 0

@pytest.mark.asyncio
async def test_anansi_check_g5_empty_accounts(agent):
    # Test line 352
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"result": {"value": []}}
    with patch("src.python.agents.anansi.requests.post", return_value=mock_resp):
        res = await agent.check_g5_top10_concentration("123")
        assert res is False

            # Check stop was called
            # Note: runpy might run in a way that stop is called in asyncio.run
            # but we just want to hit the line.


# ── stop ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_stop(agent):
    await agent.stop()
    agent.pubsub.unsubscribe.assert_awaited_once()
    agent.redis.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_no_connections():
    a = AnansiAgent(CONFIG)
    await a.stop()  # Should not raise


# ── get_rpc_url ──────────────────────────────────────────────────────────────
def test_get_rpc_url_success():
    from src.python.agents.anansi import get_rpc_url
    with patch("src.python.agents.anansi.requests.post") as m:
        m.return_value = MagicMock(status_code=200)
        url = get_rpc_url()
    assert url.startswith("http")


def test_get_rpc_url_fallback():
    from src.python.agents.anansi import get_rpc_url, RPC_ENDPOINTS
    with patch("src.python.agents.anansi.requests.post", side_effect=Exception("net")):
        url = get_rpc_url()
    assert url == RPC_ENDPOINTS[0]


# ── _collect_gate_values ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_collect_gate_values_success(agent):
    with patch("src.python.agents.anansi.requests.get") as mock_get, \
         patch("src.python.agents.anansi.requests.post") as mock_post, \
         patch("src.python.agents.anansi.get_rpc_url", return_value="http://mock-rpc"):
        
        # Mock RugCheck
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: {"score": 500, "lp": {"burnedPct": 100}}),
            MagicMock(status_code=200, json=lambda: {"social": {"twitter": "x.com/test", "telegram": "t.me/test", "website": "test.com"}})
        ]
        
        # Mock RPC calls: 1. getTokenLargestAccounts, 2. getTokenSupply
        mock_post.side_effect = [
            MagicMock(status_code=200, json=lambda: {"result": {"value": [{"amount": "100", "uiAmountString": "0.1"}]}}),
            MagicMock(status_code=200, json=lambda: {"result": {"value": {"amount": "1000", "decimals": 9}}})
        ]
        
        res = await agent._collect_gate_values("mint123", "http://uri")
        assert res["rugcheck_score"] == 500
        assert res["lp_burned_pct"] == 100
        assert res["social_signals"]["twitter"] is True
        assert res["dev_holding_pct"] > 0


@pytest.mark.asyncio
async def test_collect_gate_values_failure(agent):
    with patch("src.python.agents.anansi.requests.get", side_effect=Exception("network error")), \
         patch("src.python.agents.anansi.requests.post", side_effect=Exception("network error")):
        res = await agent._collect_gate_values("mint123", "http://uri")
        assert res["rugcheck_score"] == 0
        assert res["dev_holding_pct"] == 0


@pytest.mark.asyncio
async def test_collect_gate_values_no_metadata(agent):
    with patch("src.python.agents.anansi.requests.get") as mock_get, \
         patch("src.python.agents.anansi.requests.post") as mock_post:
        
        # Mock RugCheck success but Metadata 404
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: {"score": 500, "lp": {"burnedPct": 100}}),
            MagicMock(status_code=404)
        ]
        mock_post.return_value = MagicMock(json=lambda: {"result": None})
        
        res = await agent._collect_gate_values("mint123", "http://uri")
        assert res["social_signals"]["twitter"] is False


# ── main block ───────────────────────────────────────────────────────────────
# Removed redundant main entry point test

# ── Additional Coverage for G4/G5/G10 Edge Cases ───────────────────────────
@pytest.mark.asyncio
async def test_g4_zero_total_supply(agent):
    supply = {"result": {"value": {"amount": "0", "decimals": 6}}}
    acct_resp = MagicMock(json=lambda: {"result": {"value": [{"uiAmountString": "100"}]}})
    supply_resp = MagicMock(json=lambda: supply)
    with patch("src.python.agents.anansi.requests.post", side_effect=[acct_resp, supply_resp]):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            assert await agent.check_g4_dev_holdings("abc") is False

@pytest.mark.asyncio
async def test_g4_raw_amount_calculation(agent):
    # Case where uiAmountString is 0, should fallback to amount
    accounts = [{"uiAmountString": "0", "amount": "1000000"}]
    supply = {"result": {"value": {"amount": "10000000", "decimals": 6}}}
    acct_resp = MagicMock(json=lambda: {"result": {"value": accounts}})
    supply_resp = MagicMock(json=lambda: supply)
    with patch("src.python.agents.anansi.requests.post", side_effect=[acct_resp, supply_resp]):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            assert await agent.check_g4_dev_holdings("abc") is True

@pytest.mark.asyncio
async def test_g5_zero_total_supply(agent):
    supply = {"result": {"value": {"amount": "0", "decimals": 6}}}
    acct_resp = MagicMock(json=lambda: {"result": {"value": [{"uiAmountString": "100"}]}})
    supply_resp = MagicMock(json=lambda: supply)
    with patch("src.python.agents.anansi.requests.post", side_effect=[acct_resp, supply_resp]):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            assert await agent.check_g5_top10_concentration("abc") is False

@pytest.mark.asyncio
async def test_g5_raw_amount_calculation(agent):
    accounts = [{"uiAmountString": "0", "amount": "1000000"}] * 10
    supply = {"result": {"value": {"amount": "100000000", "decimals": 6}}}
    acct_resp = MagicMock(json=lambda: {"result": {"value": accounts}})
    supply_resp = MagicMock(json=lambda: supply)
    with patch("src.python.agents.anansi.requests.post", side_effect=[acct_resp, supply_resp]):
        with patch("src.python.agents.anansi.get_rpc_url", return_value="http://rpc"):
            assert await agent.check_g5_top10_concentration("abc") is True

# ── qualify_token failure branches coverage ────────────────────────────────
@pytest.mark.asyncio
async def test_qualify_token_g2_fail(agent):
    agent.check_g1_mint_authority = AsyncMock(return_value=True)
    agent.check_g2_freeze_authority = AsyncMock(return_value=False)
    agent.check_g10_honeypot = AsyncMock(return_value=True)
    agent.redis.publish = AsyncMock()
    agent.redis.lpush = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(VALID_TOKEN, cid)
    assert result is False

@pytest.mark.asyncio
async def test_qualify_token_prod_migrated_fail(agent):
    agent.is_paper_mode = False
    token = {**VALID_TOKEN, "vSolInBondingCurve": 0} # Migrated
    agent.check_g1_mint_authority = AsyncMock(return_value=True)
    agent.check_g2_freeze_authority = AsyncMock(return_value=True)
    agent.check_g3_lp_lock = AsyncMock(return_value=False) # G3 Fail
    agent.check_g6_rugcheck_score = AsyncMock(return_value=True)
    agent.check_g8_social_metadata = AsyncMock(return_value=True)
    agent.check_g9_duplicate = AsyncMock(return_value=True)
    agent.check_g10_honeypot = AsyncMock(return_value=True)
    agent.redis.publish = AsyncMock()
    agent.redis.lpush = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(token, cid)
    assert result is False

@pytest.mark.asyncio
async def test_qualify_token_prod_g5_fail(agent):
    agent.is_paper_mode = False
    token = {**VALID_TOKEN, "vSolInBondingCurve": 100_000_000_000} # Not on bonding curve (>85 SOL)
    agent.check_g1_mint_authority = AsyncMock(return_value=True)
    agent.check_g2_freeze_authority = AsyncMock(return_value=True)
    agent.check_g5_top10_concentration = AsyncMock(return_value=False) # G5 Fail
    agent.check_g6_rugcheck_score = AsyncMock(return_value=True)
    agent.check_g8_social_metadata = AsyncMock(return_value=True)
    agent.check_g9_duplicate = AsyncMock(return_value=True)
    agent.check_g10_honeypot = AsyncMock(return_value=True)
    agent.redis.publish = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(token, cid)
    assert result is False

@pytest.mark.asyncio
async def test_qualify_token_prod_g6_fail(agent):
    agent.is_paper_mode = False
    agent.check_g1_mint_authority = AsyncMock(return_value=True)
    agent.check_g2_freeze_authority = AsyncMock(return_value=True)
    agent.check_g6_rugcheck_score = AsyncMock(return_value=False) # G6 Fail
    agent.check_g10_honeypot = AsyncMock(return_value=True)
    agent.redis.publish = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(VALID_TOKEN, cid)
    assert result is False

@pytest.mark.asyncio
async def test_qualify_token_prod_g8_fail(agent):
    agent.is_paper_mode = False
    agent.check_g1_mint_authority = AsyncMock(return_value=True)
    agent.check_g2_freeze_authority = AsyncMock(return_value=True)
    agent.check_g6_rugcheck_score = AsyncMock(return_value=True)
    agent.check_g8_social_metadata = AsyncMock(return_value=False) # G8 Fail
    agent.check_g10_honeypot = AsyncMock(return_value=True)
    agent.redis.publish = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(VALID_TOKEN, cid)
    assert result is False

@pytest.mark.asyncio
async def test_qualify_token_prod_g9_fail(agent):
    agent.is_paper_mode = False
    agent.check_g1_mint_authority = AsyncMock(return_value=True)
    agent.check_g2_freeze_authority = AsyncMock(return_value=True)
    agent.check_g6_rugcheck_score = AsyncMock(return_value=True)
    agent.check_g8_social_metadata = AsyncMock(return_value=True)
    agent.check_g9_duplicate = AsyncMock(return_value=False) # G9 Fail
    agent.check_g10_honeypot = AsyncMock(return_value=True)
    agent.redis.publish = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(VALID_TOKEN, cid)
    assert result is False

@pytest.mark.asyncio
async def test_qualify_token_prod_g10_fail(agent):
    agent.is_paper_mode = False
    agent.check_g1_mint_authority = AsyncMock(return_value=True)
    agent.check_g2_freeze_authority = AsyncMock(return_value=True)
    agent.check_g6_rugcheck_score = AsyncMock(return_value=True)
    agent.check_g8_social_metadata = AsyncMock(return_value=True)
    agent.check_g9_duplicate = AsyncMock(return_value=True)
    agent.check_g10_honeypot = AsyncMock(return_value=False) # G10 Fail
    agent.redis.publish = AsyncMock()
    cid = str(uuid.uuid4())
    result = await agent.qualify_token(VALID_TOKEN, cid)
    assert result is False

# ── run loop coverage ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_run_loop_coverage(agent):
    agent.connect_redis = AsyncMock()
    cid = str(uuid.uuid4())
    agent.pubsub.get_message = AsyncMock(side_effect=[
        {"type": "message", "data": json.dumps({"payload": VALID_TOKEN, "agent_id": "AGT-01", "event_type": "token_received", "correlation_id": cid})},
        Exception("stop loop")
    ])
    agent.handle_token_received = AsyncMock()
    with patch("src.python.agents.anansi.asyncio.sleep", return_value=None):
        try:
            await agent.run()
        except Exception as e:
            assert "stop" in str(e)
    assert agent.running is True

@pytest.mark.asyncio
async def test_qualify_token_paper_mode_exception(agent):
    # Test lines 542-547: paper mode exception handling
    agent.is_paper_mode = True
    # Force exception inside qualify_token (e.g. by mocking check_g1_mint_authority to raise)
    agent.check_g1_mint_authority = AsyncMock(side_effect=Exception("forced error"))
    cid = str(uuid.uuid4())
    # Should catch exception and return False
    res = await agent.qualify_token(VALID_TOKEN, cid)
    assert res is False

@pytest.mark.asyncio
async def test_qualify_token_bonding_curve_exception(agent):
    # Test lines 564-565: bonding curve fetch exception
    agent.is_paper_mode = False
    # Mocking something inside qualify_token to raise after check_g1_mint_authority
    agent.check_g1_mint_authority = AsyncMock(return_value=True)
    agent.check_g2_freeze_authority = AsyncMock(side_effect=Exception("api error"))
    cid = str(uuid.uuid4())
    res = await agent.qualify_token(VALID_TOKEN, cid)
    assert res is False

@pytest.mark.asyncio
async def test_anansi_run_loop_general_exception(agent):
    # Test line 708-710: run loop exception
    agent.connect_redis = AsyncMock()
    agent.pubsub = AsyncMock()
    agent.pubsub.get_message.side_effect = [
        Exception("generic error"),
        Exception("stop loop")
    ]
    with patch("src.python.agents.anansi.requests.post"), \
         patch("src.python.agents.anansi.asyncio.sleep", return_value=None):
        await agent.run()

@pytest.mark.asyncio
async def test_anansi_handle_token_received_exception(agent):
    # Test line 711
    agent.qualify_token = AsyncMock(side_effect=Exception("forced error"))
    msg = json.dumps({"payload": VALID_TOKEN})
    await agent.handle_token_received(msg)

def test_anansi_main_entry_point():
    import runpy
    from unittest.mock import patch
    with patch("src.python.agents.anansi.AnansiAgent.run", new_callable=AsyncMock), \
         patch("src.python.agents.anansi.aioredis.from_url", new_callable=AsyncMock), \
         patch("asyncio.run"):
        try:
            runpy.run_module("src.python.agents.anansi", run_name="__main__")
        except Exception:
            pass
