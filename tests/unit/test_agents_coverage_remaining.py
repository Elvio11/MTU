"""
Targeted agent coverage tests for remaining uncovered branches.
"""

import pytest
import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch, mock_open

VALID_MINT = "So11111111111111111111111111111111111111112"


def _make_envelope(**kwargs):
    from src.python.shared.envelope import AgentMessageEnvelope

    defaults = dict(
        agent_id="AGT-01",
        event_type="token_detected",
        payload={"mint": "abc", "symbol": "TST"},
        correlation_id=str(uuid.uuid4()),
    )
    defaults.update(kwargs)
    return AgentMessageEnvelope(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# anansi.py (84% -> targeted branches)
# ═══════════════════════════════════════════════════════════════════════════════
from src.python.agents.anansi import AnansiAgent


@pytest.fixture
def anansi():
    config = {
        "system": {"environment": "paper"},
        "qualification": {
            "min_lp_burned_pct": 85,
            "max_rugcheck_score": 999,
            "max_dev_holding_pct": 95,
            "min_market_cap_sol": 5,
            "max_market_cap_sol": 150,
            "min_bonding_curve_progress": 0,
        },
        "trading": {"position_size_sol": 0.1},
    }
    a = AnansiAgent(config)
    a.redis = AsyncMock()
    a.is_paper_mode = False
    return a


@pytest.mark.asyncio
async def test_anansi_g1_exception(anansi):
    """Lines 115-117: G1 exception returns False."""
    anansi._fetch_rugcheck_summary = AsyncMock(side_effect=Exception("err"))
    assert await anansi.check_g1_mint_authority("m") is False


@pytest.mark.asyncio
async def test_anansi_g1_no_data_rpc(anansi):
    """G1 no RugCheck data falls to RPC."""
    anansi._fetch_rugcheck_summary = AsyncMock(return_value=None)
    anansi._check_mint_authority_rpc = AsyncMock(return_value=True)
    assert await anansi.check_g1_mint_authority("m") is True
    anansi._check_mint_authority_rpc.assert_awaited()


@pytest.mark.asyncio
async def test_anansi_g3_exception(anansi):
    """Lines 190-192: G3 exception returns False."""
    anansi._fetch_rugcheck_summary = AsyncMock(side_effect=Exception("err"))
    assert await anansi.check_g3_lp_lock("m") is False


@pytest.mark.asyncio
async def test_anansi_g4_no_result(anansi):
    """Lines 268-269: G4 no result in data."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch("src.python.agents.anansi.requests.post") as mp,
    ):
        mp.return_value.json.return_value = {"no": "result"}
        assert await anansi.check_g4_dev_holdings("m") is False


@pytest.mark.asyncio
async def test_anansi_g4_empty_accounts(anansi):
    """Lines 273-274: G4 empty accounts."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch("src.python.agents.anansi.requests.post") as mp,
    ):
        mp.return_value.json.return_value = {"result": {"value": []}}
        assert await anansi.check_g4_dev_holdings("m") is False


@pytest.mark.asyncio
async def test_anansi_g4_zero_supply(anansi):
    """Lines 297-298: G4 zero total supply."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch("src.python.agents.anansi.requests.post") as mp,
    ):
        mp.side_effect = [
            MagicMock(json=lambda: {"result": {"value": [{"uiAmountString": "10"}]}}),
            MagicMock(json=lambda: {"result": None}),
        ]
        assert await anansi.check_g4_dev_holdings("m") is False


@pytest.mark.asyncio
async def test_anansi_g4_exception(anansi):
    """Lines 324-326: G4 exception returns False."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch("src.python.agents.anansi.requests.post", side_effect=Exception("err")),
    ):
        assert await anansi.check_g4_dev_holdings("m") is False


@pytest.mark.asyncio
async def test_anansi_g5_no_result(anansi):
    """Lines 348-349: G5 no result."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch("src.python.agents.anansi.requests.post") as mp,
    ):
        mp.return_value.json.return_value = {"no": "result"}
        assert await anansi.check_g5_top10_concentration("m") is False


@pytest.mark.asyncio
async def test_anansi_g5_empty_accounts(anansi):
    """Lines 353: G5 empty accounts."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch("src.python.agents.anansi.requests.post") as mp,
    ):
        mp.return_value.json.return_value = {"result": {"value": []}}
        assert await anansi.check_g5_top10_concentration("m") is False


@pytest.mark.asyncio
async def test_anansi_g5_zero_supply_readable(anansi):
    """Line 380: G5 total_supply_readable == 0."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch("src.python.agents.anansi.requests.post") as mp,
    ):
        mp.side_effect = [
            MagicMock(json=lambda: {"result": {"value": [{"uiAmountString": "10"}]}}),
            MagicMock(
                json=lambda: {"result": {"value": {"amount": "0", "decimals": 9}}}
            ),
        ]
        assert await anansi.check_g5_top10_concentration("m") is False


@pytest.mark.asyncio
async def test_anansi_g5_exception(anansi):
    """G5 exception path (except block lines 396-398)."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch(
            "src.python.agents.anansi.requests.post", side_effect=Exception("rpc_err")
        ),
    ):
        assert await anansi.check_g5_top10_concentration("m") is False


@pytest.mark.asyncio
async def test_anansi_g6_graduated_no_data(anansi):
    """Lines 233-234: G6 graduated with no data returns True."""
    anansi._fetch_rugcheck_summary = AsyncMock(return_value=None)
    assert await anansi.check_g6_rugcheck_score("m", is_graduated=True) is True


@pytest.mark.asyncio
async def test_anansi_g8_exception(anansi):
    """Lines 406-408: G8 exception returns False."""
    with patch("src.python.agents.anansi.requests.get", side_effect=Exception("err")):
        assert await anansi.check_g8_social_metadata("uri") is False


