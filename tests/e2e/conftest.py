"""
E2E Test Configuration - Shared fixtures for end-to-end tests.
"""

import os
import sys
import pytest
import aioredis
from pytest_asyncio import fixture

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)


@fixture
async def redis_client():
    """Provide a Redis client for e2e tests."""
    redis = await aioredis.from_url("redis://localhost:6379", decode_responses=True)
    yield redis
    await redis.close()


@fixture
async def clean_redis(redis_client):
    """Clean Redis keys before each test."""
    redis = redis_client
    keys = []
    async for key in redis.scan_iter("mtus:*"):
        keys.append(key)
    if keys:
        await redis.delete(*keys)
    yield redis


@fixture
def test_config():
    """Provide test configuration."""
    return {
        "system": {
            "trading_active": True,
            "environment": "paper",
        },
        "trading": {
            "position_size_sol": 0.0005,
            "max_simultaneous_positions": 1,
            "max_trades_per_hour": 3,
            "daily_loss_limit_sol": 0.002,
            "tp1_multiplier": 2.0,
            "tp2_multiplier": 5.0,
            "sl_multiplier": 0.7,
        },
        "qualification": {
            "max_market_cap_sol": 150,
            "min_market_cap_sol": 5,
        },
    }


@fixture
def paper_mode():
    """Ensure paper mode is set for tests."""
    original = os.getenv("MTUS_ENVIRONMENT")
    os.environ["MTUS_ENVIRONMENT"] = "paper"
    yield
    if original:
        os.environ["MTUS_ENVIRONMENT"] = original
    else:
        os.environ.pop("MTUS_ENVIRONMENT", None)
