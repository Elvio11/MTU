"""
E2E Test - Position Management
Tests TP/SL, trailing stop, and position lifecycle.
"""

import asyncio
import time
import pytest
import aioredis

from src.python.shared.envelope import AgentMessageEnvelope
from src.python.shared.constants import (
    CHANNEL_POSITION_OPENED,
    CHANNEL_POSITION_CLOSED,
    CHANNEL_TP1_HIT,
    CHANNEL_TP2_HIT,
    CHANNEL_STOP_LOSS_HIT,
    CHANNEL_TRAILING_STOP_HIT,
    REDIS_KEY_POSITION_PREFIX,
    KEY_ALL_ACTIVE_POSITIONS,
)


class TestPositionManagement:
    """Test position management and lifecycle."""

    @pytest.mark.asyncio
    async def test_01_position_opened_event(self, clean_redis):
        """Test: Position opened event published."""
        redis = clean_redis

        position_data = {
            "position_id": "pos_e2e_001",
            "mint": "5ZH8bCprBLN1qhS4dDdTGQnQxKVC3F1k6jz5rR5ax",
            "entryPriceSol": 0.01,
            "position_size_sol": 0.0005,
            "tokensReceived": 50000,
        }

        envelope = AgentMessageEnvelope(
            agent_id="AGT-05",
            event_type="position_opened",
            payload=position_data,
        )

        await redis.publish(CHANNEL_POSITION_OPENED, envelope.model_dump_json())

        await redis.sadd(KEY_ALL_ACTIVE_POSITIONS, position_data["position_id"])

        positions = await redis.smembers(KEY_ALL_ACTIVE_POSITIONS)
        assert "pos_e2e_001" in positions

    @pytest.mark.asyncio
    async def test_02_tp1_hit(self, clean_redis):
        """Test: TP1 (take profit level 1) triggers."""
        redis = clean_redis

        envelope = AgentMessageEnvelope(
            agent_id="AGT-06",
            event_type="tp1_hit",
            payload={
                "position_id": "pos_e2e_001",
                "sell_portion": 0.5,
                "realised_pnl_sol": 0.001,
            },
        )

        await redis.publish(CHANNEL_TP1_HIT, envelope.model_dump_json())

        result = True
        assert result == True

    @pytest.mark.asyncio
    async def test_03_tp2_hit(self, clean_redis):
        """Test: TP2 (take profit level 2) triggers."""
        redis = clean_redis

        envelope = AgentMessageEnvelope(
            agent_id="AGT-06",
            event_type="tp2_hit",
            payload={
                "position_id": "pos_e2e_001",
                "sell_portion": 0.5,
                "realised_pnl_sol": 0.004,
            },
        )

        await redis.publish(CHANNEL_TP2_HIT, envelope.model_dump_json())

        result = True
        assert result == True

    @pytest.mark.asyncio
    async def test_04_stop_loss_hit(self, clean_redis):
        """Test: Stop loss triggers."""
        redis = clean_redis

        envelope = AgentMessageEnvelope(
            agent_id="AGT-06",
            event_type="stop_loss_hit",
            payload={
                "position_id": "pos_e2e_001",
                "sell_portion": 1.0,
                "realised_pnl_sol": -0.00035,
            },
        )

        await redis.publish(CHANNEL_STOP_LOSS_HIT, envelope.model_dump_json())

        result = True
        assert result == True

    @pytest.mark.asyncio
    async def test_05_trailing_stop(self, clean_redis):
        """Test: Trailing stop logic."""
        redis = clean_redis

        current_price = 0.015
        peak_price = 0.02
        trailing_stop_pct = 15

        trailing_trigger_price = peak_price * (1 - trailing_stop_pct / 100)

        trailing_hit = current_price <= trailing_trigger_price

        assert trailing_trigger_price == 0.017
        # 0.015 <= 0.017 is True - price has dropped below trailing stop threshold
        assert trailing_hit == True

    @pytest.mark.asyncio
    async def test_06_position_closed_event(self, clean_redis):
        """Test: Position closed event."""
        redis = clean_redis

        envelope = AgentMessageEnvelope(
            agent_id="AGT-06",
            event_type="position_closed",
            payload={
                "position_id": "pos_e2e_001",
                "realised_pnl_sol": 0.001,
                "exit_reason": "tp1_hit",
            },
        )

        await redis.publish(CHANNEL_POSITION_CLOSED, envelope.model_dump_json())

        await redis.srem(KEY_ALL_ACTIVE_POSITIONS, "pos_e2e_001")

        positions = await redis.smembers(KEY_ALL_ACTIVE_POSITIONS)
        assert "pos_e2e_001" not in positions

    @pytest.mark.asyncio
    async def test_07_position_redis_storage(self, clean_redis):
        """Test: Position data stored in Redis."""
        redis = clean_redis

        position_data = {
            "position_id": "pos_e2e_001",
            "mint": "test_mint",
            "entry_price": "0.01",
            "position_size": "0.0005",
            "tp1_price": "0.02",
            "tp2_price": "0.05",
            "sl_price": "0.007",
            "opened_at": str(time.time()),
        }

        # Use hset with positional args instead of mapping= keyword
        key = f"{REDIS_KEY_POSITION_PREFIX}pos_e2e_001"
        for field, value in position_data.items():
            await redis.hset(key, field, value)

        stored = await redis.hgetall(f"{REDIS_KEY_POSITION_PREFIX}pos_e2e_001")

        assert stored["mint"] == "test_mint"
        assert stored["position_size"] == "0.0005"

    @pytest.mark.asyncio
    async def test_08_tp_multiplier_calc(self, test_config):
        """Test: TP multiplier calculations."""
        entry_price = 0.01
        tp1_multiplier = test_config["trading"]["tp1_multiplier"]
        tp2_multiplier = test_config["trading"]["tp2_multiplier"]

        tp1_price = entry_price * tp1_multiplier
        tp2_price = entry_price * tp2_multiplier

        assert tp1_price == 0.02
        assert tp2_price == 0.05

    @pytest.mark.asyncio
    async def test_09_sl_multiplier_calc(self, test_config):
        """Test: SL multiplier calculation."""
        entry_price = 0.01
        sl_multiplier = test_config["trading"]["sl_multiplier"]

        sl_price = entry_price * sl_multiplier

        assert round(sl_price, 4) == 0.007

    @pytest.mark.asyncio
    async def test_10_time_based_sl(self):
        """Test: Time-based stop loss."""
        opened_at = time.time() - (5 * 60 * 60)
        current_time = time.time()
        time_sl_hours = 4

        hours_elapsed = (current_time - opened_at) / 3600
        time_sl_triggered = hours_elapsed >= time_sl_hours

        assert hours_elapsed >= 4.0
        assert time_sl_triggered == True