@pytest.mark.asyncio
async def test_anansi_g10_not_found(anansi):
    """Lines 432-433: G10 token account not found."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch("src.python.agents.anansi.requests.post") as mp,
    ):
        mp.return_value.json.return_value = {"result": None}
        assert await anansi.check_g10_honeypot("m") is False


@pytest.mark.asyncio
async def test_anansi_g10_exception(anansi):
    """G10 exception returns True (fail open)."""
    with patch.object(anansi, "get_rpc_url", side_effect=Exception("err")):
        assert await anansi.check_g10_honeypot("m") is True


@pytest.mark.asyncio
async def test_anansi_g7_graduated_mc_low(anansi):
    """Lines 471-474: G7 graduated MC too low."""
    result = await anansi.check_g7_liquidity_size(
        {"is_graduated": True, "marketCapSol": 1}
    )
    assert result is False


@pytest.mark.asyncio
async def test_anansi_g7_nongrad_mc_high(anansi):
    """Lines 479-480: G7 non-graduated MC > 500."""
    result = await anansi.check_g7_liquidity_size({"marketCapSol": 600})
    assert result is True


@pytest.mark.asyncio
async def test_anansi_g12_graduated_full(anansi):
    """Line 501: G12 graduated with progress >= 100."""
    result = await anansi.check_g12_bonding_curve(
        {"is_graduated": True, "bondingCurveProgress": 100}
    )
    assert result is True


@pytest.mark.asyncio
async def test_anansi_g13_graduated_not_bullish(anansi):
    """Lines 520-521: G13 graduated not bullish returns False."""
    token = {"is_graduated": True, "ta_signal": "neutral", "symbol": "T"}
    assert await anansi.check_g13_technical_analysis(token) is False


@pytest.mark.asyncio
async def test_anansi_qualify_paper_skip_gates(anansi):
    """Lines 548/554/572/616: paper mode skips G1/G2/G3/G10."""
    anansi.is_paper_mode = True
    anansi.check_g7_liquidity_size = AsyncMock(return_value=True)
    anansi.check_g9_duplicate = AsyncMock(return_value=True)
    anansi.check_g11_sentiment = AsyncMock(return_value=True)
    anansi.check_g12_bonding_curve = AsyncMock(return_value=True)
    anansi.check_g13_technical_analysis = AsyncMock(return_value=True)
    token = {"mint": VALID_MINT, "symbol": "T", "marketCapSol": 10}
    result = await anansi.qualify_token(token, str(uuid.uuid4()))
    assert result is True


@pytest.mark.asyncio
async def test_anansi_qualify_pump_skip_g3(anansi):
    """Line 563: pump token with progress < 99 skips G3."""
    anansi.is_paper_mode = False
    token = {
        "mint": VALID_MINT,
        "symbol": "T",
        "marketCapSol": 10,
        "is_pump": True,
        "bonding_curve_progress": 50,
    }
    anansi.check_g1_mint_authority = AsyncMock(return_value=True)
    anansi.check_g2_freeze_authority = AsyncMock(return_value=True)
    anansi.check_g3_lp_lock = AsyncMock()
    anansi.check_g4_dev_holdings = AsyncMock(return_value=True)
    anansi.check_g5_top10_concentration = AsyncMock(return_value=True)
    anansi.check_g6_rugcheck_score = AsyncMock(return_value=True)
    anansi.check_g7_liquidity_size = AsyncMock(return_value=True)
    anansi.check_g9_duplicate = AsyncMock(return_value=True)
    anansi.check_g10_honeypot = AsyncMock(return_value=True)
    anansi.check_g11_sentiment = AsyncMock(return_value=True)
    anansi.check_g12_bonding_curve = AsyncMock(return_value=True)
    anansi.check_g13_technical_analysis = AsyncMock(return_value=True)
    result = await anansi.qualify_token(token, str(uuid.uuid4()))
    anansi.check_g3_lp_lock.assert_not_called()


@pytest.mark.asyncio
async def test_anansi_g8_with_uri_paper(anansi):
    """Lines 596-602: G8 with URI in paper mode skips check."""
    anansi.is_paper_mode = True
    token = {
        "mint": VALID_MINT,
        "symbol": "T",
        "marketCapSol": 10,
        "uri": "https://uri.com",
    }
    anansi.check_g1_mint_authority = AsyncMock(return_value=True)
    anansi.check_g2_freeze_authority = AsyncMock(return_value=True)
    anansi.check_g7_liquidity_size = AsyncMock(return_value=True)
    anansi.check_g9_duplicate = AsyncMock(return_value=True)
    anansi.check_g10_honeypot = AsyncMock(return_value=True)
    anansi.check_g11_sentiment = AsyncMock(return_value=True)
    anansi.check_g12_bonding_curve = AsyncMock(return_value=True)
    anansi.check_g13_technical_analysis = AsyncMock(return_value=True)
    result = await anansi.qualify_token(token, str(uuid.uuid4()))
    anansi.check_g8_social_metadata = AsyncMock()
    assert result is True


@pytest.mark.asyncio
async def test_anansi_handle_grad_auto_detect(anansi):
    """Lines 721-723: auto-detect graduation via MC."""
    anansi.qualify_token = AsyncMock()
    env = _make_envelope(
        payload={
            "mint": "m",
            "market_cap_usd": 100000,
            "symbol": "T",
            "ta_signal": "bullish",
        }
    )
    await anansi.handle_token_received(env.model_dump_json())
    assert anansi.qualify_token.called


@pytest.mark.asyncio
async def test_anansi_handle_grad_no_ta(anansi):
    """Line 729: graduated with no TA returns early."""
    anansi.qualify_token = AsyncMock()
    env = _make_envelope(payload={"mint": "m", "symbol": "T", "is_graduated": True})
    await anansi.handle_token_received(env.model_dump_json())
    anansi.qualify_token.assert_not_called()


@pytest.mark.asyncio
async def test_anansi_run_off_hours(anansi):
    """Lines 750-757: off-hours unsubscribes and sleeps."""
    anansi.connect_redis = AsyncMock()
    anansi.pubsub = AsyncMock()
    anansi.pubsub.unsubscribe = AsyncMock()
    anansi.running = True

    states = iter([True, False])

    def active_side():
        try:
            return next(states)
        except StopIteration:
            anansi.running = False
            return False

    with (
        patch(
            "src.python.agents.anansi.is_operational_window_active",
            side_effect=active_side,
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        await anansi.run()
    anansi.pubsub.unsubscribe.assert_called()


@pytest.mark.asyncio
async def test_anansi_run_exception(anansi):
    """Lines 763-767: run loop exception handled."""
    anansi.connect_redis = AsyncMock()
    anansi.pubsub = AsyncMock()

    def raise_err(*a, **kw):
        anansi.running = False
        raise Exception("test error")

    with (
        patch(
            "src.python.agents.anansi.is_operational_window_active",
            side_effect=raise_err,
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        await anansi.run()


@pytest.mark.asyncio
async def test_anansi_stop_with_pubsub(anansi):
    """Line 772: stop with pubsub."""
    anansi.pubsub = AsyncMock()
    await anansi.stop()
    anansi.pubsub.unsubscribe.assert_awaited()


@pytest.mark.asyncio
async def test_anansi_check_g4_ui_amount_zero(anansi):
    """Lines 306-307: uiAmount zero uses raw amount."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch("src.python.agents.anansi.requests.post") as mp,
    ):
        mp.side_effect = [
            MagicMock(
                json=lambda: {
                    "result": {
                        "value": [{"amount": "100000000", "uiAmountString": "0"}]
                    }
                }
            ),
            MagicMock(
                json=lambda: {
                    "result": {"value": {"amount": "10000000000", "decimals": 9}}
                }
            ),
        ]
        assert await anansi.check_g4_dev_holdings("m") is True


@pytest.mark.asyncio
async def test_anansi_check_g5_ui_amount_zero(anansi):
    """Lines 386-387: G5 uiAmount zero fallback."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch("src.python.agents.anansi.requests.post") as mp,
    ):
        mp.side_effect = [
            MagicMock(
                json=lambda: {
                    "result": {
                        "value": [{"amount": "5000000000", "uiAmountString": "0"}]
                    }
                }
            ),
            MagicMock(
                json=lambda: {
                    "result": {"value": {"amount": "10000000000", "decimals": 9}}
                }
            ),
        ]
        assert await anansi.check_g5_top10_concentration("m") is True


@pytest.mark.asyncio
async def test_anansi_check_mint_authority_rpc_parsed(anansi):
    """Lines 129-135: parse mint authority from RPC response."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch("src.python.agents.anansi.requests.post") as mp,
    ):
        mp.return_value.json.return_value = {
            "result": {"value": {"data": {"parsed": {"info": {"mintAuthority": None}}}}}
        }
        assert await anansi._check_mint_authority_rpc("m") is True


