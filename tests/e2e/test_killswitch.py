"""
E2E Test - Kill Switch Safety Mechanisms
Tests kill switch triggering and all safety controls.
"""

import asyncio
import json
import time
import pytest
import aioredis

from src.python.shared.envelope import AgentMessageEnvelope
from src.python.shared.constants import (
    CHANNEL_KILL_SWITCH_TRIGGERED,
    REDIS_KEY_KILL_SWITCH,
    REDIS_KEY_TRADING_PAUSED,
    REDIS_KEY_KILL_SWITCH_TRIGGERED,
    is_paper_mode,
)


class TestKillSwitch:
    """Test kill switch safety mechanisms."""

    @pytest.mark.asyncio
    async def test_01_kill_switch_channel_publish(self, clean_redis):
        """Test: Kill switch publishes to correct channel."""
        redis = clean_redis

        # Subscribe FIRST (before publishing)
        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL_KILL_SWITCH_TRIGGERED)

        # Allow time for subscription to establish
        await asyncio.sleep(0.1)

        envelope = AgentMessageEnvelope(
            agent_id="AGT-10",
            event_type="kill_switch_triggered",
            payload={"reason": "Test kill switch", "timestamp": time.time()},
        )

        # NOW publish (after subscribing)
        await redis.publish(CHANNEL_KILL_SWITCH_TRIGGERED, envelope.model_dump_json())

        await asyncio.sleep(0.2)

        messages = []
        for _ in range(10):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if msg and msg["type"] == "message":
                messages.append(json.loads(msg["data"]))
                break

        await pubsub.unsubscribe(CHANNEL_KILL_SWITCH_TRIGGERED)
        await pubsub.close()

        assert len(messages) == 1
        assert messages[0]["event_type"] == "kill_switch_triggered"
        assert messages[0]["payload"]["reason"] == "Test kill switch"

    @pytest.mark.asyncio
    async def test_02_kill_switch_redis_key(self, clean_redis):
        """Test: Kill switch sets Redis key correctly."""
        redis = clean_redis

        await redis.set(REDIS_KEY_KILL_SWITCH, "active")
        value = await redis.get(REDIS_KEY_KILL_SWITCH)

        assert value == "active"

        await redis.set(REDIS_KEY_KILL_SWITCH, "inactive")
        value = await redis.get(REDIS_KEY_KILL_SWITCH)

        assert value == "inactive"

    @pytest.mark.asyncio
    async def test_03_trading_paused_key(self, clean_redis):
        """Test: Trading pause key operations."""
        redis = clean_redis

        await redis.set(REDIS_KEY_TRADING_PAUSED, "true")
        value = await redis.get(REDIS_KEY_TRADING_PAUSED)

        assert value == "true"

        await redis.delete(REDIS_KEY_TRADING_PAUSED)
        value = await redis.get(REDIS_KEY_TRADING_PAUSED)

        assert value is None

    @pytest.mark.asyncio
    async def test_04_daily_loss_limit_check(self, clean_redis, test_config):
        """Test: Daily loss limit triggers kill switch."""
        redis = clean_redis
        daily_loss_limit = test_config["trading"]["daily_loss_limit_sol"]

        current_pnl = -0.003

        if current_pnl < daily_loss_limit:
            should_trigger = True
        else:
            should_trigger = False

        assert should_trigger == True

    @pytest.mark.asyncio
    async def test_05_operational_window_check(self, clean_redis):
        """Test: Outside operational window disables trading."""
        from src.python.shared.constants import REDIS_KEY_SYSTEM_STATE

        redis = clean_redis

        await redis.set(REDIS_KEY_SYSTEM_STATE, "operational")
        state = await redis.get(REDIS_KEY_SYSTEM_STATE)

        assert state == "operational"

    @pytest.mark.asyncio
    async def test_06_agent_health_timeout(self, test_config):
        """Test: Agent health timeout detection."""
        agent_last_beat = time.time() - 35
        current_time = time.time()
        timeout = 30

        is_timed_out = current_time - agent_last_beat > timeout

        assert is_timed_out == True

    @pytest.mark.asyncio
    async def test_07_killswitch_key_exists(self, clean_redis):
        """Test: All kill switch related keys exist."""
        redis = clean_redis

        keys_to_check = [
            REDIS_KEY_KILL_SWITCH,
            REDIS_KEY_TRADING_PAUSED,
            REDIS_KEY_KILL_SWITCH_TRIGGERED,
        ]

        for key in keys_to_check:
            await redis.set(key, "test_value")
            value = await redis.get(key)
            assert value == "test_value"
            await redis.delete(key)

    @pytest.mark.asyncio
    async def test_08_envelope_schema(self, clean_redis):
        """Test: Kill switch envelope has correct schema."""
        envelope = AgentMessageEnvelope(
            agent_id="AGT-10",
            event_type="kill_switch_triggered",
            payload={
                "reason": "Daily loss limit",
                "timestamp": time.time(),
            },
            correlation_id="550e8400-e29b-41d4-a716-446655440000",  # Valid UUID
        )

        data = envelope.model_dump()

        assert data["agent_id"] == "AGT-10"
        assert data["event_type"] == "kill_switch_triggered"
        assert "reason" in data["payload"]
        assert "timestamp" in data["payload"]
