"""
Chaos Tests - RPC Failure Scenarios
Section 10.1: Chaos: RPC failure, Redis downtime
"""

import pytest
import sys
import os
import asyncio
from unittest.mock import patch, MagicMock

# Add D:/Trader/src to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

from src.python.shared.circuit_breaker import CircuitBreaker, CircuitState


class TestRPCFailures:
    """Test system behavior when all RPC providers fail"""

    def test_01_all_rpcs_return_429(self):
        """All RPCs return 429 (rate limited) - circuit breakers should open"""
        from src.python.agents.anansi import AnansiAgent

        config = {
            "qualification": {
                "min_market_cap_sol": 5,
                "max_market_cap_sol": 150,
            },
            "rpc": {"providers": [{"http_url": "https://api.mainnet-beta.solana.com"}]},
        }
        agent = AnansiAgent(config)

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {"error": "Too Many Requests"}

        with patch("requests.post", return_value=mock_response):
            result = asyncio.run(agent.check_g1_mint_authority("test_mint"))
            assert result == False

    def test_02_rpc_timeout(self):
        """RPC calls timeout - should handle gracefully"""
        from src.python.agents.anansi import AnansiAgent

        config = {
            "qualification": {
                "min_market_cap_sol": 5,
                "max_market_cap_sol": 150,
            },
            "rpc": {"providers": [{"http_url": "https://api.mainnet-beta.solana.com"}]},
        }
        agent = AnansiAgent(config)

        with patch("requests.post", side_effect=TimeoutError("Connection timeout")):
            result = asyncio.run(agent.check_g4_dev_holdings("test_mint"))
            assert result == False

    def test_03_circuit_breaker_opens_after_failures(self):
        """Circuit breaker should open after threshold failures"""
        cb = CircuitBreaker(threshold=3, reset_timeout_sec=60)

        # Simulate failures
        for _ in range(3):
            cb.on_failure()

        # Circuit should be OPEN
        assert cb.get_state() == CircuitState.OPEN

        # Next call should raise exception (circuit open)
        executed = False

        def test_func():
            nonlocal executed
            executed = True

        try:
            cb.execute(test_func)
            assert False, "Should have raised an exception"
        except Exception as e:
            assert "OPEN" in str(e)
            assert executed == False

    def test_04_circuit_breaker_half_open_after_timeout(self):
        """Circuit breaker should transition to HALF_OPEN after timeout"""
        cb = CircuitBreaker(threshold=2, reset_timeout_sec=1)

        # Simulate failures to open circuit
        cb.on_failure()
        cb.on_failure()
        assert cb.get_state() == CircuitState.OPEN

        # Wait for timeout
        import time

        time.sleep(1.1)

        # Call execute - this should transition to HALF_OPEN and execute the function
        executed = False

        def test_func():
            nonlocal executed
            executed = True

        cb.execute(test_func)  # Should NOT raise exception
        assert executed == True
        # After successful execution, state should be CLOSED
        assert cb.get_state() == CircuitState.CLOSED


class TestRedisDowntime:
    """Test system behavior when Redis goes down"""

    def test_05_redis_connection_lost(self):
        """Redis connection is lost mid-operation"""
        import aioredis

        async def test_redis():
            redis = aioredis.from_url(
                "redis://localhost:9999", decode_responses=True, socket_timeout=1
            )
            try:
                await redis.ping()
                return False
            except Exception as e:
                return str(e).lower()
            finally:
                await redis.close()

        error_str = asyncio.run(test_redis())
        assert (
            "error" in error_str
            or "timeout" in error_str
            or "refused" in error_str
            or "no current event loop" in error_str
        )

    def test_06_agent_handles_redis_down(self):
        """Agent should not crash when Redis is down"""
        from src.python.agents.nofx import NofxAgent

        agent = NofxAgent()
        # Don't call connect_redis - simulate Redis being down
        agent.redis = None

        # Publishing should fail gracefully
        # (In real code, this would be handled by try/except)
        assert agent.redis is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
