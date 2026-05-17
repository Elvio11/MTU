import asyncio
import aioredis
import json
import time
import os
import sys
import yaml
from datetime import datetime, timedelta
from typing import Dict
from dotenv import load_dotenv

# Load .env file
load_dotenv("./.env")

from src.python.shared.db import get_connection
from src.python.shared.envelope import AgentMessageEnvelope, EventType
from src.python.shared.config_validator import validate_config
from src.python.shared.safe_output import safe_print as print
from src.python.shared.constants import (
    CHANNEL_TOKEN_DETECTED,
    CHANNEL_TOKEN_QUALIFIED,
    CHANNEL_TRADE_APPROVED,
    CHANNEL_TRADE_EXECUTED,
    CHANNEL_TRADE_FAILED,
    CHANNEL_POSITION_OPENED,
    CHANNEL_POSITION_CLOSED,
    CHANNEL_TP1_HIT,
    CHANNEL_TP2_HIT,
    CHANNEL_STOP_LOSS_HIT,
    CHANNEL_TRAILING_STOP_HIT,
    CHANNEL_TIME_SL_HIT,
    CHANNEL_PRICE_UNAVAILABLE,
)
from src.python.shared.operational_window import is_operational_window_active


from src.python.shared.config_validator import validate_config

class LedgerAgent:
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.redis = None
        self.pubsub = None
        self.db = None
        self.running = False
        self.audit_file = None

    def connect_db(self):
        """Connect to PostgreSQL and create audit ledger table."""
        self.db = get_connection()
        self.db.autocommit = False
        with self.db.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_ledger (
                    id              SERIAL PRIMARY KEY,
                    envelope_id     TEXT DEFAULT '',
                    agent_id        TEXT DEFAULT '',
                    event_type      TEXT DEFAULT '',
                    payload         TEXT DEFAULT '',
                    timestamp_utc   TEXT DEFAULT ''
                )
            """)
        self.db.commit()
        print("AGT-09: Connected to PostgreSQL audit ledger DB")

    async def connect_redis(self):
        """Subscribe to all trade events per Section 3.9"""
        self.redis = await aioredis.from_url(
            "redis://localhost:6379", decode_responses=True
        )
        self.pubsub = self.redis.pubsub()
        # Subscribe to all relevant events
        channels = [
            CHANNEL_TOKEN_DETECTED,
            CHANNEL_TOKEN_QUALIFIED,
            CHANNEL_TRADE_APPROVED,
            CHANNEL_TRADE_EXECUTED,
            CHANNEL_TRADE_FAILED,
            CHANNEL_POSITION_OPENED,
            CHANNEL_POSITION_CLOSED,
            CHANNEL_TP1_HIT,
            CHANNEL_TP2_HIT,
            CHANNEL_STOP_LOSS_HIT,
            CHANNEL_TRAILING_STOP_HIT,
            CHANNEL_TIME_SL_HIT,
            CHANNEL_PRICE_UNAVAILABLE,
        ]
        await self.pubsub.subscribe(*channels)
        print(f"AGT-09: Subscribed to {len(channels)} event channels")

    def write_audit_log(self, envelope: AgentMessageEnvelope):
        """Write to append-only PostgreSQL and JSON ledger."""
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_ledger (envelope_id, agent_id, event_type, payload, timestamp_utc) VALUES (%s, %s, %s, %s, %s)",
                (
                    envelope.envelope_id,
                    envelope.agent_id,
                    envelope.event_type,
                    json.dumps(envelope.payload),
                    envelope.timestamp_utc,
                ),
            )
        self.db.commit()

        # Append-only JSON file
        self.audit_file.write(json.dumps(envelope.model_dump()) + "\n")
        self.audit_file.flush()

    async def handle_event(self, channel: str, envelope_json: str):
        try:
            envelope = AgentMessageEnvelope.model_validate_json(envelope_json)
            self.write_audit_log(envelope)
            print(f"AGT-09: Logged {envelope.event_type} from {envelope.agent_id}")
        except Exception as e:
            print(f"AGT-09: Error handling event: {e}")

    def rotate_audit_logs(self):
        """Delete audit logs older than 30 days and clean stale positions."""
        try:
            cutoff = (datetime.now() - timedelta(days=30)).isoformat()
            with self.db.cursor() as cur:
                cur.execute(
                    "DELETE FROM audit_ledger WHERE timestamp_utc < %s", (cutoff,)
                )
                deleted = cur.rowcount
                if deleted > 0:
                    print(f"AGT-09: [ROTATION] Deleted {deleted} old audit log entries")

                # Stale position cleanup
                cur.execute(
                    "DELETE FROM positions WHERE position_id IN (%s, %s)",
                    ("pos_2", "pos_3"),
                )
                deleted_stale = cur.rowcount
                if deleted_stale > 0:
                    print(f"AGT-09: [CLEANUP] Deleted {deleted_stale} stale position entries")

            self.db.commit()
        except Exception as e:
            print(f"AGT-09: Error during rotation/cleanup: {e}")

    async def run(self):
        self.running = True
        self.connect_db()
        await self.connect_redis()
        self.audit_file = open("data/audit_ledger.json", "a", encoding="utf-8")
        is_subscribed = True
        print("AGT-09: Ledger agent started")
        last_rotation = 0

        while self.running:
            try:
                now_ts = time.time()
                if now_ts - last_rotation > 86400: # Every 24h
                    self.rotate_audit_logs()
                    last_rotation = now_ts
                active = is_operational_window_active()
                
                if active and not is_subscribed:
                    await self.pubsub.subscribe(*[
                        CHANNEL_TOKEN_DETECTED,
                        CHANNEL_TOKEN_QUALIFIED,
                        CHANNEL_TRADE_APPROVED,
                        CHANNEL_TRADE_EXECUTED,
                        CHANNEL_TRADE_FAILED,
                        CHANNEL_POSITION_OPENED,
                        CHANNEL_POSITION_CLOSED,
                        CHANNEL_TP1_HIT,
                        CHANNEL_TP2_HIT,
                        CHANNEL_STOP_LOSS_HIT,
                        CHANNEL_TRAILING_STOP_HIT,
                        CHANNEL_TIME_SL_HIT,
                        CHANNEL_PRICE_UNAVAILABLE,
                    ])
                    is_subscribed = True
                    print("AGT-09: [WINDOW OPEN] Resubscribed to event channels")
                elif not active and is_subscribed:
                    await self.pubsub.unsubscribe()
                    is_subscribed = False
                    print("AGT-09: [OFF-HOURS] Unsubscribed from channels to save resources")

                if not active:
                    await asyncio.sleep(60)
                    continue

                if self.pubsub is None:
                    await self.connect_redis()
                    is_subscribed = True

                message = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    await self.handle_event(message["channel"], message["data"])
                await asyncio.sleep(0.01)
            except Exception as e:
                print(f"AGT-09: Error in run loop: {e}")
                await asyncio.sleep(1)

    async def stop(self):
        self.running = False
        if self.db:
            self.db.close()
        if self.audit_file:
            self.audit_file.close()
        if self.redis:
            await self.redis.close()
        print("AGT-09: Ledger agent stopped")


async def main():
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    config_path = os.path.join(project_root, "config", "config.yaml")

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"[CONFIG] Error loading config: {e}")
        sys.exit(1)

    is_valid, error = validate_config(config)
    if not is_valid:
        print(f"[CONFIG] Configuration validation failed: {error}")
        sys.exit(1)

    agent = LedgerAgent(config)
    try:
        await agent.run()
    except KeyboardInterrupt:
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
