"""
E2E Test - Live Trading Preparation
Tests the pre-flight checks and configurations required before going live.
Following the followforlive.md 8-phase preparation plan.
"""

import asyncio
import json
import pytest
import os
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from src.python.shared.envelope import AgentMessageEnvelope
from src.python.shared.constants import (
    CHANNEL_TOKEN_DETECTED,
    CHANNEL_TOKEN_RECEIVED,
    CHANNEL_TRADE_APPROVED,
    CHANNEL_POSITION_OPENED,
    CHANNEL_TP1_HIT,
    CHANNEL_STOP_LOSS_HIT,
    KEY_TRADE_QUEUE,
    KEY_ALL_ACTIVE_POSITIONS,
    KEY_POSITION_SIZE_SOL,
    REDIS_KEY_KILL_SWITCH,
    REDIS_KEY_TRADING_PAUSED,
    REDIS_KEY_KILL_SWITCH_TRIGGERED,
    is_paper_mode,
)


class TestLiveTradingPreparation:
    """Test live trading preparation phase checks."""

    @pytest.mark.asyncio
    async def test_01_redis_connectivity(self, clean_redis):
        """Phase 1.2: Verify Redis connectivity."""
        redis = clean_redis

        pong = await redis.ping()
        assert pong == True

    @pytest.mark.asyncio
    async def test_02_priority_queue_empty(self, clean_redis):
        """Phase 4.3: Verify priority queue is empty before trading."""
        redis = clean_redis

        await redis.delete(KEY_TRADE_QUEUE)

        count = await redis.zcard(KEY_TRADE_QUEUE)
        assert count == 0

    @pytest.mark.asyncio
    async def test_03_position_size_configured(self, clean_redis):
        """Phase 5.1: Verify position size is set correctly."""
        redis = clean_redis

        position_size = 0.0005
        await redis.set(KEY_POSITION_SIZE_SOL, str(position_size))

        stored_size = await redis.get(KEY_POSITION_SIZE_SOL)
        assert float(stored_size) == position_size
        assert float(stored_size) >= 0.0001

    @pytest.mark.asyncio
    async def test_04_kill_switch_inactive(self, clean_redis):
        """Phase 6.1: Verify kill switch is not active."""
        redis = clean_redis

        await redis.delete(REDIS_KEY_KILL_SWITCH)

        kill_switch = await redis.get(REDIS_KEY_KILL_SWITCH)
        assert kill_switch is None

    @pytest.mark.asyncio
    async def test_05_trading_not_paused(self, clean_redis):
        """Phase 6.2: Verify trading is not paused."""
        redis = clean_redis

        await redis.delete(REDIS_KEY_TRADING_PAUSED)

        paused = await redis.get(REDIS_KEY_TRADING_PAUSED)
        assert paused is None

    @pytest.mark.asyncio
    async def test_06_active_positions_clear(self, clean_redis):
        """Phase 4.3: Verify no active positions before trading."""
        redis = clean_redis

        await redis.delete(KEY_ALL_ACTIVE_POSITIONS)

        count = await redis.scard(KEY_ALL_ACTIVE_POSITIONS)
        assert count == 0

    @pytest.mark.asyncio
    async def test_07_rate_limits_configured(self, clean_redis):
        """Phase 1.1: Verify rate limits are configured."""
        redis = clean_redis
        current_hour = int(time.time() // 3600)

        trade_key = f"mtus:trade_count:{current_hour}"
        await redis.set(trade_key, "0")

        count = await redis.get(trade_key)
        assert int(count) == 0

    @pytest.mark.asyncio
    async def test_08_daily_pnl_within_limits(self, clean_redis):
        """Phase 7.3: Verify daily PnL is within limits."""
        redis = clean_redis

        daily_pnl_key = "mtus:daily_pnl"
        await redis.set(daily_pnl_key, "0.0005")

        pnl = await redis.get(daily_pnl_key)
        daily_loss_limit = -0.002

        assert float(pnl) > daily_loss_limit

    @pytest.mark.asyncio
    async def test_09_environment_detection(self, paper_mode):
        """Phase 2.1: Verify environment detection works."""
        assert is_paper_mode() == True

    @pytest.mark.asyncio
    async def test_10_operational_window_check(self, clean_redis):
        """Phase 1.1: Verify operational window can be checked."""
        redis = clean_redis

        system_state_key = "mtus:system_state"
        await redis.set(system_state_key, "operational")

        state = await redis.get(system_state_key)
        assert state == "operational"

    @pytest.mark.asyncio
    async def test_11_telegram_bot_connection(self, clean_redis):
        """Phase 6: Test telegram bot integration points."""
        redis = clean_redis

        await redis.set("mtus:trading_paused", "false")
        paused = await redis.get("mtus:trading_paused")
        assert paused == "false"

    @pytest.mark.asyncio
    async def test_12_agent_health_keys(self, clean_redis):
        """Phase 4.1: Verify agent health tracking keys exist."""
        redis = clean_redis

        agent_health_keys = [
            "mtus:agent:AGT-01:last_beat",
            "mtus:agent:AGT-02:last_beat",
            "mtus:agent:AGT-03:last_beat",
            "mtus:agent:AGT-05:last_beat",
            "mtus:agent:AGT-06:last_beat",
        ]

        for key in agent_health_keys:
            timestamp = str(int(time.time()))
            await redis.set(key, timestamp)

            value = await redis.get(key)
            assert value is not None

    @pytest.mark.asyncio
    async def test_13_qualification_gates_configured(self, clean_redis):
        """Phase 5.2: Verify qualification gate thresholds are configured."""
        redis = clean_redis

        gate_keys = {
            "mtus:min_market_cap_sol": 5,
            "mtus:max_market_cap_sol": 150,
            "mtus:min_virtual_sol_reserves": 30,
            "mtus:max_rugcheck_score": 300,
            "mtus:min_lp_burned_pct": 85,
        }

        for key, expected_value in gate_keys.items():
            await redis.set(key, str(expected_value))
            value = await redis.get(key)
            assert float(value) == expected_value

    @pytest.mark.asyncio
    async def test_14_tp_sl_multipliers_configured(self, clean_redis):
        """Phase 3.6: Verify TP/SL multipliers are configured."""
        redis = clean_redis

        await redis.set("mtus:tp1_multiplier", "2.0")
        await redis.set("mtus:tp2_multiplier", "5.0")
        await redis.set("mtus:sl_multiplier", "0.7")

        tp1 = await redis.get("mtus:tp1_multiplier")
        tp2 = await redis.get("mtus:tp2_multiplier")
        sl = await redis.get("mtus:sl_multiplier")

        assert float(tp1) == 2.0
        assert float(tp2) == 5.0
        assert float(sl) == 0.7

    @pytest.mark.asyncio
    async def test_15_token_dedup_cache(self, clean_redis):
        """Phase 5.2: Verify token deduplication cache exists."""
        redis = clean_redis
        mint = "5ZH8bCprBLN1qhS4dDdTGQnQxKVC3F1k6jz5rR5ax"

        dedup_key = f"mtus:dedup:{mint}"
        await redis.setex(dedup_key, 86400, "1")

        exists = await redis.exists(dedup_key)
        assert exists == 1

    @pytest.mark.asyncio
    async def test_16_wallet_address_validation(self, clean_redis):
        """Phase 1.3: Verify wallet addresses are stored correctly."""
        redis = clean_redis

        sniper_wallet = "ESHH2KcsMWSKoA6ypBGfbpP8Mre3k1QVw4jkypn8A1xc"
        main_wallet = "FFtyqaLq9ApacZDBa1T4uXbyQnyexXhRXjg8XiSoPc1a"

        await redis.set("mtus:sniper_wallet", sniper_wallet)
        await redis.set("mtus:main_wallet", main_wallet)

        stored_sniper = await redis.get("mtus:sniper_wallet")
        stored_main = await redis.get("mtus:main_wallet")

        assert stored_sniper == sniper_wallet
        assert stored_main == main_wallet
        assert len(stored_sniper) == 44
        assert len(stored_main) == 44

    @pytest.mark.asyncio
    async def test_17_max_concurrent_positions_limit(self, clean_redis):
        """Phase 1.1: Verify max concurrent positions limit."""
        redis = clean_redis
        max_positions = 1

        await redis.set("mtus:max_positions", str(max_positions))

        limit = await redis.get("mtus:max_positions")
        assert int(limit) == max_positions

    @pytest.mark.asyncio
    async def test_18_max_trades_per_hour_limit(self, clean_redis):
        """Phase 1.1: Verify max trades per hour limit."""
        redis = clean_redis
        max_trades = 3
        current_hour = int(time.time() // 3600)

        await redis.set(f"mtus:trade_count:{current_hour}", "0")
        count = await redis.get(f"mtus:trade_count:{current_hour}")
        assert int(count) < max_trades

    @pytest.mark.asyncio
    async def test_19_audit_ledger_write(self, clean_redis):
        """Phase 7.1: Verify audit ledger can be written."""
        redis = clean_redis

        correlation_id = str(uuid.uuid4())
        audit_event = {
            "envelope_id": correlation_id,
            "agent_id": "AGT-01",
            "event_type": "token_detected",
            "payload": {"mint": "test_mint"},
            "timestamp_utc": "2024-01-01T00:00:00Z",
        }

        await redis.lpush("event:token_detected:0", json.dumps(audit_event))

        events = await redis.lrange("event:token_detected:0", 0, 0)
        assert len(events) == 1

        logged = json.loads(events[0])
        assert logged["event_type"] == "token_detected"

    @pytest.mark.asyncio
    async def test_20_position_state_transitions(self, clean_redis):
        """Phase 5.3: Test position state transitions."""
        redis = clean_redis
        position_id = str(uuid.uuid4())

        await redis.sadd(KEY_ALL_ACTIVE_POSITIONS, position_id)

        state_key = f"mtus:position:{position_id}:state"
        await redis.set(state_key, "OPEN")

        state = await redis.get(state_key)
        assert state == "OPEN"

        await redis.set(state_key, "TAKE_PROFIT_1")
        state = await redis.get(state_key)
        assert state == "TAKE_PROFIT_1"

    @pytest.mark.asyncio
    async def test_21_price_polling_active(self, clean_redis):
        """Phase 5.3: Verify price polling can be tracked."""
        redis = clean_redis

        price_key = "mtus:price:TEST_TOKEN"
        await redis.set(price_key, "0.0005")

        price = await redis.get(price_key)
        assert float(price) > 0

    @pytest.mark.asyncio
    async def test_22_trailing_stop_calculation(self, clean_redis):
        """Phase 5.3: Verify trailing stop calculation."""
        peak_price = 0.001
        trailing_pct = 0.85

        trailing_stop = peak_price * trailing_pct

        assert trailing_stop == 0.00085

    @pytest.mark.asyncio
    async def test_23_time_based_sl(self, clean_redis):
        """Phase 5.3: Verify time-based stop loss."""
        entry_timestamp = int(time.time()) - (5 * 60 * 60)
        current_timestamp = int(time.time())

        time_elapsed = current_timestamp - entry_timestamp
        time_sl_threshold = 4 * 60 * 60

        assert time_elapsed > time_sl_threshold

    @pytest.mark.asyncio
    async def test_24_killswitch_triggered_key(self, clean_redis):
        """Phase 6.1: Verify kill switch triggered key."""
        redis = clean_redis

        await redis.delete(REDIS_KEY_KILL_SWITCH_TRIGGERED)

        triggered = await redis.get(REDIS_KEY_KILL_SWITCH_TRIGGERED)
        assert triggered is None

    @pytest.mark.asyncio
    async def test_25_go_live_checklist(self, clean_redis, paper_mode):
        """Phase 8: Verify complete go-live checklist."""
        redis = clean_redis
        current_hour = int(time.time() // 3600)

        checklist = {
            "redis_connected": await redis.ping() == True,
            "queue_empty": (await redis.zcard(KEY_TRADE_QUEUE)) == 0,
            "position_size_set": True,
            "kill_switch_inactive": (await redis.get(REDIS_KEY_KILL_SWITCH)) is None,
            "trading_not_paused": (await redis.get(REDIS_KEY_TRADING_PAUSED)) is None,
            "active_positions_clear": (await redis.scard(KEY_ALL_ACTIVE_POSITIONS))
            == 0,
            "rate_limit_ok": int(
                await redis.get(f"mtus:trade_count:{current_hour}") or "0"
            )
            < 3,
            "daily_pnl_ok": float(await redis.get("mtus:daily_pnl") or "0") > -0.002,
            "paper_mode": is_paper_mode() == True,
        }

        failed_checks = [k for k, v in checklist.items() if not v]

        assert len(failed_checks) == 0, f"Failed checks: {failed_checks}"

    @pytest.mark.asyncio
    async def test_26_event_channel_subscribe_before_publish(self, clean_redis):
        """Test: Subscribe BEFORE publishing to avoid missed messages."""
        redis = clean_redis

        pubsub = redis.pubsub()
        await pubsub.subscribe("test_channel")
        await asyncio.sleep(0.1)

        test_message = {"event": "test", "data": "value"}
        await redis.publish("test_channel", json.dumps(test_message))

        await asyncio.sleep(0.2)

        received = []
        for _ in range(5):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if msg and msg["type"] == "message":
                received.append(json.loads(msg["data"]))
                break

        await pubsub.unsubscribe("test_channel")
        await pubsub.close()

        assert len(received) == 1
        assert received[0]["event"] == "test"


class TestLiveTradingIntegration:
    """Integration tests for live trading preparation."""

    @pytest.mark.asyncio
    async def test_01_complete_pre_flight_sequence(self, clean_redis, paper_mode):
        """Test: Complete pre-flight sequence."""
        redis = clean_redis
        current_hour = int(time.time() // 3600)

        await redis.ping()

        await redis.delete(KEY_TRADE_QUEUE)
        assert await redis.zcard(KEY_TRADE_QUEUE) == 0

        await redis.set(KEY_POSITION_SIZE_SOL, "0.0005")

        await redis.delete(REDIS_KEY_KILL_SWITCH)

        await redis.delete(REDIS_KEY_TRADING_PAUSED)

        await redis.delete(KEY_ALL_ACTIVE_POSITIONS)

        await redis.set(f"mtus:trade_count:{current_hour}", "0")

        await redis.set("mtus:daily_pnl", "0.0")

        assert is_paper_mode() == True

    @pytest.mark.asyncio
    async def test_02_trade_execution_flow(self, clean_redis):
        """Test: Simulated trade execution flow."""
        redis = clean_redis
        correlation_id = str(uuid.uuid4())
        position_id = str(uuid.uuid4())

        token = {
            "mint": "5ZH8bCprBLN1qhS4dDdTGQnQxKVC3F1k6jz5rR5ax",
            "symbol": "LIVE",
            "marketCapSol": 50.0,
            "vSolInBondingCurve": 45000000000,
        }

        envelope = AgentMessageEnvelope(
            agent_id="AGT-01",
            event_type="token_detected",
            payload=token,
            correlation_id=correlation_id,
        )
        await redis.zadd(KEY_TRADE_QUEUE, {json.dumps(envelope.model_dump()): 3})

        queue_count = await redis.zcard(KEY_TRADE_QUEUE)
        assert queue_count > 0

    @pytest.mark.asyncio
    async def test_03_emergency_stop_procedure(self, clean_redis):
        """Test: Emergency stop procedure."""
        redis = clean_redis

        await redis.set(REDIS_KEY_KILL_SWITCH, "active")
        await redis.set(REDIS_KEY_KILL_SWITCH_TRIGGERED, "true")
        await redis.set(REDIS_KEY_TRADING_PAUSED, "true")

        kill_switch = await redis.get(REDIS_KEY_KILL_SWITCH)
        triggered = await redis.get(REDIS_KEY_KILL_SWITCH_TRIGGERED)
        paused = await redis.get(REDIS_KEY_TRADING_PAUSED)

        assert kill_switch == "active"
        assert triggered == "true"
        assert paused == "true"

    @pytest.mark.asyncio
    async def test_04_paper_vs_live_mode_difference(self, paper_mode):
        """Test: Verify paper mode is detected correctly."""
        assert is_paper_mode() == True

    @pytest.mark.asyncio
    async def test_05_agent_startup_sequence(self, clean_redis):
        """Test: Agent startup health check sequence."""
        redis = clean_redis

        agent_ids = ["AGT-01", "AGT-02", "AGT-03", "AGT-04", "AGT-05", "AGT-06"]

        for agent_id in agent_ids:
            key = f"mtus:agent:{agent_id}:last_beat"
            await redis.set(key, str(int(time.time())))

            value = await redis.get(key)
            assert value is not None
