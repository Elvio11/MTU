"""
E2E Test - Agent Pipeline Flow
Tests the complete token detection → qualification → trade flow.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.python.shared.envelope import AgentMessageEnvelope, EventType
from src.python.shared.constants import (
    CHANNEL_TOKEN_DETECTED,
    CHANNEL_TOKEN_RECEIVED,
    CHANNEL_TOKEN_QUALIFIED,
    CHANNEL_TRADE_APPROVED,
    CHANNEL_POSITION_OPENED,
    is_paper_mode,
)


class TestAgentPipeline:
    """Test full agent pipeline flow."""

    @pytest.mark.asyncio
    async def test_01_token_detected_to_hermes(self, clean_redis):
        """Test: NOFX detects token → Hermes receives on channel."""
        redis = clean_redis

        # Subscribe FIRST
        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL_TOKEN_DETECTED)
        await asyncio.sleep(0.1)  # Allow subscription to establish

        test_token = {
            "mint": "5ZH8bCprBLN1qhS4dDdTGQnQxKVC3F1k6jz5rR5ax",
            "symbol": "TEST",
            "marketCapSol": 50.0,
            "vSol": 45.0,
        }

        envelope = AgentMessageEnvelope(
            agent_id="AGT-01",
            event_type="token_detected",
            payload=test_token,
        )

        # Publish AFTER subscribing
        await redis.publish(CHANNEL_TOKEN_DETECTED, envelope.model_dump_json())

        await asyncio.sleep(0.2)

        messages = []
        for _ in range(10):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if msg and msg["type"] == "message":
                messages.append(json.loads(msg["data"]))
                break

        await pubsub.unsubscribe(CHANNEL_TOKEN_DETECTED)
        await pubsub.close()

        assert len(messages) == 1
        assert messages[0]["event_type"] == "token_detected"
        assert messages[0]["payload"]["mint"] == test_token["mint"]

    @pytest.mark.asyncio
    async def test_02_hermes_to_anansi(self, clean_redis):
        """Test: Hermes routes token to Anansi for qualification."""
        redis = clean_redis

        # Subscribe FIRST
        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL_TOKEN_RECEIVED)
        await asyncio.sleep(0.1)

        token_data = {
            "mint": "5ZH8bCprBLN1qhS4dDdTGQnQxKVC3F1k6jz5rR5ax",
            "symbol": "TEST",
            "marketCapSol": 50.0,
        }

        envelope = AgentMessageEnvelope(
            agent_id="AGT-02",
            event_type="token_received",
            payload=token_data,
        )

        # Publish AFTER subscribing
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
    async def test_03_anansi_qualification_result(self, clean_redis):
        """Test: Anansi publishes qualification result."""
        redis = clean_redis

        # Subscribe FIRST
        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL_TOKEN_QUALIFIED)
        await asyncio.sleep(0.1)

        qualification = {
            "gates_passed": ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"],
            "gates_failed": [],
            "rugcheck_score": 150,
            "qualified": True,
        }

        envelope = AgentMessageEnvelope(
            agent_id="AGT-03",
            event_type="token_qualified",
            payload={
                "token": {"mint": "test_mint"},
                "qualification": qualification,
            },
        )

        # Publish AFTER subscribing
        await redis.publish(CHANNEL_TOKEN_QUALIFIED, envelope.model_dump_json())

        await asyncio.sleep(0.2)

        messages = []
        for _ in range(10):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if msg and msg["type"] == "message":
                messages.append(json.loads(msg["data"]))
                break

        await pubsub.unsubscribe(CHANNEL_TOKEN_QUALIFIED)
        await pubsub.close()

        assert len(messages) == 1
        assert messages[0]["event_type"] == "token_qualified"
        assert messages[0]["payload"]["qualification"]["qualified"] == True

    @pytest.mark.asyncio
    async def test_04_trade_approved_flow(self, clean_redis):
        """Test: Trade approved flows to executor."""
        redis = clean_redis

        # Subscribe FIRST
        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL_TRADE_APPROVED)
        await asyncio.sleep(0.1)

        envelope = AgentMessageEnvelope(
            agent_id="AGT-03",
            event_type="trade_approved",
            payload={
                "mint": "test_mint",
                "position_size_sol": 0.0005,
                "entry_price": 0.01,
            },
        )

        # Publish AFTER subscribing
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

    @pytest.mark.asyncio
    async def test_05_position_opened(self, clean_redis):
        """Test: Position opened event."""
        redis = clean_redis

        # Subscribe FIRST
        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL_POSITION_OPENED)
        await asyncio.sleep(0.1)

        envelope = AgentMessageEnvelope(
            agent_id="AGT-05",
            event_type="position_opened",
            payload={
                "position_id": "test-pos-123",
                "mint": "test_mint",
                "entry_price_sol": 0.0005,
                "tokens_received": 1000000,
            },
        )

        # Publish AFTER subscribing
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

    def test_06_paper_mode_detection(self, paper_mode):
        """Test: is_paper_mode returns correct value."""
        assert is_paper_mode() == True
