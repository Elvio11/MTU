/**
 * Centralized Redis Pub/Sub channel names for MTUS.
 * All channels use the mtus:channel: prefix.
 * Must stay in sync with src/python/shared/constants.py
 */

export const MTUS_CHANNEL_PREFIX = 'mtus:channel:';

// Token Channels
export const CHANNEL_TOKEN_DETECTED = `${MTUS_CHANNEL_PREFIX}token_detected`;
export const CHANNEL_TOKEN_RECEIVED = `${MTUS_CHANNEL_PREFIX}token_received`;
export const CHANNEL_TOKEN_RECEIVED_SOCIAL = `${MTUS_CHANNEL_PREFIX}token_received_social`;
export const CHANNEL_TOKEN_QUALIFIED = `${MTUS_CHANNEL_PREFIX}token_qualified`;
export const CHANNEL_TOKEN_GRADATED = `${MTUS_CHANNEL_PREFIX}token_gradated`;
export const CHANNEL_TOKEN_MIGRATED = `${MTUS_CHANNEL_PREFIX}token_migrated`;

// Trade Channels
export const CHANNEL_TRADE_APPROVED = `${MTUS_CHANNEL_PREFIX}trade_approved`;
export const CHANNEL_TRADE_EXECUTED = `${MTUS_CHANNEL_PREFIX}trade_executed`;
export const CHANNEL_TRADE_FAILED = `${MTUS_CHANNEL_PREFIX}trade_failed`;

// Position Channels
export const CHANNEL_POSITION_OPENED = `${MTUS_CHANNEL_PREFIX}position_opened`;
export const CHANNEL_POSITION_CLOSED = `${MTUS_CHANNEL_PREFIX}position_closed`;

// Price Channels
export const CHANNEL_PRICE_UPDATED = `${MTUS_CHANNEL_PREFIX}price_updated`;
export const CHANNEL_PRICE_UNAVAILABLE = `${MTUS_CHANNEL_PREFIX}price_unavailable`;

// System Channels
export const CHANNEL_HEALTH_CHECK = `${MTUS_CHANNEL_PREFIX}health_check`;
export const CHANNEL_SYSTEM_ALERT = `${MTUS_CHANNEL_PREFIX}system_alert`;
export const CHANNEL_KILL_SWITCH_TRIGGERED = `${MTUS_CHANNEL_PREFIX}kill_switch_triggered`;

// Event Channels (TP/SL)
export const CHANNEL_TP1_HIT = `${MTUS_CHANNEL_PREFIX}tp1_hit`;
export const CHANNEL_TP2_HIT = `${MTUS_CHANNEL_PREFIX}tp2_hit`;
export const CHANNEL_STOP_LOSS_HIT = `${MTUS_CHANNEL_PREFIX}stop_loss_hit`;
export const CHANNEL_TRAILING_STOP_HIT = `${MTUS_CHANNEL_PREFIX}trailing_stop_hit`;
export const CHANNEL_TIME_SL_HIT = `${MTUS_CHANNEL_PREFIX}time_sl_hit`;
export const CHANNEL_MANUAL_EXIT = `${MTUS_CHANNEL_PREFIX}manual_exit`;

// Admin Channels
export const CHANNEL_SWEEP_REQUESTED = `${MTUS_CHANNEL_PREFIX}sweep_requested`;
export const CHANNEL_SWEEP_COMPLETED = `${MTUS_CHANNEL_PREFIX}sweep_completed`;
export const CHANNEL_CONFIG_UPDATED = `${MTUS_CHANNEL_PREFIX}config_updated`;

// Social Channels
export const CHANNEL_SOCIAL_SCORED = `${MTUS_CHANNEL_PREFIX}social_scored`;

/**
 * Maps an EventType string to its prefixed channel name.
 * Use this when you have a dynamic event type and need the channel.
 */
export function eventTypeToChannel(eventType: string): string {
  return `${MTUS_CHANNEL_PREFIX}${eventType}`;
}
