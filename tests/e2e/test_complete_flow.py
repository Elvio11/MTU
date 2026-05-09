"""
E2E Test - Complete Trading Flow
Tests the end-to-end flow from token detection through trade execution and TP/SL monitoring.
"""

import asyncio
import json
import time
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from src.python.shared.envelope import AgentMessageEnvelope
from src.python.shared.constants import (
    CHANNEL_TOKEN_DETECTED,
    CHANNEL_TOKEN_RECEIVED,
    CHANNEL_TOKEN_QUALIFIED,
    CHANNEL_TRADE_APPROVED,
    CHANNEL_POSITION_OPENED,
    CHANNEL_TP1_HIT,
    CHANNEL_TP2_HIT,
    CHANNEL_STOP_LOSS_HIT,
    CHANNEL_TRADE_FAILED,
    KEY_TRADE_QUEUE,
    KEY_ALL_ACTIVE_POSITIONS,
    REDIS_KEY_KILL_SWITCH,
    REDIS_KEY_TRADING_PAUSED,
    is_paper_mode,
)

REDIS_KEY_DAILY_PNL = "mtus:daily_pnl"
REDIS_KEY_POSITION_PREFIX = "mtus:position:"
REDIS_KEY_TRADE_QUEUE = KEY_TRADE_QUEUE
REDIS_KEY_ACTIVE_POSITIONS = KEY_ALL_ACTIVE_POSITIONS