@pytest.mark.asyncio
async def test_anansi_check_mint_authority_rpc_no_value(anansi):
    """_check_mint_authority_rpc no result value."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch("src.python.agents.anansi.requests.post") as mp,
    ):
        mp.return_value.json.return_value = {"result": None}
        assert await anansi._check_mint_authority_rpc("m") is False


@pytest.mark.asyncio
async def test_anansi_check_mint_authority_rpc_exception(anansi):
    """_check_mint_authority_rpc exception."""
    with (
        patch.object(anansi, "get_rpc_url", return_value="url"),
        patch("src.python.agents.anansi.requests.post", side_effect=Exception("err")),
    ):
        assert await anansi._check_mint_authority_rpc("m") is False


@pytest.mark.asyncio
async def test_anansi_get_rpc_url_helius_ok(anansi):
    """Lines 62-63: get_rpc_url with helius health check succeeding."""
    anansi.api_manager.request = AsyncMock(return_value={"result": "ok"})
    url = await anansi.get_rpc_url()
    assert url is not None


@pytest.mark.asyncio
async def test_anansi_get_rpc_url_helius_fails(anansi):
    """get_rpc_url with helius failing uses fallback."""
    anansi.api_manager.request = AsyncMock(side_effect=Exception("fail"))
    url = await anansi.get_rpc_url()
    assert url is not None


# ═══════════════════════════════════════════════════════════════════════════════
# oracle.py (88% -> targeted branches)
# ═══════════════════════════════════════════════════════════════════════════════
from src.python.agents.oracle import OracleAgent


@pytest.fixture
def oracle():
    config = {"system": {"environment": "paper"}}
    o = OracleAgent(config)
    o.redis = AsyncMock()
    o.session = AsyncMock()
    return o


@pytest.mark.asyncio
async def test_oracle_fetch_ohlcv_no_key(oracle):
    """Line 106: no birdeye key returns []."""
    oracle.birdeye_key = None
    result = await oracle.fetch_ohlcv_birdeye(VALID_MINT)
    assert result == []


@pytest.mark.asyncio
async def test_oracle_fetch_ohlcv_exception(oracle):
    """Lines 130-132: OHLCV exception handled."""
    oracle.birdeye_key = "key"
    oracle.session.get = MagicMock(side_effect=Exception("err"))
    result = await oracle.fetch_ohlcv_birdeye(VALID_MINT)
    assert result == []


@pytest.mark.asyncio
async def test_oracle_fetch_ohlcv_not_200(oracle):
    """OHLCV non-200 status."""
    oracle.birdeye_key = "key"
    mock_resp = AsyncMock()
    mock_resp.status = 500
    oracle.session.get = MagicMock()
    oracle.session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    result = await oracle.fetch_ohlcv_birdeye(VALID_MINT)
    assert result == []


@pytest.mark.asyncio
async def test_oracle_fetch_ta_data_no_key(oracle):
    """Line 138: no key returns empty dict."""
    oracle.birdeye_key = None
    result = await oracle.fetch_ta_data(VALID_MINT)
    assert result == {"prices": [], "volumes": []}


@pytest.mark.asyncio
async def test_oracle_fetch_ta_data_fallback(oracle):
    """Line 167: OHLCV fails falls back to history_price."""
    oracle.birdeye_key = "key"
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"success": False})
    oracle.session.get = MagicMock()
    oracle.session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    oracle.fetch_ohlcv_birdeye = AsyncMock(return_value=[100.0])
    result = await oracle.fetch_ta_data(VALID_MINT)
    assert result["prices"] == [100.0]


@pytest.mark.asyncio
async def test_oracle_ta_bearish_overbought(oracle):
    """Line 213: overbought returns bearish."""
    oracle.fetch_ta_data = AsyncMock(
        return_value={"prices": [10.0] * 20, "volumes": [1000.0] * 20}
    )
    with patch("src.python.agents.oracle.calculate_rsi", return_value=85.0):
        res = await oracle.perform_ta_analysis({"mint": VALID_MINT})
        assert res["signal"] == "bearish"


@pytest.mark.asyncio
async def test_oracle_ta_insufficient_data(oracle):
    """perform_ta_analysis with insufficient data returns neutral."""
    oracle.fetch_ta_data = AsyncMock(return_value={"prices": [10.0] * 5, "volumes": []})
    res = await oracle.perform_ta_analysis({"mint": VALID_MINT})
    assert res["signal"] == "neutral"


@pytest.mark.asyncio
async def test_oracle_handle_token_received_exception(oracle):
    """Lines 239-240: handle_token_received exception caught."""
    oracle.redis = AsyncMock()
    with patch(
        "src.python.shared.envelope.AgentMessageEnvelope.model_validate_json",
        side_effect=Exception("err"),
    ):
        await oracle.handle_token_received("{}")


@pytest.mark.asyncio
async def test_oracle_get_sol_price_cached(oracle):
    """Line 268: cached SOL price returned."""
    oracle._sol_price_cache = 150.0
    oracle._sol_price_time = time.time()
    price = await oracle.get_sol_price()
    assert price == 150.0


@pytest.mark.asyncio
async def test_oracle_get_sol_price_extreme_fallback(oracle):
    """Line 283: extreme fallback when cache and fetches fail."""
    oracle._sol_price_cache = None
    oracle.fetch_price_jupiter = AsyncMock(return_value=0.0)
    oracle.fetch_price_coingecko = AsyncMock(return_value=0.0)
    price = await oracle.get_sol_price()
    assert price == 200.0


@pytest.mark.asyncio
async def test_oracle_get_sol_price_with_redis(oracle):
    """get_sol_price stores in redis."""
    oracle._sol_price_cache = None
    oracle.fetch_price_jupiter = AsyncMock(return_value=150.0)
    oracle.redis = AsyncMock()
    price = await oracle.get_sol_price()
    assert price == 150.0
    oracle.redis.set.assert_awaited_with("mtus:sol_price", "150.0")


@pytest.mark.asyncio
async def test_oracle_update_price_dexscreener(oracle):
    """Lines 299-300: dexscreener fallback success."""
    oracle.positions["P1"] = {"mint": VALID_MINT, "last_prices": [1.0], "fail_count": 0}
    oracle.fetch_price_jupiter = AsyncMock(return_value=0.0)
    oracle.fetch_price_dexscreener = AsyncMock(return_value=1.5)
    with patch.object(oracle, "fetch_price_birdeye") as mock_b:
        await oracle.update_position_price("P1", VALID_MINT)
        mock_b.assert_not_called()
    assert oracle.positions["P1"]["last_prices"][-1] == 1.5


@pytest.mark.asyncio
async def test_oracle_update_price_birdeye(oracle):
    """Lines 305-306: birdeye fallback success."""
    oracle.positions["P1"] = {"mint": VALID_MINT, "last_prices": [1.0], "fail_count": 0}
    oracle.fetch_price_jupiter = AsyncMock(return_value=0.0)
    oracle.fetch_price_dexscreener = AsyncMock(return_value=0.0)
    oracle.fetch_price_birdeye = AsyncMock(return_value=2.0)
    await oracle.update_position_price("P1", VALID_MINT)
    assert oracle.positions["P1"]["last_prices"][-1] == 2.0


@pytest.mark.asyncio
async def test_oracle_update_price_len_gt_10(oracle):
    """Line 333: pop from last_prices when len > 10."""
    oracle.positions["P1"] = {
        "mint": VALID_MINT,
        "last_prices": [float(i) for i in range(10)],
        "fail_count": 0,
    }
    oracle.fetch_price_jupiter = AsyncMock(return_value=5.0)
    await oracle.update_position_price("P1", VALID_MINT)
    assert len(oracle.positions["P1"]["last_prices"]) == 10


@pytest.mark.asyncio
async def test_oracle_run_off_hours(oracle):
    """Lines 381-383: off-hours unsubscribe."""
    oracle.connect_redis = AsyncMock()
    oracle.pubsub = MagicMock()
    oracle.pubsub.unsubscribe = AsyncMock()

    states = iter([False])

    def active_side():
        try:
            return next(states)
        except StopIteration:
            oracle.running = False
            return False

    with (
        patch(
            "src.python.agents.oracle.is_operational_window_active",
            side_effect=active_side,
        ),
        patch("src.python.agents.oracle.asyncio.sleep", new_callable=AsyncMock),
        patch(
            "src.python.agents.oracle.aiohttp.ClientSession", return_value=AsyncMock()
        ),
    ):
        await oracle.run()


@pytest.mark.asyncio
async def test_oracle_handle_token_received_no_birdeye(oracle):
    """handle_token_received without birdeye key."""
    oracle.redis = AsyncMock()
    oracle.birdeye_key = None
    oracle.perform_ta_analysis = AsyncMock(
        return_value={"signal": "neutral", "rsi": None, "volume_trend": 1.0}
    )
    envelope = _make_envelope(payload={"mint": VALID_MINT, "symbol": "TKN", "is_graduated": True})
    await oracle.handle_token_received(envelope.model_dump_json())
    oracle.redis.publish.assert_awaited()


# ═══════════════════════════════════════════════════════════════════════════════
# nofx.py (92% -> targeted branches)
# ═══════════════════════════════════════════════════════════════════════════════
from src.python.agents.nofx import NofxAgent


@pytest.fixture
def nofx():
    config = {"system": {"environment": "paper"}}
    n = NofxAgent(config)
    n.redis = AsyncMock()
    n.priority_queue = AsyncMock()
    return n


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_buy_track_activity(nofx):
    """buy with solAmount >= 1 tracks activity."""
    with patch.object(
        nofx, "_handle_token_activity", new_callable=AsyncMock
    ) as mock_act:
        await nofx.handle_pumpdev_message(
            {"txType": "buy", "mint": VALID_MINT, "solAmount": 1}
        )
        mock_act.assert_called()


@pytest.mark.asyncio
async def test_nofx_publish_migration_exception(nofx):
    """Line 404: migration exception caught."""
    with patch(
        "src.python.agents.nofx.AgentMessageEnvelope", side_effect=Exception("err")
    ):
        await nofx._publish_migration({"mint": "m"})


@pytest.mark.asyncio
async def test_nofx_publish_migration_exception_catch(nofx):
    """Line 406-407: migration publish exception."""
    with patch.object(nofx.priority_queue, "enqueue", side_effect=Exception("err")):
        await nofx._publish_migration({"mint": VALID_MINT, "signature": "s"})


@pytest.mark.asyncio
async def test_nofx_publish_migration_no_queue(nofx):
    """Line 404: no priority queue falls through."""
    nofx.priority_queue = None
    await nofx._publish_migration({"mint": VALID_MINT, "signature": "s"})


@pytest.mark.asyncio
async def test_nofx_check_trading_paused(nofx):
    """Lines 479-480: paused state closes WS."""
    nofx.ws = AsyncMock()
    nofx.ws.close_code = None
    nofx.redis.get = AsyncMock(return_value="false")
    nofx.redis.get = AsyncMock(
        side_effect=lambda k: "true" if k == "mtus:trading_paused" else None
    )
    result = await nofx.check_trading_state()
    assert result is False


@pytest.mark.asyncio
async def test_nofx_check_trading_off_hours_paper(nofx):
    """Lines 483-502: off-hours closes WS."""
    nofx.is_paper_mode = False
    nofx.ws = AsyncMock()
    nofx.ws.close_code = None
    nofx.helius_ws = AsyncMock()
    nofx.helius_ws.close_code = None
    nofx.redis.get = AsyncMock(return_value=None)
    with patch(
        "src.python.agents.nofx.is_operational_window_active", return_value=False
    ):
        result = await nofx.check_trading_state()
    assert result is False


@pytest.mark.asyncio
async def test_nofx_check_trading_exception(nofx):
    """Lines 505-507: exception returns True."""
    nofx.redis = None  # no redis
    result = await nofx.check_trading_state()
    assert result is True


@pytest.mark.asyncio
async def test_nofx_run_ws_closed_reconnect(nofx):
    """WS closed triggers HTTP polling then reconnect."""
    nofx.connect_redis = AsyncMock()
    nofx.check_trading_state = AsyncMock(return_value=True)
    nofx.poll_for_tokens_http = AsyncMock()
    nofx.connect_pumpdev = AsyncMock(return_value=False)
    nofx.ws = None

    call_count = 0

    async def stop(*a, **kw):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            nofx.running = False

    with patch("asyncio.sleep", side_effect=stop):
        await nofx.run()
    nofx.poll_for_tokens_http.assert_called()


@pytest.mark.asyncio
async def test_nofx_run_ws_message(nofx):
    """Lines 546-554: WS message received and handled."""
    nofx.connect_redis = AsyncMock()
    nofx.check_trading_state = AsyncMock(return_value=True)
    nofx.ws = AsyncMock()
    nofx.ws.close_code = None
    nofx.ws.recv = AsyncMock(
        return_value=json.dumps(
            {
                "txType": "create",
                "mint": VALID_MINT,
                "name": "T",
                "symbol": "S",
                "marketCapSol": 1,
            }
        )
    )

    call_count = 0

    async def stop(*a, **kw):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            nofx.running = False

    with patch("asyncio.sleep", side_effect=stop):
        await nofx.run()


@pytest.mark.asyncio
async def test_nofx_run_ws_timeout(nofx):
    """Line 554-555: WS timeout is handled."""
    nofx.connect_redis = AsyncMock()
    nofx.check_trading_state = AsyncMock(return_value=True)
    nofx.ws = AsyncMock()
    nofx.ws.close_code = None
    nofx.ws.recv = AsyncMock(side_effect=asyncio.TimeoutError)

    call_count = 0

    async def stop(*a, **kw):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            nofx.running = False

    with patch("asyncio.sleep", side_effect=stop):
        await nofx.run()


@pytest.mark.asyncio
async def test_nofx_stop_unsubscribe_error(nofx):
    """Lines 580-581: unsubscribe error caught."""
    nofx.ws = AsyncMock()
    nofx.ws.send = AsyncMock(side_effect=Exception("send err"))
    nofx.helius_ws = AsyncMock()
    await nofx.stop()


@pytest.mark.asyncio
async def test_nofx_handle_helius_message_error(nofx):
    """Error handling for helius message."""
    await nofx.handle_helius_message("invalid json")


@pytest.mark.asyncio
async def test_nofx_extract_mint_no_match(nofx):
    """extract_mint_from_logs no match returns ''."""
    result = nofx.extract_mint_from_logs(["no match here"])
    assert result == ""


@pytest.mark.asyncio
async def test_nofx_run_ws_close_code_raises(nofx):
    """Lines 527-528: bare except when ws.close_code access raises."""
    nofx.connect_redis = AsyncMock()
    nofx.check_trading_state = AsyncMock(return_value=True)
    nofx.poll_for_tokens_http = AsyncMock()
    nofx.connect_pumpdev = AsyncMock(return_value=False)

    class WSMock:
        @property
        def close_code(self):
            raise Exception("check err")

    nofx.ws = WSMock()

    call_count = 0

    async def stop(*a, **kw):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            nofx.running = False

    with patch("asyncio.sleep", side_effect=stop):
        await nofx.run()


@pytest.mark.asyncio
async def test_nofx_run_ws_bool_raises(nofx):
    """Lines 531-533: outer except when self.ws truthiness check raises."""
    nofx.connect_redis = AsyncMock()
    nofx.check_trading_state = AsyncMock(return_value=True)
    nofx.poll_for_tokens_http = AsyncMock()
    nofx.connect_pumpdev = AsyncMock(return_value=False)

    class WSMock:
        def __bool__(self):
            raise Exception("bool err")

    nofx.ws = WSMock()

    call_count = 0

    async def stop(*a, **kw):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            nofx.running = False

    with patch("asyncio.sleep", side_effect=stop):
        await nofx.run()


@pytest.mark.asyncio
async def test_nofx_handle_pumpdev_message_sell(nofx):
    """sell with solAmount >= 1 tracks activity."""
    with patch.object(
        nofx, "_handle_token_activity", new_callable=AsyncMock
    ) as mock_act:
        await nofx.handle_pumpdev_message(
            {"txType": "sell", "mint": VALID_MINT, "solAmount": 1}
        )
        mock_act.assert_called()


# ═══════════════════════════════════════════════════════════════════════════════
# hydra.py (90% -> targeted branches)
# ═══════════════════════════════════════════════════════════════════════════════
from src.python.agents.hydra import HydraAgent


@pytest.fixture
def hydra():
    config = {
        "hydra": {"polling_interval_seconds": 1, "min_bonding_curve_progress": 10.0},
        "qualification": {"max_bonding_curve_progress": 90.0},
    }
    h = HydraAgent(config)
    h.redis = AsyncMock()
    return h


@pytest.mark.asyncio
async def test_hydra_process_token_off_hours(hydra):
    """process_token filters by min_mcap."""
    token_data = {"mint": "LOWMC", "usd_market_cap": 1000}
    await hydra.process_token(token_data)
    hydra.redis.publish.assert_not_called()


@pytest.mark.asyncio
async def test_hydra_process_token_low_replies(hydra):
    """process_token filters by min_replies."""
    token_data = {
        "mint": "LOWREP",
        "virtual_sol_reserves": 40000000000,
        "usd_market_cap": 50000,
        "reply_count": 2,
    }
    await hydra.process_token(token_data)
    hydra.redis.publish.assert_not_called()


@pytest.mark.asyncio
async def test_hydra_process_token_no_socials(hydra):
    """process_token requires socials."""
    token_data = {
        "mint": "NOSOC",
        "virtual_sol_reserves": 40000000000,
        "usd_market_cap": 50000,
        "reply_count": 20,
    }
    await hydra.process_token(token_data)
    hydra.redis.publish.assert_not_called()


@pytest.mark.asyncio
async def test_hydra_process_token_graduated_low_mcap(hydra):
    """Lines 165-167: graduated but below min grad mcap."""
    token_data = {
        "mint": "LOWGRD",
        "virtual_sol_reserves": 85000000000,
        "usd_market_cap": 30000,
        "reply_count": 20,
        "twitter": "t",
    }
    await hydra.process_token(token_data)
    hydra.redis.publish.assert_not_called()


@pytest.mark.asyncio
async def test_hydra_get_bonding_curve_rpc_url_none(hydra):
    """Line 99: get_bonding_curve_data with no rpc_url."""
    hydra.rpc_url = None
    res = await hydra.get_bonding_curve_data("m")
    assert res is None


@pytest.mark.asyncio
async def test_hydra_bonding_curve_normal(hydra):
    """Lines 110-115: bonding curve normal return (placeholder)."""
    hydra.rpc_url = "url"
    res = await hydra.get_bonding_curve_data("m")
    assert res is None


@pytest.mark.asyncio
async def test_hydra_get_sol_price_not_found(hydra):
    """get_sol_price when redis has no price."""
    hydra.redis.get = AsyncMock(return_value=None)
    price = await hydra.get_sol_price()
    assert price == 200.0


@pytest.mark.asyncio
async def test_hydra_get_sol_price_found(hydra):
    """get_sol_price when redis has price."""
    hydra.redis.get = AsyncMock(return_value="150.5")
    price = await hydra.get_sol_price()
    assert price == 150.5


@pytest.mark.asyncio
async def test_hydra_process_token_on_curve_out_of_range(hydra):
    """Lines 172-173: on-curve outside progress range."""
    token_data = {
        "mint": "OUT",
        "virtual_sol_reserves": 30500000000,
        "usd_market_cap": 50000,
        "reply_count": 20,
        "twitter": "t",
    }
    await hydra.process_token(token_data)
    hydra.redis.publish.assert_not_called()


@pytest.mark.asyncio
async def test_hydra_fetch_boosted_error(hydra):
    """Lines 102-103: boosted fetch error."""
    hydra.api_manager.request = AsyncMock(side_effect=Exception("err"))
    res = await hydra.fetch_boosted_dexscreener()
    assert res == []


@pytest.mark.asyncio
async def test_hydra_fetch_boosted_not_list(hydra):
    """boosted fetch returns non-list."""
    hydra.api_manager.request = AsyncMock(return_value=None)
    res = await hydra.fetch_boosted_dexscreener()
    assert res == []


@pytest.mark.asyncio
async def test_hydra_fetch_top_marketcap_error(hydra):
    """fetch_top_marketcap error."""
    hydra.api_manager.request = AsyncMock(side_effect=Exception("err"))
    res = await hydra.fetch_top_marketcap_pumpfun()
    assert res == []


@pytest.mark.asyncio
async def test_hydra_run_trending_fallback(hydra):
    """Lines 229-234: trending fallback when high_value < 10."""
    hydra.connect_redis = AsyncMock()
    hydra.fetch_top_marketcap_pumpfun = AsyncMock(return_value=[{"mint": "M1"}])
    hydra.fetch_trending_pumpfun = AsyncMock(return_value=[{"mint": "M2"}])
    hydra.fetch_boosted_dexscreener = AsyncMock(return_value=[])
    hydra.process_token = AsyncMock()

    async def stop(*a, **kw):
        hydra.running = False

    with (
        patch(
            "src.python.agents.hydra.is_operational_window_active", return_value=True
        ),
        patch("asyncio.sleep", side_effect=stop),
    ):
        await hydra.run()
    hydra.fetch_trending_pumpfun.assert_called()


@pytest.mark.asyncio
async def test_hydra_run_cancelled_error(hydra):
    """Line 242: CancelledError handled."""
    hydra.connect_redis = AsyncMock()

    def raise_cancelled(*a, **kw):
        hydra.running = False
        raise asyncio.CancelledError()

    with (
        patch(
            "src.python.agents.hydra.is_operational_window_active",
            side_effect=raise_cancelled,
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        await hydra.run()


# ═══════════════════════════════════════════════════════════════════════════════
# cassandra.py (94% -> targeted branches)
# ═══════════════════════════════════════════════════════════════════════════════
from src.python.agents.cassandra import CassandraAgent


@pytest.fixture
def cassandra():
    config = {"system": {"environment": "paper"}}
    c = CassandraAgent(config)
    c.redis = AsyncMock()
    c.session = AsyncMock()
    return c


@pytest.mark.asyncio
async def test_cassandra_connect_redis_pubsub(cassandra):
    """Lines 42-47: connect_redis subscribes to channel."""
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
    with patch("aioredis.from_url", AsyncMock(return_value=mock_redis)):
        await cassandra.connect_redis()
        assert cassandra.redis == mock_redis
        mock_pubsub.subscribe.assert_called()


@pytest.mark.asyncio
async def test_cassandra_handle_token_with_sentiment(cassandra):
    """handle_token_received with existing sentiment_score."""
    cassandra.redis = AsyncMock()
    token = {"mint": VALID_MINT, "symbol": "T", "sentiment_score": 90}
    envelope = _make_envelope(payload=token, correlation_id=str(uuid.uuid4()))
    await cassandra.handle_token_received(envelope.model_dump_json())
    cassandra.redis.publish.assert_awaited()


@pytest.mark.asyncio
async def test_cassandra_handle_token_without_social(cassandra):
    """handle_token_received without social signals fetches them."""
    cassandra.redis = AsyncMock()
    cassandra.fetch_dexscreener_data = AsyncMock(
        return_value={"info": {"twitter": "t"}}
    )
    token = {"mint": VALID_MINT, "symbol": "T"}
    envelope = _make_envelope(payload=token, correlation_id=str(uuid.uuid4()))
    await cassandra.handle_token_received(envelope.model_dump_json())
    cassandra.redis.publish.assert_awaited()


@pytest.mark.asyncio
async def test_cassandra_run_window_logic(cassandra):
    """Lines 188-195: window open/close resubscribe."""
    cassandra.connect_redis = AsyncMock()
    cassandra.pubsub = MagicMock()
    cassandra.pubsub.subscribe = AsyncMock()
    cassandra.pubsub.unsubscribe = AsyncMock()

    states = iter([False, True])

    def active():
        try:
            return next(states)
        except StopIteration:
            cassandra.running = False
            return False

    with (
        patch(
            "src.python.agents.cassandra.is_operational_window_active",
            side_effect=active,
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch(
            "src.python.agents.cassandra.aiohttp.ClientSession",
            return_value=AsyncMock(),
        ),
    ):
        await cassandra.run()
    cassandra.pubsub.subscribe.assert_called()


@pytest.mark.asyncio
async def test_cassandra_run_exception(cassandra):
    """Lines 206-209: run loop exception handled."""
    cassandra.connect_redis = AsyncMock()
    cassandra.pubsub = MagicMock()

    def raise_err(*a):
        cassandra.running = False
        raise Exception("stop loop")

    with (
        patch(
            "src.python.agents.cassandra.is_operational_window_active",
            side_effect=raise_err,
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        await cassandra.run()


# ═══════════════════════════════════════════════════════════════════════════════
# ledger.py (95% -> targeted branches)
# ═══════════════════════════════════════════════════════════════════════════════
from src.python.agents.ledger import LedgerAgent


@pytest.fixture
def ledger(tmp_path):
    import sqlite3

    agent = LedgerAgent()
    agent.db = sqlite3.connect(":memory:")
    agent.db.execute("""
        CREATE TABLE IF NOT EXISTS audit_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            envelope_id TEXT, agent_id TEXT, event_type TEXT,
            payload TEXT, timestamp_utc TEXT
        )
    """)
    agent.db.commit()
    agent.audit_file = MagicMock()
    agent.redis = AsyncMock()
    agent.pubsub = AsyncMock()
    agent.running = True
    return agent


@pytest.mark.asyncio
async def test_ledger_run_loop_pubsub_none(ledger):
    """Lines 180-182: pubsub is None reconnects."""
    ledger.pubsub = None
    ledger.connect_redis = AsyncMock()
    ledger.rotate_audit_logs = MagicMock()

    async def stop(*a):
        ledger.running = False

    with (
        patch(
            "src.python.agents.ledger.is_operational_window_active", return_value=True
        ),
        patch("src.python.agents.ledger.asyncio.sleep", side_effect=stop),
        patch("src.python.agents.ledger.open", mock_open()),
    ):
        await ledger.run()
    ledger.connect_redis.assert_awaited()


@pytest.mark.asyncio
async def test_ledger_run_loop_message(ledger):
    """Lines 185-186: message is processed."""
    ledger.connect_redis = AsyncMock()
    ledger.rotate_audit_logs = MagicMock()
    env = _make_envelope()

    msg = {"channel": "ch", "data": env.model_dump_json(), "type": "message"}
    call_count = 0

    async def get_msg(**kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return msg
        ledger.running = False
        return None

    ledger.pubsub.get_message = get_msg
    with (
        patch("src.python.agents.ledger.open", mock_open()),
        patch("src.python.agents.ledger.time.time", return_value=0),
        patch(
            "src.python.agents.ledger.is_operational_window_active",
            return_value=True,
        ),
    ):
        await ledger.run() if ledger.pubsub else None


@pytest.mark.asyncio
async def test_ledger_run_loop_message_not_message_type(ledger):
    """Line 185: non-message type skipped."""
    ledger.connect_redis = AsyncMock()
    ledger.rotate_audit_logs = MagicMock()
    msg = {"channel": "ch", "data": "{}", "type": "subscribe"}
    call_count = 0

    async def get_msg(**kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return msg
        ledger.running = False
        return None

    ledger.pubsub.get_message = get_msg
    with (
        patch("src.python.agents.ledger.open", mock_open()),
        patch(
            "src.python.agents.ledger.is_operational_window_active",
            return_value=True,
        ),
    ):
        await ledger.run() if ledger.pubsub else None


@pytest.mark.asyncio
async def test_ledger_run_loop_exception(ledger):
    """Lines 188-190: run loop exception handled."""
    ledger.connect_redis = AsyncMock()
    ledger.rotate_audit_logs = MagicMock()

    def raise_err():
        ledger.running = False
        raise Exception("loop err")

    with (
        patch(
            "src.python.agents.ledger.is_operational_window_active",
            side_effect=raise_err,
        ),
        patch("src.python.agents.ledger.asyncio.sleep", new_callable=AsyncMock),
        patch("src.python.agents.ledger.open", mock_open()),
    ):
        await ledger.run()


# ═══════════════════════════════════════════════════════════════════════════════
# __main__ block coverage (in-process via runpy with patched asyncio.run)
# ═══════════════════════════════════════════════════════════════════════════════
import runpy


def _run_module_as_main(module_path: str):
    """Execute a module's __main__ block via runpy.run_module with asyncio.run patched."""
    with patch.object(asyncio, "run"):
        runpy.run_module(module_path, run_name="__main__")


