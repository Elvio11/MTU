import { eventTypeToChannel } from './channels';
import { createEnvelope } from './envelope';

describe('channels', () => {
  test('eventTypeToChannel maps correctly', () => {
    expect(eventTypeToChannel('token_detected')).toBe('mtus:channel:token_detected');
    expect(eventTypeToChannel('')).toBe('mtus:channel:');
  });
});

describe('envelope', () => {
  test('createEnvelope generates valid envelope', () => {
    const env = createEnvelope('AGT-05', 'trade_executed', { mint: 'abc' }, 'corr-1');
    expect(env.agent_id).toBe('AGT-05');
    expect(env.event_type).toBe('trade_executed');
    expect(env.payload.mint).toBe('abc');
    expect(env.correlation_id).toBe('corr-1');
    expect(env.schema_version).toBe('1.0.0');
    expect(env.envelope_id).toBeDefined();
    expect(env.timestamp_utc).toBeDefined();
  });

  test('createEnvelope auto-generates correlation_id', () => {
    const env = createEnvelope('AGT-01', 'health_check', {});
    expect(env.correlation_id).toBeDefined();
    expect(env.correlation_id).not.toBe('');
  });
});
