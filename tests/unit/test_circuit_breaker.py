import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

from python.shared.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreaker:
    def test_01_initial_state_closed(self):
        cb = CircuitBreaker(threshold=3, reset_timeout_sec=60)
        assert cb.get_state() == CircuitState.CLOSED

    def test_02_failure_threshold_opens_circuit(self):
        cb = CircuitBreaker(threshold=3, reset_timeout_sec=60)
        for _ in range(3):
            cb.on_failure()
        assert cb.get_state() == CircuitState.OPEN

    def test_03_reset_after_timeout(self):
        cb = CircuitBreaker(threshold=3, reset_timeout_sec=1)
        for _ in range(3):
            cb.on_failure()
        assert cb.get_state() == CircuitState.OPEN
        import time

        time.sleep(1.1)
        cb.state = CircuitState.HALF_OPEN
        assert cb.get_state() == CircuitState.HALF_OPEN

    def test_04_success_resets_circuit(self):
        cb = CircuitBreaker()
        cb.on_failure()
        cb.on_failure()
        cb.on_success()
        assert cb.get_state() == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_05_execute_with_closed_circuit(self):
        cb = CircuitBreaker()
        result = cb.execute(lambda: 42)
        assert result == 42

    def test_06_execute_with_open_circuit(self):
        cb = CircuitBreaker(threshold=1, reset_timeout_sec=60)
        cb.on_failure()
        try:
            cb.execute(lambda: 42)
            assert False, "Should have raised"
        except Exception:
            pass