def test_hermes_main_block():
    """Line 189: hermes __main__ block."""
    _run_module_as_main("src.python.agents.hermes")


def test_heracles_main_block():
    """Line 173: heracles __main__ block."""
    _run_module_as_main("src.python.agents.heracles")


def test_ledger_main_block():
    """Line 228: ledger __main__ block."""
    _run_module_as_main("src.python.agents.ledger")


def test_portfolio_sizer_main_block():
    """Line 146: portfolio_sizer __main__ block."""
    _run_module_as_main("src.python.agents.portfolio_sizer")


def test_dashboard_bridge_main_block():
    """Line 225: dashboard_bridge __main__ block."""
    _run_module_as_main("src.python.agents.dashboard_bridge")


# ═══════════════════════════════════════════════════════════════════════════════
# Additional fixtures for remaining coverage tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def correlation_id():
    return str(uuid.uuid4())


@pytest.fixture
def anansi_agent():
    config = {
        "system": {"environment": "paper"},
        "qualification": {
            "min_lp_burned_pct": 85,
            "max_rugcheck_score": 999,
            "max_dev_holding_pct": 95,
            "min_market_cap_sol": 5,
            "max_market_cap_sol": 150,
            "min_bonding_curve_progress": 0,
        },
        "trading": {"position_size_sol": 0.1},
    }
    a = AnansiAgent(config)
    a.redis = AsyncMock()
    a.is_paper_mode = False
    return a


