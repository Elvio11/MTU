import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from src.python.shared.priority_queue import PriorityQueue, calculate_priority

@pytest.fixture
def queue():
    return PriorityQueue(redis_url="redis://test")

@pytest.mark.asyncio
async def test_connect(queue):
    mock_redis = MagicMock()
    with patch("aioredis.from_url", new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
        await queue.connect()
        mock_from_url.assert_called_once_with(queue.redis_url, decode_responses=True)
        assert queue.redis is mock_redis

@pytest.mark.asyncio
async def test_enqueue_dequeue(queue):
    queue.redis = AsyncMock()
    queue.redis.zcard.return_value = 0
    queue.redis.zrange.return_value = [(json.dumps({"id": 1}), 1e12 + 12345)]
    
    await queue.enqueue({"id": 1}, 1)
    queue.redis.zadd.assert_called_once()
    
    data, priority = await queue.dequeue()
    assert data == {"id": 1}
    assert priority == 1
    queue.redis.zrem.assert_called_once()

@pytest.mark.asyncio
async def test_enqueue_full_eviction(queue):
    queue.redis = AsyncMock()
    queue.redis.zcard.return_value = 100
    queue.redis.zrevrange.return_value = [("old_data", 3e12)]
    
    await queue.enqueue({"id": 2}, 1)
    queue.redis.zrem.assert_called_once_with(queue.QUEUE_KEY, "old_data")

@pytest.mark.asyncio
async def test_peek(queue):
    queue.redis = AsyncMock()
    queue.redis.zrangebyscore.return_value = [(json.dumps({"id": 1}), 1e12)]
    
    data, priority = await queue.peek()
    assert data == {"id": 1}
    assert priority == 1

@pytest.mark.asyncio
async def test_get_queue_lengths(queue):
    queue.redis = AsyncMock()
    queue.redis.zcount.side_effect = [10, 20, 30]
    queue.redis.zcard.return_value = 60
    
    lengths = await queue.get_queue_lengths()
    assert lengths["priority_1"] == 10
    assert lengths["total"] == 60

@pytest.mark.asyncio
async def test_clear(queue):
    queue.redis = AsyncMock()
    queue.redis.zcard.return_value = 5
    
    count = await queue.clear()
    assert count == 5
    queue.redis.delete.assert_called_once_with(queue.QUEUE_KEY)

@pytest.mark.asyncio
async def test_remove_item(queue):
    queue.redis = AsyncMock()
    queue.redis.zrem.return_value = 1
    
    result = await queue.remove_item({"id": 1})
    assert result is True

def test_calculate_priority():
    assert calculate_priority("complete") == 1
    assert calculate_priority("create", 40 * 1e9) == 2
    assert calculate_priority("create", 10 * 1e9) == 3
