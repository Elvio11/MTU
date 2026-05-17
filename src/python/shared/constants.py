"""
Constants module for MTUS Trading System.
Section 6.1: Centralized constants for Redis keys, channels, and configuration.
"""

import os
from typing import Dict, Any

# =============================================================================
# Environment Functions (replaces module-level variables)
# =============================================================================


def is_paper_mode() -> bool:
    """Check if running in paper trading mode."""
    return os.getenv("MTUS_ENVIRONMENT", "paper").lower() == "paper"


# =============================================================================
# Redis Key Prefixes - All keys should use mtus: prefix
# =============================================================================

MTUS_PREFIX = "mtus:"

# System State Keys
REDIS_KEY_KILL_SWITCH = f"{MTUS_PREFIX}kill_switch"
REDIS_KEY_TRADING_ACTIVE = f"{MTUS_PREFIX}trading_active"
REDIS_KEY_TRADING_PAUSED = f"{MTUS_PREFIX}trading_paused"
REDIS_KEY_SYSTEM_STATE = f"{MTUS_PREFIX}system_state"
REDIS_KEY_KILL_SWITCH_TRIGGERED = f"{MTUS_PREFIX}kill_switch_triggered"

# Position Keys
REDIS_KEY_POSITION_PREFIX = f"{MTUS_PREFIX}position:"  # Use with position_id
REDIS_KEY_POSITION_CLOSED_PREFIX = (
    f"{MTUS_PREFIX}position_closed:"  # Use with position_id
)
KEY_ALL_ACTIVE_POSITIONS = f"{MTUS_PREFIX}active_positions"
KEY_ALL_POSITIONS = "position:*"
KEY_ALL_CLOSED_POSITIONS = "position_closed:*"

# Trade Queue Keys
KEY_TRADE_QUEUE = f"{MTUS_PREFIX}trade_queue"
KEY_TRADE_COUNT = f"{MTUS_PREFIX}trade_count"

# Config Keys
KEY_POSITION_SIZE_SOL = f"{MTUS_PREFIX}position_size_sol"
KEY_MAX_POSITIONS = f"{MTUS_PREFIX}max_positions"
KEY_TP1_MULTIPLIER = f"{MTUS_PREFIX}tp1_multiplier"
KEY_TP2_MULTIPLIER = f"{MTUS_PREFIX}tp2_multiplier"
KEY_SL_MULTIPLIER = f"{MTUS_PREFIX}sl_multiplier"

# Deduplication Keys
KEY_DEDUP_PREFIX = f"{MTUS_PREFIX}dedup:"  # Use with mint


# =============================================================================
# Pub/Sub Channel Names - All channels use mtus:channel: prefix
# =============================================================================

MTUS_CHANNEL_PREFIX = f"{MTUS_PREFIX}channel:"

# Token Channels
CHANNEL_TOKEN_DETECTED = f"{MTUS_CHANNEL_PREFIX}token_detected"
CHANNEL_TOKEN_RECEIVED = f"{MTUS_CHANNEL_PREFIX}token_received"
CHANNEL_TOKEN_RECEIVED_SOCIAL = f"{MTUS_CHANNEL_PREFIX}token_received_social"
CHANNEL_TOKEN_QUALIFIED = f"{MTUS_CHANNEL_PREFIX}token_qualified"
CHANNEL_TOKEN_GRADATED = f"{MTUS_CHANNEL_PREFIX}token_gradated"
CHANNEL_TOKEN_MIGRATED = f"{MTUS_CHANNEL_PREFIX}token_migrated"
CHANNEL_TOKEN_TA_SCORED = f"{MTUS_CHANNEL_PREFIX}token_ta_scored"

# Trade Channels
CHANNEL_TRADE_APPROVED = f"{MTUS_CHANNEL_PREFIX}trade_approved"
CHANNEL_TRADE_EXECUTED = f"{MTUS_CHANNEL_PREFIX}trade_executed"
CHANNEL_TRADE_FAILED = f"{MTUS_CHANNEL_PREFIX}trade_failed"

# Position Channels
CHANNEL_POSITION_OPENED = f"{MTUS_CHANNEL_PREFIX}position_opened"
CHANNEL_POSITION_CLOSED = f"{MTUS_CHANNEL_PREFIX}position_closed"

# Price Channels
CHANNEL_PRICE_UPDATED = f"{MTUS_CHANNEL_PREFIX}price_updated"
CHANNEL_PRICE_UNAVAILABLE = f"{MTUS_CHANNEL_PREFIX}price_unavailable"

# System Channels
CHANNEL_HEALTH_CHECK = f"{MTUS_CHANNEL_PREFIX}health_check"
CHANNEL_SYSTEM_ALERT = f"{MTUS_CHANNEL_PREFIX}system_alert"
CHANNEL_KILL_SWITCH_TRIGGERED = f"{MTUS_CHANNEL_PREFIX}kill_switch_triggered"