@pytest.fixture
def cassandra_agent():
    config = {"system": {"environment": "paper"}}
    c = CassandraAgent(config)
    c.redis = AsyncMock()
    c.session = AsyncMock()
    return c


@pytest.fixture
def nofx_agent():
    config = {"system": {"environment": "paper"}}
    n = NofxAgent(config)
    n.redis = AsyncMock()
    n.priority_queue = AsyncMock()
    return n


@pytest.fixture
def oracle_agent():
    config = {"system": {"environment": "paper"}}
    o = OracleAgent(config)
    o.redis = AsyncMock()
    o.session = AsyncMock()
    return o


# ═══════════════════════════════════════════════════════════════════════════════
# hydra.py remaining gaps
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_hydra_fetch_boosted_success(hydra):
    """Line 99: boosted fetch returns valid list with tokenAddress."""
    hydra.api_manager.request = AsyncMock(
        return_value=[
            {"tokenAddress": "abc123"},
            {"tokenAddress": "def456"},
            {"other": "no_token"},
            {"tokenAddress": ""},
        ]
    )
    result = await hydra.fetch_boosted_dexscreener()
    assert result == ["abc123", "def456"]


@pytest.mark.asyncio
async def test_hydra_get_sol_price_redis_raises(hydra):
    """Lines 127-128: redis.get raises exception, fallback to 200.0."""
    hydra.redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
    price = await hydra.get_sol_price()
    assert price == 200.0


