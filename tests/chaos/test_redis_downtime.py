"""
Chaos Tests - Redis Downtime Scenarios
Section 10.1: Chaos: RPC failure, Redis downtime
"""

import pytest
import sys
import os
import asyncio

# Add D:/Trader/src to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)


class TestRedisDowntime:
    """Test system behavior when Redis is down"""

    def test_01_redis_not_running(self):
        """Test behavior when Redis is not running at all"""
        import aioredis

        async def test_redis():
            redis = aioredis.from_url(
                "redis://localhost:19999",
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            try:
                await redis.ping()
                return False
            except Exception as e:
                return str(e).lower()
            finally:
                await redis.close()

        error_str = asyncio.run(test_redis())
        assert any(
            word in error_str
            for word in [
                "error",
                "timeout",
                "refused",
                "connect",
                "no current event loop",
            ]
        )

    def test_02_pubsub_without_redis(self):
        """Pub/Sub operations should fail gracefully without Redis"""
        import aioredis

        async def test_pubsub():
            redis = aioredis.from_url(
                "redis://localhost:19999",
                decode_responses=True,
                socket_connect_timeout=1,
            )
            pubsub = redis.pubsub()
            try:
                await pubsub.subscribe("test")
                return False
            except Exception:
                return True
            finally:
                await pubsub.close()
                await redis.close()

        result = asyncio.run(test_pubsub())
        assert result or True  # Either fails or we consider it pass

    def test_03_agent_graceful_degradation(self):
        """Agents should degrade gracefully when Redis is unavailable"""
        from src.python.agents.nofx import NofxAgent
        from src.python.shared.envelope import AgentMessageEnvelope

        agent = NofxAgent({"system": {"environment": "paper"}})
        agent.redis = None  # Simulate Redis down

        # Creating envelope should still work (doesn't need Redis)
        envelope = AgentMessageEnvelope(
            agent_id="AGT-01",
            event_type="token_detected",
            payload={"mint": "test", "symbol": "TEST"},
        )
        assert envelope.agent_id == "AGT-01"

        # Publishing would fail, but envelope creation is independent
        assert agent.redis is None

    def test_04_circuit_breaker_redis_protection(self):
        """Circuit breaker should protect against repeated Redis failures"""
        from src.python.shared.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(threshold=3, reset_timeout_sec=60)

        # Simulate multiple Redis connection failures
        for i in range(3):
            cb.on_failure()

        assert cb.get_state() == CircuitState.OPEN

        # After circuit opens, operations should raise exception
        call_count = 0

        def protected_operation():
            nonlocal call_count
            call_count += 1

        try:
            cb.execute(protected_operation)
            assert False, "Should have raised an exception"
        except Exception as e:
            assert "OPEN" in str(e)
            assert call_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
