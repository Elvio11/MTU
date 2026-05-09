import time
from enum import Enum


class CircuitState(Enum):
    CLOSED = 1
    OPEN = 2
    HALF_OPEN = 3


class CircuitBreaker:
    def __init__(self, threshold: int = 3, reset_timeout_sec: int = 60):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.threshold = threshold
        self.reset_timeout_sec = reset_timeout_sec

    def execute(self, fn):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.reset_timeout_sec:
                self.state = CircuitState.HALF_OPEN
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = fn()
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise e

    def on_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.threshold:
            self.state = CircuitState.OPEN

    def get_state(self):
        return self.state