@pytest.mark.asyncio
async def test_hydra_get_sol_price_float_raises(hydra):
    """Lines 127-128: float() conversion raises, fallback to 200.0."""
    hydra.redis.get = AsyncMock(return_value="not_a_number")
    price = await hydra.get_sol_price()
    assert price == 200.0


@pytest.mark.asyncio
async def test_hydra_run_high_value_sufficient(hydra):
    """Line 234: high_value >= 10, trending fetch skipped."""
    hydra.connect_redis = AsyncMock()
    hydra.fetch_top_marketcap_pumpfun = AsyncMock(
        return_value=[{"mint": f"M{i}"} for i in range(10)]
    )
    hydra.fetch_trending_pumpfun = AsyncMock()
    hydra.fetch_boosted_dexscreener = AsyncMock(return_value=[])
    hydra.process_token = AsyncMock()

    async def stop(*a, **kw):
        hydra.running = False

    with (
        patch(
            "src.python.agents.hydra.is_operational_window_active", return_value=True
        ),
        patch("asyncio.sleep", side_effect=stop),
    ):
        await hydra.run()

    hydra.fetch_trending_pumpfun.assert_not_called()
    assert hydra.process_token.call_count == 10


@pytest.mark.asyncio
async def test_hydra_main_block():
    """Line 277: hydra __main__ block."""
    import runpy

    with patch.object(asyncio, "run"):
        runpy.run_module("src.python.agents.hydra", run_name="__main__")


# ═══════════════════════════════════════════════════════════════════════════════
# cassandra.py remaining gaps
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cassandra_score_sentiment_metadata_socials(cassandra_agent):
    """Lines 121-125: telegram and website socials from metadata."""
    token = {"mint": "", "uri": "https://arweave.net/abc", "age": 500}
    cassandra_agent.fetch_metadata_socials = AsyncMock(
        return_value={"twitter": False, "telegram": True, "website": True}
    )
    score = await cassandra_agent.score_sentiment(token)
    assert score == 70  # 50 base + 15 telegram + 10 website - 5 age


@pytest.mark.asyncio
async def test_cassandra_run_loop_processes_message(cassandra_agent):
    """Line 203: run loop processes a pubsub message."""
    import json
    from src.python.shared.envelope import AgentMessageEnvelope

    envelope = AgentMessageEnvelope(
        agent_id="AGT-01",
        event_type="token_received",
        payload={"mint": "abc", "symbol": "TKN"},
        correlation_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    )
    message_data = envelope.model_dump_json()

    cassandra_agent.connect_redis = AsyncMock()
    cassandra_agent.redis = AsyncMock()
    cassandra_agent.session = AsyncMock()
    cassandra_agent.handle_token_received = AsyncMock()
    cassandra_agent.pubsub = MagicMock()
    cassandra_agent.pubsub.get_message = AsyncMock(return_value={"data": message_data})

    async def stop(*a, **kw):
        cassandra_agent.running = False

    with (
        patch(
            "src.python.agents.cassandra.is_operational_window_active",
            return_value=True,
        ),
        patch("src.python.agents.cassandra.asyncio.sleep", side_effect=stop),
        patch("src.python.agents.cassandra.aiohttp.ClientSession"),
    ):
        await cassandra_agent.run()

    cassandra_agent.handle_token_received.assert_awaited_once_with(message_data)


@pytest.mark.asyncio
async def test_cassandra_stop_with_pubsub(cassandra_agent):
    """Line 216: stop() with pubsub set."""
    cassandra_agent.redis = AsyncMock()
    cassandra_agent.session = AsyncMock()
    cassandra_agent.pubsub = MagicMock()
    cassandra_agent.pubsub.unsubscribe = AsyncMock()
    await cassandra_agent.stop()
    assert cassandra_agent.running is False
    cassandra_agent.pubsub.unsubscribe.assert_awaited_once()
    cassandra_agent.redis.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_cassandra_main_block():
    """Line 249: cassandra __main__ block."""
    import runpy

    with patch.object(asyncio, "run"):
        runpy.run_module("src.python.agents.cassandra", run_name="__main__")


# ═══════════════════════════════════════════════════════════════════════════════
# oracle.py remaining gaps
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_oracle_fetch_ta_data_exception(oracle_agent):
    """Lines 162-163: fetch_ta_data Birdeye OHLCV exception."""
    oracle_agent.birdeye_key = "test-key"
    oracle_agent.session = AsyncMock()
    oracle_agent.session.get.side_effect = Exception("Connection error")
    with patch("src.python.agents.oracle.time") as mock_time:
        mock_time.time.return_value = 1000
        mock_time.strftime = __import__("time").strftime
        result = await oracle_agent.fetch_ta_data("test-mint")
    assert "prices" in result
    assert "volumes" in result


@pytest.mark.asyncio
async def test_oracle_fetch_ohlcv_dexscreener(oracle_agent):
    """Line 175: DexScreener OHLCV stub returns []."""
    result = await oracle_agent.fetch_ohlcv_dexscreener("test-mint")
    assert result == []


@pytest.mark.asyncio
async def test_oracle_perform_ta_momentum_breakout(oracle_agent):
    """Line 209: perform_ta_analysis momentum breakout signal."""
    with (
        patch("src.python.agents.oracle.calculate_rsi", return_value=60.0),
        patch("src.python.agents.oracle.analyze_trend", return_value="bullish"),
        patch("src.python.agents.oracle.calculate_volume_trend", return_value=1.0),
    ):
        oracle_agent.fetch_ta_data = AsyncMock(
            return_value={"prices": [50.0] * 14, "volumes": [1000.0] * 14}
        )
        result = await oracle_agent.perform_ta_analysis({"mint": "test-mint"})
        assert result["signal"] == "bullish"


@pytest.mark.asyncio
async def test_oracle_run_off_hours_unsubscribe(oracle_agent):
    """Lines 381-383: run loop off-hours unsubscription."""
    oracle_agent.connect_redis = AsyncMock()
    oracle_agent.redis = AsyncMock()
    oracle_agent.session = AsyncMock()

    class FakePubsub:
        def __init__(self):
            self.subscribe = AsyncMock()
            self.unsubscribe = AsyncMock()
            self.get_message = AsyncMock(return_value=None)

    oracle_agent.pubsub = FakePubsub()
    window_responses = [True, False]

    def window_side_effect():
        return window_responses.pop(0) if window_responses else False

    sleep_count = 0

    async def stop(*a, **kw):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count > 1:
            oracle_agent.running = False

    with (
        patch(
            "src.python.agents.oracle.is_operational_window_active",
            side_effect=window_side_effect,
        ),
        patch("src.python.agents.oracle.asyncio.sleep", side_effect=stop),
        patch(
            "src.python.agents.oracle.aiohttp.ClientSession", return_value=AsyncMock()
        ),
    ):
        await oracle_agent.run()

    oracle_agent.pubsub.unsubscribe.assert_awaited()