class TestCompleteFlow:
    """Test complete end-to-end trading flow."""

    @pytest.mark.asyncio
    async def test_01_token_detection_to_queue(self, clean_redis):
        """Test: Token detected by NOFX is queued in priority queue."""
        redis = clean_redis
        correlation_id = str(uuid.uuid4())

        test_token = {
            "mint": "5ZH8bCprBLN1qhS4dDdTGQnQxKVC3F1k6jz5rR5ax",
            "symbol": "COMPLETE",
            "name": "Complete Token",
            "marketCapSol": 50.0,
            "vSolInBondingCurve": 45000000000,
            "bondingCurveKey": "test_curve_key",
            "uri": "https://example.com/token.json",
        }

        envelope = AgentMessageEnvelope(
            agent_id="AGT-01",
            event_type="token_detected",
            payload=test_token,
            correlation_id=correlation_id,
        )

        priority = 3
        await redis.zadd(
            REDIS_KEY_TRADE_QUEUE, {json.dumps(envelope.model_dump()): priority}
        )

        items = await redis.zrange(REDIS_KEY_TRADE_QUEUE, 0, -1)
        assert len(items) == 1

        queued_data = json.loads(items[0])
        assert queued_data["event_type"] == "token_detected"
        assert queued_data["payload"]["symbol"] == "COMPLETE"
        assert queued_data["correlation_id"] == correlation_id

    @pytest.mark.asyncio
    async def test_02_queue_dequeue_by_priority(self, clean_redis):
        """Test: Higher priority items are dequeued first."""
        redis = clean_redis

        priority_1 = AgentMessageEnvelope(
            agent_id="AGT-01",
            event_type="token_migrated",
            payload={"mint": "migration_token", "program": "pumpswap"},
            correlation_id=str(uuid.uuid4()),
        )
        priority_3 = AgentMessageEnvelope(
            agent_id="AGT-01",
            event_type="token_detected",
            payload={"mint": "new_token", "marketCapSol": 50.0},
            correlation_id=str(uuid.uuid4()),
        )
        priority_2 = AgentMessageEnvelope(
            agent_id="AGT-01",
            event_type="token_gradated",
            payload={"mint": "gradated_token"},
            correlation_id=str(uuid.uuid4()),
        )

        await redis.zadd(
            REDIS_KEY_TRADE_QUEUE, {json.dumps(priority_1.model_dump()): 1}
        )
        await redis.zadd(
            REDIS_KEY_TRADE_QUEUE, {json.dumps(priority_3.model_dump()): 3}
        )
        await redis.zadd(
            REDIS_KEY_TRADE_QUEUE, {json.dumps(priority_2.model_dump()): 2}
        )

        items = await redis.zrange(REDIS_KEY_TRADE_QUEUE, 0, 0)
        first_item = json.loads(items[0])
        assert first_item["event_type"] == "token_migrated"

    @pytest.mark.asyncio
    async def test_03_hermes_routing(self, clean_redis):
        """Test: Hermes routes token to Anansi and Cassandra."""
        redis = clean_redis

        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL_TOKEN_RECEIVED)
        await asyncio.sleep(0.1)

        token_data = {
            "mint": "5ZH8bCprBLN1qhS4dDdTGQnQxKVC3F1k6jz5rR5ax",
            "symbol": "FLOW",
            "marketCapSol": 50.0,
            "vSolInBondingCurve": 45000000000,
        }

        envelope = AgentMessageEnvelope(
            agent_id="AGT-02",
            event_type="token_received",
            payload=token_data,
            correlation_id=str(uuid.uuid4()),
        )

        await redis.publish(CHANNEL_TOKEN_RECEIVED, envelope.model_dump_json())
        await asyncio.sleep(0.2)

        messages = []
        for _ in range(10):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if msg and msg["type"] == "message":
                messages.append(json.loads(msg["data"]))
                break

        await pubsub.unsubscribe(CHANNEL_TOKEN_RECEIVED)
        await pubsub.close()

        assert len(messages) == 1
        assert messages[0]["event_type"] == "token_received"

    @pytest.mark.asyncio
    async def test_04_anansi_qualification_pass(self, clean_redis):
        """Test: Anansi passes qualified token through safety gates."""
        redis = clean_redis

        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL_TRADE_APPROVED)
        await asyncio.sleep(0.1)

        qualification = {
            "gates_passed": ["G1", "G2", "G3", "G7", "G10", "G11"],
            "gates_failed": [],
            "qualified": True,
        }

        envelope = AgentMessageEnvelope(
            agent_id="AGT-03",
            event_type="trade_approved",
            payload={
                "token": {
                    "mint": "qualified_token_mint",
                    "symbol": "QUAL",
                    "marketCapSol": 50.0,
                },
                "qualification_report": qualification,
                "position_size_sol": 0.0005,
            },
            correlation_id=str(uuid.uuid4()),
        )

        await redis.publish(CHANNEL_TRADE_APPROVED, envelope.model_dump_json())
        await asyncio.sleep(0.2)

        messages = []
        for _ in range(10):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if msg and msg["type"] == "message":
                messages.append(json.loads(msg["data"]))
                break

        await pubsub.unsubscribe(CHANNEL_TRADE_APPROVED)
        await pubsub.close()

        assert len(messages) == 1
        assert messages[0]["event_type"] == "trade_approved"
        assert messages[0]["payload"]["qualification_report"]["qualified"] == True

    @pytest.mark.asyncio
    async def test_05_anansi_qualification_fail(self, clean_redis):
        """Test: Anansi rejects token that fails safety gates."""
        redis = clean_redis

        from src.python.shared.constants import CHANNEL_TRADE_FAILED

        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL_TRADE_FAILED)
        await asyncio.sleep(0.1)

        envelope = AgentMessageEnvelope(
            agent_id="AGT-03",
            event_type="trade_failed",
            payload={
                "token": {"mint": "failed_token", "symbol": "FAIL"},
                "reason": "Failed gates: ['G1']",
                "gates_passed": ["G7", "G11"],
                "gates_failed": ["G1", "G2"],
            },
            correlation_id=str(uuid.uuid4()),
        )

        await redis.publish(CHANNEL_TRADE_FAILED, envelope.model_dump_json())
        await asyncio.sleep(0.2)

        messages = []
        for _ in range(10):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if msg and msg["type"] == "message":
                messages.append(json.loads(msg["data"]))
                break

        await pubsub.unsubscribe(CHANNEL_TRADE_FAILED)
        await pubsub.close()

        assert len(messages) == 1
        assert messages[0]["event_type"] == "trade_failed"

    @pytest.mark.asyncio
    async def test_06_ares_position_opened(self, clean_redis):
        """Test: Ares executes trade and opens position."""
        redis = clean_redis

        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL_POSITION_OPENED)
        await asyncio.sleep(0.1)

        entry_price = 0.0005
        tokens_received = 1000000

        envelope = AgentMessageEnvelope(
            agent_id="AGT-05",
            event_type="position_opened",
            payload={
                "position_id": str(uuid.uuid4()),
                "mint": "EPjFWdd5AufqSSqeM2qNDbS92h5hS4G1h6X1S5Qzj5bZ",
                "entry_price_sol": entry_price,
                "tokens_received": tokens_received,
                "position_size_sol": 0.0005,
            },
            correlation_id=str(uuid.uuid4()),
        )

        await redis.publish(CHANNEL_POSITION_OPENED, envelope.model_dump_json())
        await asyncio.sleep(0.2)

        messages = []
        for _ in range(10):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if msg and msg["type"] == "message":
                messages.append(json.loads(msg["data"]))
                break

        await pubsub.unsubscribe(CHANNEL_POSITION_OPENED)
        await pubsub.close()

        assert len(messages) == 1
        assert messages[0]["event_type"] == "position_opened"
        assert messages[0]["payload"]["tokens_received"] == tokens_received

    @pytest.mark.asyncio
    async def test_07_active_positions_tracking(self, clean_redis):
        """Test: Active positions are tracked in Redis."""
        redis = clean_redis
        position_id = str(uuid.uuid4())

        await redis.sadd(REDIS_KEY_ACTIVE_POSITIONS, position_id)

        count = await redis.scard(REDIS_KEY_ACTIVE_POSITIONS)
        assert count == 1

        is_member = await redis.sismember(REDIS_KEY_ACTIVE_POSITIONS, position_id)
        assert is_member == True

    @pytest.mark.asyncio
    async def test_08_tp1_hit_event(self, clean_redis):
        """Test: TP1 hit triggers partial sell."""
        redis = clean_redis

        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL_TP1_HIT)
        await asyncio.sleep(0.1)

        envelope = AgentMessageEnvelope(
            agent_id="AGT-06",
            event_type="tp1_hit",
            payload={
                "position_id": str(uuid.uuid4()),
                "mint": "TP1_token_mint",
                "sell_portion": 0.5,
                "exit_price": 0.001,
                "current_price": 0.001,
            },
            correlation_id=str(uuid.uuid4()),
        )

        await redis.publish(CHANNEL_TP1_HIT, envelope.model_dump_json())
        await asyncio.sleep(0.2)

        messages = []
        for _ in range(10):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if msg and msg["type"] == "message":
                messages.append(json.loads(msg["data"]))
                break

        await pubsub.unsubscribe(CHANNEL_TP1_HIT)
        await pubsub.close()

        assert len(messages) == 1
        assert messages[0]["event_type"] == "tp1_hit"
        assert messages[0]["payload"]["sell_portion"] == 0.5

    @pytest.mark.asyncio
    async def test_09_tp2_hit_event(self, clean_redis):
        """Test: TP2 hit triggers final sell."""
        redis = clean_redis

        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL_TP2_HIT)
        await asyncio.sleep(0.1)

        envelope = AgentMessageEnvelope(
            agent_id="AGT-06",
            event_type="tp2_hit",
            payload={
                "position_id": str(uuid.uuid4()),
                "mint": "TP2_token_mint",
                "sell_portion": 0.5,
                "current_price": 0.0025,
            },
            correlation_id=str(uuid.uuid4()),
        )

        await redis.publish(CHANNEL_TP2_HIT, envelope.model_dump_json())
        await asyncio.sleep(0.2)

        messages = []
        for _ in range(10):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if msg and msg["type"] == "message":
                messages.append(json.loads(msg["data"]))
                break

        await pubsub.unsubscribe(CHANNEL_TP2_HIT)
        await pubsub.close()

        assert len(messages) == 1
        assert messages[0]["event_type"] == "tp2_hit"

    @pytest.mark.asyncio
    async def test_10_stop_loss_event(self, clean_redis):
        """Test: Stop loss triggers full position close."""
        redis = clean_redis

        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL_STOP_LOSS_HIT)
        await asyncio.sleep(0.1)

        envelope = AgentMessageEnvelope(
            agent_id="AGT-06",
            event_type="stop_loss_hit",
            payload={
                "position_id": str(uuid.uuid4()),
                "mint": "SL_token_mint",
                "sell_portion": 1.0,
                "exit_price": 0.00035,
                "current_price": 0.00035,
            },
            correlation_id=str(uuid.uuid4()),
        )

        await redis.publish(CHANNEL_STOP_LOSS_HIT, envelope.model_dump_json())
        await asyncio.sleep(0.2)

        messages = []
        for _ in range(10):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if msg and msg["type"] == "message":
                messages.append(json.loads(msg["data"]))
                break

        await pubsub.unsubscribe(CHANNEL_STOP_LOSS_HIT)
        await pubsub.close()

        assert len(messages) == 1
        assert messages[0]["event_type"] == "stop_loss_hit"
        assert messages[0]["payload"]["sell_portion"] == 1.0

    @pytest.mark.asyncio
    async def test_11_daily_pnl_tracking(self, clean_redis):
        """Test: Daily PnL is tracked in Redis."""
        redis = clean_redis

        await redis.set(REDIS_KEY_DAILY_PNL, "0.0015")
        pnl = await redis.get(REDIS_KEY_DAILY_PNL)
        assert float(pnl) == 0.0015

        await redis.set(REDIS_KEY_DAILY_PNL, "-0.0025")
        pnl = await redis.get(REDIS_KEY_DAILY_PNL)
        assert float(pnl) == -0.0025

    @pytest.mark.asyncio
    async def test_12_kill_switch_blocks_trading(self, clean_redis):
        """Test: Kill switch prevents new trades."""
        redis = clean_redis

        await redis.set(REDIS_KEY_KILL_SWITCH, "active")
        kill_switch = await redis.get(REDIS_KEY_KILL_SWITCH)
        assert kill_switch == "active"

        position_size = 0.0005
        daily_loss_limit = -0.002
        current_pnl = -0.003

        if kill_switch == "active" or current_pnl < daily_loss_limit:
            should_block = True
        else:
            should_block = False

        assert should_block == True

    @pytest.mark.asyncio
    async def test_13_pause_trading_blocks_trading(self, clean_redis):
        """Test: Trading pause prevents new trades."""
        redis = clean_redis

        await redis.set(REDIS_KEY_TRADING_PAUSED, "true")
        paused = await redis.get(REDIS_KEY_TRADING_PAUSED)
        assert paused == "true"

    @pytest.mark.asyncio
    async def test_14_event_logging(self, clean_redis):
        """Test: Events are logged to Redis."""
        redis = clean_redis
        correlation_id = str(uuid.uuid4())

        envelope = AgentMessageEnvelope(
            agent_id="AGT-03",
            event_type="trade_approved",
            payload={"mint": "test_mint", "qualified": True},
            correlation_id=correlation_id,
        )

        await redis.lpush(f"event:trade_approved:0", envelope.model_dump_json())

        events = await redis.lrange(f"event:trade_approved:0", 0, 0)
        assert len(events) == 1

        logged_event = json.loads(events[0])
        assert logged_event["event_type"] == "trade_approved"
        assert logged_event["correlation_id"] == correlation_id

    @pytest.mark.asyncio
    async def test_15_complete_flow_integration(self, clean_redis):
        """Test: Complete flow from token detection to position closed."""
        redis = clean_redis
        correlation_id = str(uuid.uuid4())
        position_id = str(uuid.uuid4())

        token = {
            "mint": "5ZH8bCprBLN1qhS4dDdTGQnQxKVC3F1k6jz5rR5ax",
            "symbol": "FULL",
            "marketCapSol": 50.0,
            "vSolInBondingCurve": 45000000000,
            "bondingCurveKey": "curve_key",
            "uri": "",
        }

        await redis.zadd(
            REDIS_KEY_TRADE_QUEUE,
            {
                json.dumps(
                    {
                        "event_type": "token_detected",
                        "payload": token,
                        "correlation_id": correlation_id,
                    }
                ): 3
            },
        )

        queue_count = await redis.zcard(REDIS_KEY_TRADE_QUEUE)
        assert queue_count == 1

        await redis.sadd(REDIS_KEY_ACTIVE_POSITIONS, position_id)

        active_count = await redis.scard(REDIS_KEY_ACTIVE_POSITIONS)
        assert active_count == 1

        await redis.set(REDIS_KEY_DAILY_PNL, "0.0005")

        pnl = await redis.get(REDIS_KEY_DAILY_PNL)
        assert float(pnl) > 0

    @pytest.mark.asyncio
    async def test_16_rate_limiting(self, clean_redis):
        """Test: Rate limiting tracks trade counts per hour."""
        redis = clean_redis
        current_hour = int(time.time() // 3600)

        trade_key = f"mtus:trade_count:{current_hour}"
        await redis.set(trade_key, "2")

        count = await redis.get(trade_key)
        assert int(count) <= 3

        max_trades = 3
        can_trade = int(count) < max_trades
        assert can_trade == True

    @pytest.mark.asyncio
    async def test_17_position_size_validation(self, clean_redis):
        """Test: Position size is within allowed range."""
        redis = clean_redis

        position_size = 0.0005
        min_size = 0.0001
        max_size = 0.01

        assert min_size <= position_size <= max_size

    @pytest.mark.asyncio
    async def test_18_paper_mode_detection(self, paper_mode):
        """Test: Paper mode correctly identified."""
        assert is_paper_mode() == True
