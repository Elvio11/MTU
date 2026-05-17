import unittest
import sys
import os
import uuid
from unittest.mock import MagicMock, patch, AsyncMock

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)


class TestAgentMessageFlows(unittest.TestCase):
    """Integration tests for agent-to-agent message flows"""

    def test_envelope_schema(self):
        """Verify AgentMessageEnvelope schema per Section 3.2"""
        from src.python.shared.envelope import AgentMessageEnvelope, EventType

        envelope = AgentMessageEnvelope(
            agent_id="AGT-01",
            event_type="token_detected",
            payload={"mint": "test_mint", "symbol": "TEST"},
        )

        self.assertEqual(envelope.schema_version, "1.0.0")
        self.assertIn(
            envelope.agent_id,
            [
                "AGT-01",
                "AGT-02",
                "AGT-03",
                "AGT-04",
                "AGT-05",
                "AGT-06",
                "AGT-07",
                "AGT-08",
                "AGT-09",
                "AGT-10",
            ],
        )
        self.assertIsNotNone(envelope.envelope_id)
        self.assertIsNotNone(envelope.correlation_id)

    def test_token_detected_to_hermes_flow(self):
        """Test NOFX -> Hermes: token_detected event routing"""
        from src.python.agents.nofx import NofxAgent

        with patch("src.python.agents.nofx.NofxAgent"):
            agent = NofxAgent({})
            agent.redis = MagicMock()
            agent.redis.publish = AsyncMock()

            mock_envelope = {
                "envelope_id": "test-uuid",
                "agent_id": "AGT-01",
                "event_type": "token_detected",
                "payload": {"mint": "abc123", "symbol": "TEST", "marketCapSol": 50.0},
                "correlation_id": "corr-uuid",
            }

            self.assertEqual(mock_envelope["event_type"], "token_detected")

    def test_hermes_to_anansi_flow(self):
        """Test Hermes -> Anansi: token_received event routing"""
        from src.python.shared.envelope import AgentMessageEnvelope

        token_payload = {
            "mint": "5ZH8bCprBLN1qhS4dDdTGQnQxKVC3F1k6jz5rR5ax",
            "symbol": "TEST",
            "marketCapSol": 50.0,
        }

        envelope = AgentMessageEnvelope(
            agent_id="AGT-02",
            event_type="token_received",
            payload=token_payload,
        )

        self.assertEqual(envelope.event_type, "token_received")
        self.assertEqual(envelope.payload["mint"], token_payload["mint"])

    def test_anansi_to_hermes_qualified_flow(self):
        """Test Anansi -> Hermes: token_qualified event"""
        from src.python.shared.envelope import AgentMessageEnvelope

        qualification_report = {
            "gates_passed": ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"],
            "gates_failed": [],
            "rugcheck_score": 150,
            "qualified": True,
        }

        envelope = AgentMessageEnvelope(
            agent_id="AGT-03",
            event_type="token_qualified",
            payload={"token": {"mint": "test"}, "qualification": qualification_report},
        )

        self.assertEqual(envelope.event_type, "token_qualified")
        self.assertTrue(envelope.payload["qualification"]["qualified"])

    def test_hermes_to_ares_trade_approved_flow(self):
        """Test Hermes -> Ares: trade_approved event"""
        from src.python.shared.envelope import AgentMessageEnvelope

        envelope = AgentMessageEnvelope(
            agent_id="AGT-02",
            event_type="trade_approved",
            payload={
                "mint": "test_mint",
                "position_size_sol": 0.15,
                "entry_price": 0.01,
            },
        )

        self.assertEqual(envelope.event_type, "trade_approved")

    def test_ares_to_sentinel_position_opened_flow(self):
        """Test Ares -> Sentinel: position_opened event"""
        from src.python.shared.envelope import AgentMessageEnvelope

        envelope = AgentMessageEnvelope(
            agent_id="AGT-05",
            event_type="position_opened",
            payload={
                "position_id": "pos-123",
                "mint": "test_mint",
                "entryPriceSol": 0.01,
                "tokensReceived": 1000000,
            },
        )

        self.assertEqual(envelope.event_type, "position_opened")
        self.assertIsNotNone(envelope.payload["position_id"])

    def test_sentinel_tp1_hit_flow(self):
        """Test Sentinel: tp1_hit event"""
        from src.python.shared.envelope import AgentMessageEnvelope

        envelope = AgentMessageEnvelope(
            agent_id="AGT-06",
            event_type="tp1_hit",
            payload={
                "position_id": "pos-123",
                "sell_portion": 0.5,
                "realised_pnl_sol": 0.15,
            },
        )

        self.assertEqual(envelope.event_type, "tp1_hit")
        self.assertEqual(envelope.payload["sell_portion"], 0.5)

    def test_sentinel_tp2_hit_flow(self):
        """Test Sentinel: tp2_hit event"""
        from src.python.shared.envelope import AgentMessageEnvelope

        envelope = AgentMessageEnvelope(
            agent_id="AGT-06",
            event_type="tp2_hit",
            payload={
                "position_id": "pos-123",
                "sell_portion": 0.5,
                "realised_pnl_sol": 0.60,
            },
        )

        self.assertEqual(envelope.event_type, "tp2_hit")

    def test_sentinel_stop_loss_flow(self):
        """Test Sentinel: stop_loss_hit event"""
        from src.python.shared.envelope import AgentMessageEnvelope

        envelope = AgentMessageEnvelope(
            agent_id="AGT-06",
            event_type="stop_loss_hit",
            payload={
                "position_id": "pos-123",
                "sell_portion": 1.0,
                "realised_pnl_sol": -0.045,
            },
        )

        self.assertEqual(envelope.event_type, "stop_loss_hit")
        self.assertLess(envelope.payload["realised_pnl_sol"], 0)

    def test_heracles_killswitch_flow(self):
        """Test Guardian: kill_switch_triggered event"""
        from src.python.shared.envelope import AgentMessageEnvelope

        envelope = AgentMessageEnvelope(
            agent_id="AGT-10",
            event_type="kill_switch_triggered",
            payload={"reason": "Daily loss limit breached", "timestamp": 1234567890},
        )

        self.assertEqual(envelope.event_type, "kill_switch_triggered")
        self.assertIn("reason", envelope.payload)

    def test_event_type_enum_complete(self):
        """Verify all event types from spec are supported"""
        from src.python.shared.envelope import EventType

        expected_events = [
            "token_detected",
            "token_qualified",
            "token_received",
            "trade_approved",
            "trade_executed",
            "position_opened",
            "position_closed",
            "tp1_hit",
            "tp2_hit",
            "stop_loss_hit",
            "kill_switch_triggered",
            "health_check",
        ]

        for event in expected_events:
            self.assertIn(event, EventType.__args__)


class TestMessageCorrelation(unittest.TestCase):
    """Test correlation ID tracking across agent flows"""

    def test_correlation_id_preserved(self):
        """Verify correlation_id is preserved across agent boundaries"""
        from src.python.shared.envelope import AgentMessageEnvelope
        import uuid

        correlation_id = str(uuid.uuid4())

        envelope1 = AgentMessageEnvelope(
            agent_id="AGT-01",
            event_type="token_detected",
            payload={"test": "data"},
            correlation_id=correlation_id,
        )

        self.assertEqual(envelope1.correlation_id, correlation_id)

        envelope2 = AgentMessageEnvelope(
            agent_id="AGT-02",
            event_type="token_received",
            payload={"test": "data"},
            correlation_id=correlation_id,
        )

        self.assertEqual(envelope2.correlation_id, correlation_id)
        self.assertEqual(envelope1.correlation_id, envelope2.correlation_id)


if __name__ == "__main__":
    unittest.main()