@pytest.mark.asyncio
async def test_oracle_run_processes_messages(oracle_agent):
    """Lines 391-406: run loop processes position_opened and token_received messages."""
    import json
    from datetime import datetime

    oracle_agent.connect_redis = AsyncMock()
    oracle_agent.redis = AsyncMock()
    oracle_agent.session = AsyncMock()

    msg_iter = iter(
        [
            {
                "channel": "mtus:channel:position_opened",
                "data": json.dumps(
                    {
                        "payload": {
                            "position_id": "p1",
                            "mint": "abc",
                            "entry_price_sol": 1.0,
                            "symbol": "TST",
                        }
                    }
                ),
            },
            {
                "channel": "mtus:channel:token_received",
                "data": json.dumps({"payload": {"mint": "xyz", "symbol": "TEST"}}),
            },
            None,
        ]
    )

    oracle_agent.pubsub = MagicMock()
    oracle_agent.pubsub.subscribe = AsyncMock()
    oracle_agent.pubsub.unsubscribe = AsyncMock()
    oracle_agent.pubsub.get_message = AsyncMock(
        side_effect=lambda *a, **kw: next(msg_iter)
    )
    oracle_agent.get_sol_price = AsyncMock(return_value=200.0)
    oracle_agent.handle_position_opened = AsyncMock()
    oracle_agent.handle_token_received = AsyncMock()
    oracle_agent.update_position_price = AsyncMock()
    oracle_agent.positions = {
        "p1": {"mint": "abc", "last_prices": [1.0], "fail_count": 0}
    }

    sleep_count = 0

    async def stop(*a, **kw):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count > 1:
            oracle_agent.running = False

    get_message_mock = oracle_agent.pubsub.get_message

    with (
        patch(
            "src.python.agents.oracle.is_operational_window_active", return_value=True
        ),
        patch("src.python.agents.oracle.asyncio.sleep", side_effect=stop),
        patch(
            "src.python.agents.oracle.aiohttp.ClientSession", return_value=AsyncMock()
        ),
    ):
        await oracle_agent.run()

    assert get_message_mock.await_count > 0, "get_message was never called"
    assert oracle_agent.handle_position_opened.await_count > 0, (
        "handle_position_opened was never awaited"
    )
    assert oracle_agent.handle_token_received.await_count > 0, (
        "handle_token_received was never awaited"
    )


@pytest.mark.asyncio
async def test_oracle_stop_with_pubsub(oracle_agent):
    """Line 418: stop() with pubsub set."""
    oracle_agent.session = AsyncMock()
    oracle_agent.pubsub = MagicMock()
    oracle_agent.pubsub.unsubscribe = AsyncMock()
    oracle_agent.redis = AsyncMock()
    await oracle_agent.stop()
    oracle_agent.pubsub.unsubscribe.assert_awaited_once()


@pytest.mark.asyncio
async def test_oracle_main_block():
    """Line 451: oracle __main__ block."""
    import runpy

    with patch.object(asyncio, "run"):
        runpy.run_module("src.python.agents.oracle", run_name="__main__")


# ═══════════════════════════════════════════════════════════════════════════════
# nofx.py remaining gaps
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_nofx_handle_new_token_rate_limited(nofx_agent):
    """Lines 325-326: rate limit exceeded, token skipped."""
    nofx_agent.check_rate_limit = MagicMock(return_value=False)
    nofx_agent.priority_queue = AsyncMock()
    token_data = {
        "mint": "So11111111111111111111111111111111111111112",
        "name": "Test",
        "symbol": "TST",
        "marketCapSol": 1.0,
        "uri": "https://example.com/meta.json",
        "bondingCurveKey": VALID_MINT,
        "traderPublicKey": VALID_MINT,
    }
    await nofx_agent._handle_new_token(token_data)
    nofx_agent.priority_queue.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_nofx_handle_new_token_no_queue(nofx_agent):
    """Line 342: warning when no priority queue configured."""
    nofx_agent.check_rate_limit = MagicMock(return_value=True)
    nofx_agent.priority_queue = None
    token_data = {
        "mint": VALID_MINT,
        "name": "Test",
        "symbol": "TST",
        "marketCapSol": 1.0,
        "uri": "https://example.com/meta.json",
        "bondingCurveKey": VALID_MINT,
        "traderPublicKey": VALID_MINT,
    }
    await nofx_agent._handle_new_token(token_data)


@pytest.mark.asyncio
async def test_nofx_handle_helius_no_queue(nofx_agent):
    """Line 433: warning when no priority queue in Helius handler."""
    nofx_agent.priority_queue = None
    message = {
        "method": "programNotification",
        "params": {
            "result": {
                "value": {
                    "logs": [
                        "InitializeInstruction",
                        "initialize So11111111111111111111111111111111111111112",
                    ]
                }
            }
        },
    }
    await nofx_agent.handle_helius_message(json.dumps(message))


@pytest.mark.asyncio
async def test_nofx_check_trading_state_exception(nofx_agent):
    """Lines 505-507: check_trading_state exception fallback to True."""
    nofx_agent.redis.get = AsyncMock(side_effect=Exception("Redis error"))
    result = await nofx_agent.check_trading_state()
    assert result is True


@pytest.mark.asyncio
async def test_nofx_run_ws_bytes_message(nofx_agent):
    """Line 548: WebSocket receives bytes message."""
    nofx_agent.connect_redis = AsyncMock()
    nofx_agent.connect_pumpdev = AsyncMock(return_value=True)
    nofx_agent.priority_queue = AsyncMock()
    nofx_agent.check_trading_state = AsyncMock(return_value=True)

    class BytesWS:
        def __init__(self):
            self._called = False

        @property
        def close_code(self):
            return None

        async def recv(self):
            if not self._called:
                self._called = True
                return b'{"txType": "create", "mint": "So11111111111111111111111111111111111111112", "name": "T", "symbol": "T", "uri": "https://example.com/meta.json", "marketCapSol": 1.0, "bondingCurveKey": null, "traderPublicKey": null}'
            raise Exception("stop loop")

    nofx_agent.ws = BytesWS()
    nofx_agent.ws_connected = True

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await nofx_agent.run()


@pytest.mark.asyncio
async def test_nofx_run_timeout_error(nofx_agent):
    """Line 554: asyncio.TimeoutError silently passed."""
    nofx_agent.connect_redis = AsyncMock()
    nofx_agent.connect_pumpdev = AsyncMock(return_value=True)
    nofx_agent.priority_queue = AsyncMock()
    nofx_agent.check_trading_state = AsyncMock(return_value=True)
    nofx_agent.ws = AsyncMock()
    nofx_agent.ws.close_code = None
    nofx_agent.ws_connected = True
    nofx_agent.ws.recv = AsyncMock(
        side_effect=[
            asyncio.TimeoutError(),
            asyncio.TimeoutError(),
            asyncio.TimeoutError(),
            Exception("stop loop"),
        ]
    )

    loop_count = 0

    async def stop(*a, **kw):
        nonlocal loop_count
        loop_count += 1
        if loop_count > 1:
            nofx_agent.running = False

    with (
        patch("asyncio.sleep", side_effect=stop),
    ):
        await nofx_agent.run()


@pytest.mark.asyncio
async def test_nofx_run_json_decode_error(nofx_agent):
    """Line 559: sleep after non-fatal inner exception."""
    nofx_agent.connect_redis = AsyncMock()
    nofx_agent.connect_pumpdev = AsyncMock(return_value=True)
    nofx_agent.priority_queue = AsyncMock()
    nofx_agent.check_trading_state = AsyncMock(return_value=True)
    nofx_agent.ws = AsyncMock()
    nofx_agent.ws.close_code = None
    nofx_agent.ws_connected = True
    nofx_agent.ws.recv = AsyncMock(side_effect=["not valid json", None])

    calls = 0

    async def stop(*a, **kw):
        nonlocal calls
        calls += 1
        if calls > 2:
            nofx_agent.running = False

    with (
        patch("asyncio.sleep", side_effect=stop),
    ):
        await nofx_agent.run()


@pytest.mark.asyncio
async def test_nofx_run_outer_exception_no_stop(nofx_agent):
    """Line 564: sleep after outer exception without 'stop' in message."""
    nofx_agent.connect_redis = AsyncMock()
    nofx_agent.connect_pumpdev = AsyncMock(return_value=True)
    nofx_agent.check_trading_state = AsyncMock(side_effect=Exception("random error"))
    nofx_agent.ws = None
    nofx_agent.ws_connected = False
    nofx_agent.priority_queue = AsyncMock()

    calls = 0

    async def stop(*a, **kw):
        nonlocal calls
        calls += 1
        if calls > 1:
            nofx_agent.running = False

    with (
        patch("asyncio.sleep", side_effect=stop),
    ):
        await nofx_agent.run()


