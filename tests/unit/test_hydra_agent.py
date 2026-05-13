import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.hydra import HydraAgent, main

@pytest.fixture
def hydra_agent():
    config = {
        "hydra": {
            "polling_interval_seconds": 1,
            "min_bonding_curve_progress": 10.0
        },
        "qualification": {
            "max_bonding_curve_progress": 90.0
        }
    }
    agent = HydraAgent(config)
    agent.redis = AsyncMock()
    return agent

@pytest.mark.asyncio
async def test_hydra_connect_redis(hydra_agent):
    with patch("aioredis.from_url", new_callable=AsyncMock) as mock_redis:
        mock_r = AsyncMock()
        mock_redis.return_value = mock_r
        await hydra_agent.connect_redis()
        assert hydra_agent.redis == mock_r

@pytest.mark.asyncio
async def test_hydra_fetch_trending_pumpfun(hydra_agent):
    hydra_agent.api_manager.request = AsyncMock(return_value=[{"mint": "m1"}])
    res = await hydra_agent.fetch_trending_pumpfun()
    assert len(res) == 1
    assert res[0]["mint"] == "m1"

@pytest.mark.asyncio
async def test_hydra_fetch_trending_pumpfun_error(hydra_agent):
    hydra_agent.api_manager.request = AsyncMock(side_effect=Exception("api down"))
    res = await hydra_agent.fetch_trending_pumpfun()
    assert res == []

@pytest.mark.asyncio
async def test_hydra_process_token(hydra_agent):
    token_data = {
        "mint": "MINT123",
        "symbol": "TKN",
        "name": "Token",
        "virtual_sol_reserves": 40000000000, # (40-30)/55 * 100 = ~18%
        "usd_market_cap": 50000
    }
    await hydra_agent.process_token(token_data)
    hydra_agent.redis.publish.assert_called_once()
    
    # Process same mint again should skip
    hydra_agent.redis.publish.reset_mock()
    await hydra_agent.process_token(token_data)
    hydra_agent.redis.publish.assert_not_called()

@pytest.mark.asyncio
async def test_hydra_process_token_out_of_bounds(hydra_agent):
    # Too low
    token_data = {
        "mint": "LOW",
        "virtual_sol_reserves": 31000000000, # ~1.8%
    }
    await hydra_agent.process_token(token_data)
    hydra_agent.redis.publish.assert_not_called()

@pytest.mark.asyncio
async def test_hydra_get_bonding_curve_data(hydra_agent):
    # Currently a placeholder
    assert await hydra_agent.get_bonding_curve_data("mint") is None

@pytest.mark.asyncio
async def test_hydra_run_loop(hydra_agent):
    hydra_agent.fetch_trending_pumpfun = AsyncMock(return_value=[{"mint": "M1", "virtual_sol_reserves": 40000000000}])
    hydra_agent.process_token = AsyncMock()
    
    # Patch is_operational_window_active to return True then False/raise to break
    call_count = 0
    def side_effect():
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            hydra_agent.running = False
            return False
        return True

    with patch("src.python.agents.hydra.is_operational_window_active", side_effect=side_effect), \
         patch.object(hydra_agent, "connect_redis", new_callable=AsyncMock), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        await hydra_agent.run()
    
    hydra_agent.process_token.assert_called()

@pytest.mark.asyncio
async def test_hydra_stop(hydra_agent):
    await hydra_agent.stop()
    hydra_agent.redis.close.assert_called_once()
@pytest.mark.asyncio
async def test_hydra_main_keyboard_interrupt():
    m = mock_open(read_data="hydra:\n  polling_interval_seconds: 1\n")
    with patch("src.python.agents.hydra.open", m), \
         patch("src.python.agents.hydra.HydraAgent") as mock_agent_class, \
         patch("src.python.agents.hydra.validate_config", return_value=(True, None)):
        
        mock_agent_instance = mock_agent_class.return_value
        mock_agent_instance.run = AsyncMock(side_effect=KeyboardInterrupt())
        mock_agent_instance.stop = AsyncMock()
        
        await main()
        assert mock_agent_instance.run.called
        assert mock_agent_instance.stop.called

@pytest.mark.asyncio
async def test_hydra_main_config_error():
    m = mock_open(read_data="hydra:\n  polling_interval_seconds: 1\n")
    with patch("src.python.agents.hydra.open", m), \
         patch("src.python.agents.hydra.validate_config", return_value=(False, "error")), \
         patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        
        with pytest.raises(SystemExit) as exc:
            await main()
        assert exc.value.code == 1

@pytest.mark.asyncio
async def test_hydra_fetch_trending_pumpfun_none(hydra_agent):
    hydra_agent.api_manager.request = AsyncMock(return_value=None)
    res = await hydra_agent.fetch_trending_pumpfun()
    assert res == []

@pytest.mark.asyncio
async def test_hydra_get_bonding_curve_data_no_rpc(hydra_agent):
    hydra_agent.rpc_url = None
    res = await hydra_agent.get_bonding_curve_data("m")
    assert res is None

@pytest.mark.asyncio
async def test_hydra_process_token_clear_cache(hydra_agent):
    hydra_agent._processed_mints = {f"m{i}" for i in range(1000)}
    token_data = {"mint": "NEW", "virtual_sol_reserves": 40000000000}
    await hydra_agent.process_token(token_data)
    assert len(hydra_agent._processed_mints) == 1 # Cleared then added NEW
    assert "NEW" in hydra_agent._processed_mints

@pytest.mark.asyncio
async def test_hydra_run_loop_exception(hydra_agent):
    hydra_agent.fetch_trending_pumpfun = AsyncMock(side_effect=[Exception("loop fail"), []])
    hydra_agent.running = True
    
    async def stop_loop(*args, **kwargs):
        hydra_agent.running = False
        return None

    with patch("src.python.agents.hydra.is_operational_window_active", return_value=True), \
         patch.object(hydra_agent, "connect_redis", new_callable=AsyncMock), \
         patch("asyncio.sleep", side_effect=stop_loop):
        await hydra_agent.run()
    
    # Should have handled the exception and called sleep
    hydra_agent.fetch_trending_pumpfun.assert_called()

@pytest.mark.asyncio
async def test_hydra_main_load_config_error():
    with patch("src.python.agents.hydra.open", side_effect=Exception("file error")), \
         patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        with pytest.raises(SystemExit) as exc:
            await main()
        assert exc.value.code == 1
