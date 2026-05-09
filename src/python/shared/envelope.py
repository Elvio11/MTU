from pydantic import BaseModel, Field, field_validator
from uuid import uuid4, UUID
from datetime import datetime
from typing import Literal, Any, Dict

AgentId = Literal[
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
]

EventType = Literal[
    "token_detected",
    "token_qualified",
    "token_received",
    "safety_checked",
    "price_updated",
    "trade_approved",
    "trade_executed",
    "trade_failed",
    "position_opened",
    "position_closed",
    "tp1_hit",
    "tp2_hit",
    "stop_loss_hit",
    "trailing_stop_hit",
    "time_sl_hit",
    "manual_exit",
    "sweep_requested",
    "sweep_completed",
    "health_check",
    "system_alert",
    "token_gradated",
    "price_unavailable",
    "token_received_social",
    "social_scored",
    "kill_switch_triggered",
    "token_migrated",
]


class AgentMessageEnvelope(BaseModel):
    envelope_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: AgentId
    event_type: EventType
    timestamp_utc: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    payload: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: Literal["1.0.0"] = "1.0.0"

    @field_validator("envelope_id", "correlation_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        try:
            UUID(v)
        except ValueError:
            raise ValueError("Must be a valid UUID v4")
        return v