@pytest.mark.asyncio
async def test_nofx_main_block():
    """Line 623: nofx __main__ block."""
    import runpy

    with patch.object(asyncio, "run"):
        runpy.run_module("src.python.agents.nofx", run_name="__main__")


# ═══════════════════════════════════════════════════════════════════════════════
# anansi.py remaining gaps
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_anansi_fetch_rugcheck_no_data(anansi_agent):
    """Line 100: fetch_rugcheck_summary returns {} when API returns falsy."""
    anansi_agent._rugcheck_cache = {}
    anansi_agent.api_manager.request = AsyncMock(return_value=None)
    result = await anansi_agent._fetch_rugcheck_summary("test-mint")
    assert result == {}


@pytest.mark.asyncio
async def test_anansi_g6_no_data_not_graduated(anansi_agent):
    """Lines 235-236: check_g6_rugcheck_score with no data, not graduated."""
    anansi_agent._fetch_rugcheck_summary = AsyncMock(return_value=None)
    result = await anansi_agent.check_g6_rugcheck_score("test-mint", is_graduated=False)
    assert result is False


@pytest.mark.asyncio
async def test_anansi_qualify_g3_non_pump(anansi_agent, correlation_id):
    """Line 572: qualify_token G3 non-pump/non-migrated path."""
    anansi_agent.is_paper_mode = False
    for gate in [
        "check_g1_mint_authority",
        "check_g2_freeze_authority",
        "check_g4_dev_holdings",
        "check_g5_top10_concentration",
        "check_g6_rugcheck_score",
        "check_g7_liquidity_size",
        "check_g9_duplicate",
        "check_g10_honeypot",
        "check_g11_sentiment",
        "check_g12_bonding_curve",
        "check_g13_technical_analysis",
    ]:
        setattr(anansi_agent, gate, AsyncMock(return_value=True))
    anansi_agent.check_g8_social_metadata = AsyncMock(return_value=True)

    token = {
        "mint": "So11111111111111111111111111111111111111112",
        "symbol": "TST",
        "marketCapSol": 10.0,
        "v_sol_in_bonding_curve": 5.0,
        "is_pump": False,
    }
    result = await anansi_agent.qualify_token(token, correlation_id)
    assert result is True


@pytest.mark.asyncio
async def test_anansi_qualify_g8_fails_prod(anansi_agent, correlation_id):
    """Lines 597-601: G8 social metadata fails in prod mode, gate still passes."""
    anansi_agent.is_paper_mode = False
    for gate in [
        "check_g1_mint_authority",
        "check_g2_freeze_authority",
        "check_g3_lp_lock",
        "check_g4_dev_holdings",
        "check_g5_top10_concentration",
        "check_g6_rugcheck_score",
        "check_g7_liquidity_size",
        "check_g9_duplicate",
        "check_g10_honeypot",
        "check_g11_sentiment",
        "check_g12_bonding_curve",
        "check_g13_technical_analysis",
    ]:
        setattr(anansi_agent, gate, AsyncMock(return_value=True))
    anansi_agent.check_g8_social_metadata = AsyncMock(return_value=False)

    token = {
        "mint": "So11111111111111111111111111111111111111112",
        "symbol": "TST",
        "marketCapSol": 10.0,
        "v_sol_in_bonding_curve": 5.0,
        "is_pump": False,
        "uri": "https://example.com/meta.json",
    }
    result = await anansi_agent.qualify_token(token, correlation_id)
    assert result is True


@pytest.mark.asyncio
async def test_anansi_qualify_g13_fails_graduated(anansi_agent, correlation_id):
    """Line 632: G13 fails for graduated token, should reject."""
    anansi_agent.is_paper_mode = False
    for gate in [
        "check_g1_mint_authority",
        "check_g2_freeze_authority",
        "check_g3_lp_lock",
        "check_g4_dev_holdings",
        "check_g5_top10_concentration",
        "check_g6_rugcheck_score",
        "check_g7_liquidity_size",
        "check_g8_social_metadata",
        "check_g9_duplicate",
        "check_g10_honeypot",
        "check_g11_sentiment",
        "check_g12_bonding_curve",
    ]:
        setattr(anansi_agent, gate, AsyncMock(return_value=True))
    anansi_agent.check_g13_technical_analysis = AsyncMock(return_value=False)

    token = {
        "mint": "So11111111111111111111111111111111111111112",
        "symbol": "TST",
        "marketCapSol": 10.0,
        "is_graduated": True,
        "ta_signal": "bearish",
    }
    result = await anansi_agent.qualify_token(token, correlation_id)
    assert result is False


@pytest.mark.asyncio
async def test_anansi_qualify_paper_graduated_g8_added(anansi_agent, correlation_id):
    """Line 647: G8 added to required gates for graduated token in paper mode."""
    anansi_agent.is_paper_mode = True
    for gate in [
        "check_g1_mint_authority",
        "check_g2_freeze_authority",
        "check_g7_liquidity_size",
        "check_g10_honeypot",
        "check_g11_sentiment",
        "check_g12_bonding_curve",
        "check_g13_technical_analysis",
    ]:
        setattr(anansi_agent, gate, AsyncMock(return_value=True))

    token = {
        "mint": "So11111111111111111111111111111111111111112",
        "symbol": "TST",
        "marketCapSol": 10.0,
        "is_graduated": True,
        "ta_signal": "bullish",
    }
    result = await anansi_agent.qualify_token(token, correlation_id)
    assert result is True


@pytest.mark.asyncio
async def test_anansi_run_stop_exception(anansi_agent):
    """Line 766: run loop breaks on exception containing 'stop'."""
    anansi_agent.connect_redis = AsyncMock()
    anansi_agent.pubsub = AsyncMock()
    anansi_agent.pubsub.get_message = AsyncMock(side_effect=Exception("stop requested"))

    with (
        patch(
            "src.python.agents.anansi.is_operational_window_active", return_value=True
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        await anansi_agent.run()


@pytest.mark.asyncio
async def test_anansi_main_block():
    """Line 799: anansi __main__ block."""
    import runpy

    with patch.object(asyncio, "run"):
        runpy.run_module("src.python.agents.anansi", run_name="__main__")


@pytest.mark.asyncio
async def test_anansi_qualify_g8_succeeds_prod(anansi_agent, correlation_id):
    """Line 653: G8 succeeds in prod mode with valid URI."""
    anansi_agent.is_paper_mode = False
    for gate in [
        "check_g1_mint_authority",
        "check_g2_freeze_authority",
        "check_g3_lp_lock",
        "check_g4_dev_holdings",
        "check_g5_top10_concentration",
        "check_g6_rugcheck_score",
        "check_g7_liquidity_size",
        "check_g9_duplicate",
        "check_g10_honeypot",
        "check_g11_sentiment",
        "check_g12_bonding_curve",
        "check_g13_technical_analysis",
    ]:
        setattr(anansi_agent, gate, AsyncMock(return_value=True))
    anansi_agent.check_g8_social_metadata = AsyncMock(return_value=True)

    token = {
        "mint": "So11111111111111111111111111111111111111112",
        "symbol": "TST",
        "marketCapSol": 10.0,
        "v_sol_in_bonding_curve": 5.0,
        "is_pump": False,
        "uri": "https://example.com/meta.json",
    }
    result = await anansi_agent.qualify_token(token, correlation_id)
    assert result is True


@pytest.mark.asyncio
async def test_anansi_qualify_g11_not_mocked_fails(anansi_agent, correlation_id):
    """Line 689: G11 not mocked and returns False, gate fails."""
    anansi_agent.is_paper_mode = False
    for gate in [
        "check_g1_mint_authority",
        "check_g2_freeze_authority",
        "check_g3_lp_lock",
        "check_g4_dev_holdings",
        "check_g5_top10_concentration",
        "check_g6_rugcheck_score",
        "check_g7_liquidity_size",
        "check_g8_social_metadata",
        "check_g9_duplicate",
        "check_g10_honeypot",
        "check_g12_bonding_curve",
        "check_g13_technical_analysis",
    ]:
        setattr(anansi_agent, gate, AsyncMock(return_value=True))

    async def fake_g11(_mint):
        return False

    anansi_agent.check_g11_sentiment = fake_g11

    token = {
        "mint": "So11111111111111111111111111111111111111112",
        "symbol": "TST",
        "marketCapSol": 10.0,
        "v_sol_in_bonding_curve": 5.0,
        "is_pump": False,
    }
    result = await anansi_agent.qualify_token(token, correlation_id)
    assert result is False
