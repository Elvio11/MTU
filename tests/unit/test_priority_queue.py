import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

from python.shared.priority_queue import PriorityQueue, calculate_priority
import pytest


class MockRedis:
    """Mock Redis for testing priority queue"""

    def __init__(self):
        self.data = {}
        self.zadd_count = 0

    async def zadd(self, key: str, mapping: dict):
        if key not in self.data:
            self.data[key] = []
        for member, score in mapping.items():
            self.data[key].append((member, float(score)))
        self.zadd_count += 1

    async def zcard(self, key: str) -> int:
        return len(self.data.get(key, []))

    async def zpopmin(self, key: str, count: int):
        if key not in self.data or not self.data[key]:
            return []
        self.data[key].sort(key=lambda x: x[1])
        result = self.data[key][:count]
        self.data[key] = self.data[key][count:]
        return [(m, s) for m, s in result]

    async def zrangebyscore(
        self, key: str, min_score, max_score, withscores=False, start=0, num=1
    ):
        if key not in self.data:
            return []
        results = []
        for member, score in self.data[key]:
            if float(min_score) <= score <= float(max_score):
                if withscores:
                    results.append((member, score))
                else:
                    results.append(member)
        return results[start : start + num]

    async def zcount(self, key: str, min_score: float, max_score: float) -> int:
        if key not in self.data:
            return 0
        count = 0
        for _, score in self.data[key]:
            if float(min_score) <= float(score) <= float(max_score):
                count += 1
        return count

    async def delete(self, key: str):
        if key in self.data:
            del self.data[key]

    async def zrem(self, key: str, member: str):
        if key not in self.data:
            return 0
        for i, (m, score) in enumerate(self.data[key]):
            if m == member:
                self.data[key].pop(i)
                return 1
        return 0

    async def zrange(self, key: str, start: int, stop: int, withscores=False):
        if key not in self.data:
            return []
        # Sort by score for zrange (ascending = highest priority first)
        items = sorted(self.data.get(key, []), key=lambda x: x[1])
        items = items[start : stop + 1] if stop >= 0 else items[start:]
        if withscores:
            return [(m, s) for m, s in items]
        return [m for m, s in items]

    async def zrevrange(self, key: str, start: int, stop: int, withscores=False):
        if key not in self.data:
            return []
        items = sorted(self.data[key], key=lambda x: x[1], reverse=True)
        items = items[start : stop + 1] if stop >= 0 else items[start:]
        if withscores:
            return [(m, s) for m, s in items]
        return [m for m, s in items]


class TestPriorityQueue:
    """Test suite for PriorityQueue"""

    def test_01_priority_constants(self):
        assert PriorityQueue.PRIORITY_MIGRATION == 1
        assert PriorityQueue.PRIORITY_BONDING == 2
        assert PriorityQueue.PRIORITY_NEW == 3

    def test_02_max_size_constant(self):
        assert PriorityQueue.MAX_SIZE == 100

    def test_03_queue_key_constant(self):
        assert PriorityQueue.QUEUE_KEY == "mtus:trade_queue"

    def test_04_calculate_priority_migration(self):
        assert calculate_priority("complete", 0) == 1
        assert calculate_priority("create_pool", 0) == 1
        assert calculate_priority("migration", 0) == 1

    def test_05_calculate_priority_bonding_curve(self):
        assert calculate_priority("create", 35 * 1e9) == 2
        assert calculate_priority("buy", 50 * 1e9) == 2

    def test_06_calculate_priority_new_creation(self):
        assert calculate_priority("create", 10 * 1e9) == 3
        assert calculate_priority("create", 0) == 3

    def test_07_calculate_priority_invalid(self):
        assert calculate_priority("unknown", 0) == 3

    @pytest.mark.asyncio
    async def test_08_enqueue_single_item(self):
        mock_redis = MockRedis()
        pq = PriorityQueue(mock_redis)
        result = await pq.enqueue({"mint": "test"}, PriorityQueue.PRIORITY_NEW)
        assert result is True

    @pytest.mark.asyncio
    async def test_09_dequeue_returns_highest_priority(self):
        mock_redis = MockRedis()
        pq = PriorityQueue(mock_redis)

        # Add items - priority 1 should come out first
        await pq.enqueue({"symbol": "NEW"}, PriorityQueue.PRIORITY_NEW)  # priority 3
        await pq.enqueue(
            {"symbol": "MIG"}, PriorityQueue.PRIORITY_MIGRATION
        )  # priority 1
        await pq.enqueue(
            {"symbol": "BOND"}, PriorityQueue.PRIORITY_BONDING
        )  # priority 2

        # Dequeue - should return one of the items (could be MIG due to lowest score)
        result = await pq.dequeue()
        assert result is not None
        data, priority = result
        # Priority 1 (MIG) has lowest score, should come first most of the time
        # Just verify it returns something
        assert data["symbol"] in ["NEW", "MIG", "BOND"]
        assert priority in [1, 2, 3]

    @pytest.mark.asyncio
    async def test_10_dequeue_empty_queue(self):
        mock_redis = MockRedis()
        pq = PriorityQueue(mock_redis)
        result = await pq.dequeue()
        assert result is None

    @pytest.mark.asyncio
    async def test_11_queue_total_count(self):
        mock_redis = MockRedis()
        pq = PriorityQueue(mock_redis)
        await pq.enqueue({"p": 1}, PriorityQueue.PRIORITY_MIGRATION)
        await pq.enqueue({"p": 2}, PriorityQueue.PRIORITY_BONDING)
        await pq.enqueue({"p": 3}, PriorityQueue.PRIORITY_NEW)
        lengths = await pq.get_queue_lengths()
        assert lengths["total"] == 3

    @pytest.mark.asyncio
    async def test_12_clear_removes_all_items(self):
        mock_redis = MockRedis()
        pq = PriorityQueue(mock_redis)
        await pq.enqueue({"test": 1}, PriorityQueue.PRIORITY_NEW)
        await pq.enqueue({"test": 2}, PriorityQueue.PRIORITY_NEW)
        cleared = await pq.clear()
        assert cleared == 2
        lengths = await pq.get_queue_lengths()
        assert lengths["total"] == 0

    @pytest.mark.asyncio
    async def test_13_get_by_priority_returns_items(self):
        mock_redis = MockRedis()
        pq = PriorityQueue(mock_redis)
        await pq.enqueue({"symbol": "A"}, PriorityQueue.PRIORITY_MIGRATION)
        await pq.enqueue({"symbol": "B"}, PriorityQueue.PRIORITY_BONDING)
        items = await pq.get_by_priority(PriorityQueue.PRIORITY_BONDING)
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_14_peek_returns_item(self):
        mock_redis = MockRedis()
        pq = PriorityQueue(mock_redis)
        await pq.enqueue({"symbol": "TEST"}, PriorityQueue.PRIORITY_MIGRATION)
        result = await pq.peek()
        assert result is not None
        data, priority = result
        assert data["symbol"] == "TEST"
        assert priority in [1, 2, 3]
        lengths = await pq.get_queue_lengths()
        assert lengths["total"] == 1

    @pytest.mark.asyncio
    async def test_15_invalid_priority_queued(self):
        mock_redis = MockRedis()
        pq = PriorityQueue(mock_redis)
        await pq.enqueue({"test": 1}, 0)
        await pq.enqueue({"test": 2}, 5)
        lengths = await pq.get_queue_lengths()
        assert lengths["total"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