# Trading Control Channels
CHANNEL_TRADING_PAUSED = f"{MTUS_CHANNEL_PREFIX}trading_paused"
CHANNEL_TRADING_RESUMED = f"{MTUS_CHANNEL_PREFIX}trading_resumed"

# Event Channels (for ledger)
CHANNEL_TP1_HIT = f"{MTUS_CHANNEL_PREFIX}tp1_hit"
CHANNEL_TP2_HIT = f"{MTUS_CHANNEL_PREFIX}tp2_hit"
CHANNEL_STOP_LOSS_HIT = f"{MTUS_CHANNEL_PREFIX}stop_loss_hit"
CHANNEL_TRAILING_STOP_HIT = f"{MTUS_CHANNEL_PREFIX}trailing_stop_hit"
CHANNEL_TIME_SL_HIT = f"{MTUS_CHANNEL_PREFIX}time_sl_hit"
CHANNEL_MANUAL_EXIT = f"{MTUS_CHANNEL_PREFIX}manual_exit"

# Admin Channels
CHANNEL_SWEEP_REQUESTED = f"{MTUS_CHANNEL_PREFIX}sweep_requested"
CHANNEL_SWEEP_COMPLETED = f"{MTUS_CHANNEL_PREFIX}sweep_completed"
CHANNEL_CONFIG_UPDATED = f"{MTUS_CHANNEL_PREFIX}config_updated"

# Social Channels
CHANNEL_SOCIAL_SCORED = f"{MTUS_CHANNEL_PREFIX}social_scored"


# =============================================================================
# Event Type Names (for AgentMessageEnvelope)
# =============================================================================

EVENT_TOKEN_DETECTED = "token_detected"
EVENT_TOKEN_QUALIFIED = "token_qualified"
EVENT_TOKEN_RECEIVED = "token_received"
EVENT_SAFETY_CHECKED = "safety_checked"
EVENT_PRICE_UPDATED = "price_updated"
EVENT_TRADE_APPROVED = "trade_approved"
EVENT_TRADE_EXECUTED = "trade_executed"
EVENT_TRADE_FAILED = "trade_failed"
EVENT_POSITION_OPENED = "position_opened"
EVENT_POSITION_CLOSED = "position_closed"
EVENT_TP1_HIT = "tp1_hit"
EVENT_TP2_HIT = "tp2_hit"
EVENT_STOP_LOSS_HIT = "stop_loss_hit"
EVENT_TRAILING_STOP_HIT = "trailing_stop_hit"
EVENT_TIME_SL_HIT = "time_sl_hit"
EVENT_MANUAL_EXIT = "manual_exit"
EVENT_SWEEP_REQUESTED = "sweep_requested"
EVENT_SWEEP_COMPLETED = "sweep_completed"
EVENT_HEALTH_CHECK = "health_check"
EVENT_SYSTEM_ALERT = "system_alert"
EVENT_TOKEN_GRADATED = "token_gradated"
EVENT_PRICE_UNAVAILABLE = "price_unavailable"
EVENT_TOKEN_RECEIVED_SOCIAL = "token_received_social"
EVENT_SOCIAL_SCORED = "social_scored"
EVENT_KILL_SWITCH_TRIGGERED = "kill_switch_triggered"
EVENT_TOKEN_TA_SCORED = "token_ta_scored"
EVENT_TOKEN_MIGRATED = "token_migrated"


# =============================================================================
# Agent IDs
# =============================================================================

AGENT_NOFX = "AGT-01"  # Token detection
AGENT_HERMES = "AGT-02"  # Queue routing
AGENT_ANANSI = "AGT-03"  # Safety qualification
AGENT_ORACLE = "AGT-04"  # Price feeds
AGENT_ARES = "AGT-05"  # Trade execution (Ares)
AGENT_SENTINEL = "AGT-06"  # TP/SL monitoring and position management
AGENT_JANUS = "AGT-07"  # Balance sweep and wallet management
AGENT_CASSANDRA = "AGT-08"  # Social scoring
AGENT_LEDGER = "AGT-09"  # Audit ledger
AGENT_HERACLES = "AGT-10"  # Guardian/health (killswitch)
AGENT_DASHBOARD_BRIDGE = "AGT-11"  # Dashboard WebSocket


# =============================================================================
# Default Configuration Values
# =============================================================================

DEFAULT_REDIS_URL = "redis://localhost:6379"
DEFAULT_POLLING_INTERVAL = 5
DEFAULT_MAX_CONSECUTIVE_FAILURES = 3
DEFAULT_RECONNECT_BASE_DELAY = 1
DEFAULT_RECONNECT_MAX_DELAY = 30
DEFAULT_MAX_EVENTS_PER_SECOND = 10
DEFAULT_AGENT_TIMEOUT = 30
DEFAULT_HEALTH_CHECK_INTERVAL = 10
DEFAULT_DAILY_LOSS_LIMIT = -1.0
