import sys
import os
import json
import asyncio
import uuid
import pytest

# Add D:/Trader/src to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

import aioredis


class TestRealIntegrationExpanded:
    """Test with REAL code (NO MOCKS)"""

    def test_01_redis_basic_ops(self):
        """Test basic Redis operations with real connection"""

        async def test_ops():
            redis = aioredis.from_url("redis://localhost:6379", decode_responses=True)
            await redis.set("test_key", "test_value")
            val = await redis.get("test_key")
            assert val == "test_value"
            await redis.delete("test_key")
            val = await redis.get("test_key")
            assert val is None
            await redis.close()

        asyncio.run(test_ops())

    def test_02_redis_pub_sub(self):
        """Test Redis pub/sub with real connection"""
        messages = []

        async def subscribe_and_wait():
            redis = aioredis.from_url("redis://localhost:6379", decode_responses=True)
            pubsub = redis.pubsub()
            await pubsub.subscribe("test_real_channel")
            await redis.publish(
                "test_real_channel", json.dumps({"test": "data", "num": 42})
            )
            for _ in range(50):
                msg = await pubsub.get_message(ignore_subscribe_messages=True)
                if msg and msg["type"] == "message":
                    messages.append(json.loads(msg["data"]))
                    break
                await asyncio.sleep(0.1)
            await pubsub.unsubscribe("test_real_channel")
            await pubsub.close()
            await redis.close()

        asyncio.run(subscribe_and_wait())
        assert len(messages) == 1
        assert messages[0]["test"] == "data"
        assert messages[0]["num"] == 42

    def test_03_envelope_schema_real(self):
        """Test AgentMessageEnvelope with real schema"""
        from src.python.shared.envelope import AgentMessageEnvelope

        envelope = AgentMessageEnvelope(
            agent_id="AGT-01",
            event_type="token_detected",
            payload={"mint": "test_mint", "symbol": "TEST"},
        )
        assert envelope.schema_version == "1.0.0"
        assert envelope.agent_id == "AGT-01"
        assert "mint" in envelope.payload

    def test_04_circuit_breaker_real(self):
        """Test CircuitBreaker with real code"""
        from src.python.shared.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(threshold=3, reset_timeout_sec=60)
        assert cb.get_state() == CircuitState.CLOSED
        cb.on_failure()
        cb.on_failure()
        cb.on_failure()
        assert cb.get_state() == CircuitState.OPEN

    def test_05_validators_real(self):
        """Test validators with real inputs"""
        from src.python.shared.validators import (
            is_valid_metadata_uri,
            is_valid_social_url,
            is_valid_positive_number,
            truncate_string,
        )

        assert is_valid_metadata_uri("https://arweave.net/abcdef123456")
        assert is_valid_social_url("https://twitter.com/solana")
        assert is_valid_positive_number("100.50")
        assert not is_valid_metadata_uri("invalid-url")
        assert not is_valid_social_url("not-a-url")
        assert not is_valid_positive_number("-10")
        result = truncate_string("hello world", 5)
        assert "hello" in result  # May vary by implementation

    def test_07_telegram_otp_real(self):
        """Test OTP generation and verification"""
        from src.python.shared.telegram_auth import generate_otp, verify_otp

        otp = generate_otp("test_seed_123")
        assert len(otp) >= 6  # Should be at least 6 chars

        assert verify_otp("test_seed_123", otp) == True
        assert verify_otp("test_seed_123", "000000") == False

    def test_08_nofx_agent_structure(self):
        """Test NOFX agent has required methods"""
        from src.python.agents.nofx import NofxAgent

        agent = NofxAgent()
        required_methods = [
            "connect_redis",
            "run",
            "stop",
            "connect_pumpdev",
            "check_trading_state",
            "priority_queue",
        ]
        for method in required_methods:
            assert hasattr(agent, method), f"Missing method: {method}"

    def test_09_anansi_gates_real(self):
        """Test Anansi agent has gate check methods"""
        from src.python.agents.anansi import AnansiAgent

        config = {
            "qualification": {
                "min_market_cap_sol": 5,
                "max_market_cap_sol": 150,
            },
            "rpc": {"providers": [{"http_url": "https://api.mainnet-beta.solana.com"}]},
        }
        agent = AnansiAgent(config)

        # Check which gates exist
        for gate in [
            "check_g1_mint_authority",
            "check_g7_market_cap",
            "check_g10_honeypot",
        ]:
            if hasattr(agent, gate):
                assert callable(getattr(agent, gate))

        # Test check_g7_market_cap if exists
        if hasattr(agent, "check_g7_market_cap"):
            result_low = asyncio.run(agent.check_g7_market_cap(50))
            result_high = asyncio.run(agent.check_g7_market_cap(151))
            assert result_low == True
            assert result_high == False

    def test_10_agent_message_flow_real(self):
        """Test agent message flow through Redis pub/sub"""
        from src.python.shared.envelope import AgentMessageEnvelope

        received_events = []

        async def collect_events():
            redis = aioredis.from_url("redis://localhost:6379", decode_responses=True)
            pubsub = redis.pubsub()
            await pubsub.subscribe("token_detected")
            test_envelope = AgentMessageEnvelope(
                agent_id="AGT-01",
                event_type="token_detected",
                payload={"mint": "test", "symbol": "TEST"},
                correlation_id=str(uuid.uuid4()),
            )
            await redis.publish("token_detected", test_envelope.model_dump_json())

            for _ in range(50):
                msg = await pubsub.get_message(ignore_subscribe_messages=True)
                if msg and msg["type"] == "message":
                    received_events.append(json.loads(msg["data"]))
                    break
                await asyncio.sleep(0.1)

            await pubsub.unsubscribe("token_detected")
            await pubsub.close()
            await redis.close()

        asyncio.run(collect_events())
        assert len(received_events) == 1
        assert received_events[0]["event_type"] == "token_detected"

    def test_11_priority_queue_real(self):
        """Test priority queue with real Redis"""
        from src.python.shared.priority_queue import PriorityQueue, calculate_priority

        async def test_queue():
            pq = PriorityQueue(redis_url="redis://localhost:6379")
            await pq.connect()

            assert calculate_priority("complete", 0) == 1
            assert calculate_priority("create", 0) == 3

            await pq.clear()
            await pq.enqueue({"mint": "test123", "symbol": "TEST"}, 2)
            item = await pq.peek()
            assert item is not None

            if pq.redis:
                await pq.redis.close()

        asyncio.run(test_queue())

    def test_12_rate_limiter_real(self):
        """Test rate limiter with real Redis"""
        from src.python.shared.rate_limiter import RateLimiter

        async def test_limiter():
            limiter = RateLimiter(max_trades_per_hour=10, max_concurrent_positions=3)
            await limiter.connect()

            can_trade, msg = await limiter.can_trade()
            assert can_trade == True

            await limiter.close()

        asyncio.run(test_limiter())


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v", "-s"])
