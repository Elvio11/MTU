import time
from collections import deque
from typing import Optional
import aioredis
import json


class RateLimiter:
    """Rate limiter for trading operations"""

    def __init__(
        self,
        max_trades_per_hour: int = 10,
        max_concurrent_positions: int = 3,
        redis_url: str = "redis://localhost:6379",
    ):
        self.max_trades_per_hour = max_trades_per_hour
        self.max_concurrent_positions = max_concurrent_positions
        self.redis_url = redis_url
        self.redis: Optional[aioredis.Redis] = None
        self.trade_times: deque = deque()

    async def connect(self):
        self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)

    async def can_trade(self) -> tuple[bool, str]:
        """Check if a new trade is allowed"""
        if not self.redis:
            await self.connect()

        current_time = time.time()

        # Check concurrent positions
        positions_key = "mtus:active_positions"
        active_positions = await self.redis.scard(positions_key)

        if active_positions >= self.max_concurrent_positions:
            return (
                False,
                f"Max concurrent positions ({self.max_concurrent_positions}) reached",
            )

        # Check hourly rate limit
        trade_count_key = "mtus:trade_count"
        current_hour = int(current_time // 3600)

        # Get trade count for current hour
        count = await self.redis.get(f"{trade_count_key}:{current_hour}")
        trade_count = int(count) if count else 0

        if trade_count >= self.max_trades_per_hour:
            return False, f"Max trades per hour ({self.max_trades_per_hour}) reached"

        return True, "OK"

    async def record_trade(self) -> None:
        """Record a trade for rate limiting"""
        if not self.redis:
            await self.connect()

        current_time = time.time()
        current_hour = int(current_time // 3600)

        # Increment trade count
        trade_count_key = "mtus:trade_count"
        await self.redis.incr(f"{trade_count_key}:{current_hour}")

        # Set expiry for old keys (keep for 2 hours)
        old_hour = current_hour - 2
        await self.redis.delete(f"{trade_count_key}:{old_hour}")

    async def add_position(self, position_id: str) -> None:
        """Add an active position"""
        if not self.redis:
            await self.connect()

        positions_key = "mtus:active_positions"
        await self.redis.sadd(positions_key, position_id)

    async def remove_position(self, position_id: str) -> None:
        """Remove an active position"""
        if not self.redis:
            await self.connect()

        positions_key = "mtus:active_positions"
        await self.redis.srem(positions_key, position_id)

    async def get_status(self) -> dict:
        """Get current rate limiter status"""
        if not self.redis:
            await self.connect()

        current_time = time.time()
        current_hour = int(current_time // 3600)

        positions_key = "mtus:active_positions"
        active_positions = await self.redis.scard(positions_key)

        trade_count_key = "mtus:trade_count"
        count = await self.redis.get(f"{trade_count_key}:{current_hour}")
        trade_count = int(count) if count else 0

        return {
            "active_positions": active_positions,
            "max_positions": self.max_concurrent_positions,
            "trades_this_hour": trade_count,
            "max_trades_per_hour": self.max_trades_per_hour,
            "can_trade": active_positions < self.max_concurrent_positions
            and trade_count < self.max_trades_per_hour,
        }

    async def close(self):
        if self.redis:
            await self.redis.close()
