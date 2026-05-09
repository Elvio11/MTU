import { v4 as uuidv4 } from 'uuid';

export type AgentId = 'AGT-01' | 'AGT-02' | 'AGT-03' | 'AGT-04' | 'AGT-05' | 'AGT-06' | 'AGT-07' | 'AGT-08' | 'AGT-09' | 'AGT-10' | 'AGT-11';

export type EventType =
  | 'token_detected' | 'token_qualified' | 'token_received' | 'safety_checked'
  | 'price_updated' | 'trade_approved' | 'trade_executed' | 'trade_failed'
  | 'position_opened' | 'position_closed' | 'tp1_hit' | 'tp2_hit'
  | 'stop_loss_hit' | 'trailing_stop_hit' | 'time_sl_hit' | 'manual_exit'
  | 'sweep_requested' | 'sweep_completed' | 'health_check' | 'system_alert'
  | 'token_gradated' | 'price_unavailable' | 'token_received_social' | 'social_scored'
  | 'kill_switch_triggered' | 'token_migrated';

export interface AgentMessageEnvelope {
  envelope_id: string;
  agent_id: AgentId;
  event_type: EventType;
  timestamp_utc: string;
  payload: Record<string, any>;
  correlation_id: string;
  schema_version: '1.0.0';
}

export const createEnvelope = (
  agentId: AgentId,
  eventType: EventType,
  payload: Record<string, any>,
  correlationId?: string
): AgentMessageEnvelope => ({
  envelope_id: uuidv4(),
  agent_id: agentId,
  event_type: eventType,
  timestamp_utc: new Date().toISOString(),
  payload,
  correlation_id: correlationId || uuidv4(),
  schema_version: '1.0.0',
});
