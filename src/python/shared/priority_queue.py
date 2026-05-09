import json
import time
from typing import Optional, Tuple
import aioredis


class PriorityQueue:
    """Priority queue using Redis Sorted Set for trade queue management.

    Priority Levels:
        1: Migration events (highest priority)
        2: Bonding curve + volume
        3: New creations (lowest priority)

    Score calculation: priority * 1e12 + timestamp (milliseconds)
    Lower score = higher priority
    """

    QUEUE_KEY = "mtus:trade_queue"
    MAX_SIZE = 100

    PRIORITY_MIGRATION = 1  # Highest - migrating tokens to pumpswap
    PRIORITY_BONDING = 2  # Medium - tokens on bonding curve with volume
    PRIORITY_NEW = 3  # Lowest - new token creations

    def __init__(
        self, redis: aioredis.Redis = None, redis_url: str = "redis://localhost:6379"
    ):
        self.redis = redis
        self.redis_url = redis_url

    async def connect(self) -> None:
        if self.redis is None:
            self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)

    async def enqueue(self, data: dict, priority: int) -> bool:
        """Add item to queue with priority.

        Args:
            data: Token data dict to be queued
            priority: Priority level (1=highest, 3=lowest)

        Returns:
            True if queued successfully, False if queue is full
        """
        if self.redis is None:
            await self.connect()

        if not (1 <= priority <= 3):
            priority = self.PRIORITY_NEW  # Default to lowest priority

        # Check current size
        size = await self.redis.zcard(self.QUEUE_KEY)

        # If queue full, remove lowest priority item (highest score)
        # Priority 3 (new tokens) has highest score, should be evicted first
        if size >= self.MAX_SIZE:
            highest = await self.redis.zrevrange(self.QUEUE_KEY, 0, 0, withscores=True)
            if highest:
                await self.redis.zrem(self.QUEUE_KEY, highest[0][0])

        # Calculate score: priority * 1e12 + timestamp (for FIFO within priority)
        timestamp = int(time.time() * 1000)
        score = float(priority) * 1e12 + timestamp

        await self.redis.zadd(self.QUEUE_KEY, {json.dumps(data): score})
        return True

    async def dequeue(self) -> Optional[Tuple[dict, int]]:
        """Remove and return highest priority item.

        Returns:
            Tuple of (data_dict, priority) or None if queue is empty
        """
        if self.redis is None:
            await self.connect()

        # Get highest priority (lowest score) item
        # Use zrange + zrem for compatibility with Redis 3.x (zpopmin requires Redis 5.0+)
        items = await self.redis.zrange(self.QUEUE_KEY, 0, 0, withscores=True)

        if not items:
            return None

        data_str, score = items[0]
        priority = int(score / 1e12)  # Extract priority from score

        # Remove the item after reading
        await self.redis.zrem(self.QUEUE_KEY, data_str)

        return json.loads(data_str), priority

    async def peek(self) -> Optional[Tuple[dict, int]]:
        """Peek at highest priority item without removing."""
        if self.redis is None:
            await self.connect()

        items = await self.redis.zrangebyscore(
            self.QUEUE_KEY, "-inf", "+inf", withscores=True, start=0, num=1
        )

        if not items:
            return None

        data_str, score = items[0]
        priority = int(score / 1e12)

        return json.loads(data_str), priority

    async def get_queue_lengths(self) -> dict:
        """Get queue lengths per priority level.

        Returns:
            Dict with priority counts and total
        """
        if self.redis is None:
            await self.connect()

        lengths = {}
        for priority in [1, 2, 3]:
            min_score = priority * 1e12
            max_score = (priority + 1) * 1e12 - 1
            count = await self.redis.zcount(self.QUEUE_KEY, min_score, max_score)
            lengths[f"priority_{priority}"] = count

        lengths["total"] = await self.redis.zcard(self.QUEUE_KEY)
        return lengths

    async def get_by_priority(self, priority: int) -> list:
        """Get all items at specific priority level without removing."""
        if self.redis is None:
            await self.connect()

        if not (1 <= priority <= 3):
            return []

        min_score = priority * 1e12
        max_score = (priority + 1) * 1e12 - 1

        items = await self.redis.zrangebyscore(self.QUEUE_KEY, min_score, max_score)

        return [json.loads(item) for item in items]

    async def clear(self) -> int:
        """Clear the entire queue.

        Returns:
            Number of items removed
        """
        if self.redis is None:
            await self.connect()

        size = await self.redis.zcard(self.QUEUE_KEY)
        await self.redis.delete(self.QUEUE_KEY)
        return size

    async def remove_item(self, data: dict) -> bool:
        """Remove specific item from queue.

        Returns:
            True if removed, False if not found
        """
        if self.redis is None:
            await self.connect()

        result = await self.redis.zrem(self.QUEUE_KEY, json.dumps(data))
        return result > 0


def calculate_priority(tx_type: str, v_sol_in_bonding_curve: int = 0) -> int:
    """Calculate priority based on token characteristics.

    Args:
        tx_type: Transaction type (create, complete, create_pool, etc.)
        v_sol_in_bonding_curve: Virtual SOL in bonding curve (in lamports)

    Returns:
        Priority level (1=highest, 3=lowest)
    """
    # Priority 1: Migration events
    if tx_type in ("complete", "create_pool", "migration"):
        return PriorityQueue.PRIORITY_MIGRATION

    # Priority 2: Bonding curve with significant progress (>= 35 SOL)
    # Note: Pump.fun tokens start at ~30 SOL virtual liquidity, so we use 35 as the 'active' threshold
    v_sol = v_sol_in_bonding_curve / 1e9 if v_sol_in_bonding_curve > 0 else 0
    if v_sol >= 35:
        return PriorityQueue.PRIORITY_BONDING

    # Priority 3: New creations (default)
    return PriorityQueue.PRIORITY_NEW
