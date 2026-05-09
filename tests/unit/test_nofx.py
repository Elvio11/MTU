import pytest
import sys
import os
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

# Add D:/Trader/src to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

from src.python.agents.nofx import (
    NofxAgent,
    PUMP_PORTAL_WS_URL,
    MAX_EVENTS_PER_SECOND,
    RECONNECT_BASE_DELAY,
    RECONNECT_MAX_DELAY,
)
from src.python.shared.token_payload import PumpPortalTokenPayload


class TestNofxAgent:
    """Test NofxAgent (AGT-01) - Section 3.3 verification"""

    def test_01_websocket_url(self):
        """Verify PumpDev WS URL per Section 3.3"""
        url = PUMP_PORTAL_WS_URL.lower()
        assert "pumpdev" in url
        assert "wss://" in url

    def test_02_agent_instantiation(self):
        """Verify agent can be instantiated"""
        agent = NofxAgent()
        assert agent is not None
        assert hasattr(agent, "is_paper_mode")

    def test_03_exponential_backoff(self):
        """Verify reconnect with exponential backoff"""
        agent = NofxAgent()
        assert RECONNECT_BASE_DELAY == 1
        assert RECONNECT_MAX_DELAY == 30
        assert agent.get_backoff_delay(0) == 1
        assert agent.get_backoff_delay(1) == 2
        assert agent.get_backoff_delay(2) == 4
        assert agent.get_backoff_delay(5) == 30  # capped

    def test_04_rate_limit_calculation(self):
        """Verify rate limit settings"""
        assert MAX_EVENTS_PER_SECOND == 10
        agent = NofxAgent()
        agent.event_count = 0
        agent.last_reset = datetime.utcnow().timestamp()
        for i in range(10):
            assert agent.check_rate_limit() == True
        assert agent.check_rate_limit() == False

    def test_05_mint_extraction(self):
        """Verify mint extraction from logs"""
        agent = NofxAgent()
        logs = ["Program log: initialize mint 7xKXtg2C5jN4GpT1KYnH3CvB8pNq8JhQq6FhPqd1"]
        mint = agent.extract_mint_from_logs(logs)
        assert mint != ""
        assert len(mint) >= 32


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
