import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.python.shared.rate_limiter import RateLimiter

@pytest.fixture
def limiter():
    return RateLimiter(max_trades_per_hour=10, max_concurrent_positions=3)

@pytest.mark.asyncio
async def test_connect(limiter):
    mock_redis = MagicMock()
    with patch("aioredis.from_url", new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
        await limiter.connect()
        mock_from_url.assert_called_once_with(limiter.redis_url, decode_responses=True)
        assert limiter.redis is mock_redis

@pytest.mark.asyncio
async def test_can_trade_success(limiter):
    limiter.redis = AsyncMock()
    limiter.redis.scard.return_value = 1 # 1 active position
    limiter.redis.get.return_value = "5" # 5 trades this hour
    
    can, reason = await limiter.can_trade()
    assert can is True
    assert reason == "OK"

@pytest.mark.asyncio
async def test_can_trade_max_positions(limiter):
    limiter.redis = AsyncMock()
    limiter.redis.scard.return_value = 3
    
    can, reason = await limiter.can_trade()
    assert can is False
    assert "Max concurrent positions" in reason

@pytest.mark.asyncio
async def test_can_trade_max_hourly(limiter):
    limiter.redis = AsyncMock()
    limiter.redis.scard.return_value = 1
    limiter.redis.get.return_value = "10"
    
    can, reason = await limiter.can_trade()
    assert can is False
    assert "Max trades per hour" in reason

@pytest.mark.asyncio
async def test_record_trade(limiter):
    limiter.redis = AsyncMock()
    await limiter.record_trade()
    limiter.redis.incr.assert_called_once()
    limiter.redis.delete.assert_called_once()

@pytest.mark.asyncio
async def test_add_remove_position(limiter):
    limiter.redis = AsyncMock()
    await limiter.add_position("pos1")
    limiter.redis.sadd.assert_called_once_with("mtus:active_positions", "pos1")
    
    await limiter.remove_position("pos1")
    limiter.redis.srem.assert_called_once_with("mtus:active_positions", "pos1")

@pytest.mark.asyncio
async def test_get_status(limiter):
    limiter.redis = AsyncMock()
    limiter.redis.scard.return_value = 2
    limiter.redis.get.return_value = "7"
    
    status = await limiter.get_status()
    assert status["active_positions"] == 2
    assert status["trades_this_hour"] == 7
    assert status["can_trade"] is True
