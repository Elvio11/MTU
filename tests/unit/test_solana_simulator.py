import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from src.python.shared.solana_simulator import SolanaSimulator

@pytest.fixture
def simulator():
    return SolanaSimulator(rpc_url="http://mock-rpc")

@pytest.mark.asyncio
async def test_simulate_transaction(simulator):
    mock_resp = {"result": {"value": {"err": None, "logs": ["log1"]}}}
    
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=MagicMock(json=AsyncMock(return_value=mock_resp)))
    cm.__aexit__ = AsyncMock()
    
    with patch("aiohttp.ClientSession.post", return_value=cm):
        result = await simulator.simulate_transaction("tx_base64")
        assert result == mock_resp

@pytest.mark.asyncio
async def test_get_jupiter_quote(simulator):
    mock_quote = {"inputMint": "A", "outputMint": "B", "outAmount": "100"}
    
    cm = MagicMock()
    resp = MagicMock(status=200, json=AsyncMock(return_value=mock_quote))
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock()
    
    with patch("aiohttp.ClientSession.get", return_value=cm):
        result = await simulator.get_jupiter_quote("A", "B", 1000)
        assert result == mock_quote

@pytest.mark.asyncio
async def test_build_transaction(simulator):
    mock_resp = {"swapTransaction": "encoded_tx"}
    
    cm = MagicMock()
    resp = MagicMock(status=200, json=AsyncMock(return_value=mock_resp))
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock()
    
    with patch("aiohttp.ClientSession.post", return_value=cm):
        result = await simulator.build_transaction({"quote": "data"}, "user_pubkey")
        assert result == "encoded_tx"

@pytest.mark.asyncio
async def test_simulate_buy_sell_cycle_pass(simulator):
    # Mock all internal methods
    simulator.get_jupiter_quote = AsyncMock(side_effect=[
        {"outAmount": "100"}, # Buy quote
        {"outAmount": "10"}    # Sell quote
    ])
    simulator.build_transaction = AsyncMock(side_effect=["buy_tx", "sell_tx"])
    simulator.simulate_transaction = AsyncMock(side_effect=[
        {"result": {"value": {"err": None}}}, # Buy sim
        {"result": {"value": {"err": None, "logs": ["Program log: Transferring 10 tokens"]}}} # Sell sim
    ])
    
    result = await simulator.simulate_buy_sell_cycle("mint", "user_pubkey")
    assert result["is_honeypot"] is False
    assert "Passed" in result["reason"]

@pytest.mark.asyncio
async def test_simulate_buy_sell_cycle_fail_buy_quote(simulator):
    simulator.get_jupiter_quote = AsyncMock(return_value=None)
    result = await simulator.simulate_buy_sell_cycle("mint", "user_pubkey")
    assert result["is_honeypot"] is True
    assert "Buy quote failed" in result["reason"]

@pytest.mark.asyncio
async def test_execute_swap(simulator):
    simulator.build_transaction = AsyncMock(return_value="tx_data")
    sign_func = AsyncMock(return_value={"success": True, "tx_sig": "sig"})
    
    result = await simulator.execute_swap({"quote": "data"}, "user_pubkey", sign_func, "rpc")
    assert result["success"] is True
    assert result["tx_sig"] == "sig"
    sign_func.assert_called_with("tx_data")

@pytest.mark.asyncio
async def test_execute_swap_no_sign_func(simulator):
    quote = {"inputMint": "SOL", "outputMint": "USDC"}
    result = await simulator.execute_swap(quote, "user_pk", None, "http://rpc")
    assert result["success"] is False
    assert "No sign function provided" in result["error"]

@pytest.mark.asyncio
async def test_execute_swap_exception(simulator):
    quote = {"inputMint": "SOL", "outputMint": "USDC"}
    with patch.object(simulator, "build_transaction", side_effect=Exception("Build error")):
        result = await simulator.execute_swap(quote, "user_pk", AsyncMock(), "http://rpc")
        assert result["success"] is False
        assert "Build error" in result["error"]

@pytest.mark.asyncio
async def test_build_transaction_exception(simulator):
    # Mocking session.post to raise exception
    with patch("aiohttp.ClientSession.post", side_effect=Exception("Network error")):
        tx = await simulator.build_transaction({}, "user_pk")
        assert tx is not None
        # Should return fallback transaction
        assert len(tx) > 0
