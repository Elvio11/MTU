import asyncio
import aioredis
import json
import time
import sqlite3
import os
from typing import Dict
from dotenv import load_dotenv

# Load .env file
load_dotenv("./.env")

from src.python.shared.envelope import AgentMessageEnvelope, EventType
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


class LedgerAgent:
    def __init__(self):
        self.redis = None
        self.pubsub = None
        self.db = None
        self.running = False
        self.audit_file = None

    def connect_db(self):
        """Connect to SQLite and create audit ledger table per Section 5.1"""
        self.db = sqlite3.connect("data/positions.db")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS audit_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                envelope_id TEXT,
                agent_id TEXT,
                event_type TEXT,
                payload TEXT,
                timestamp_utc TEXT
            )
        """)
        self.db.commit()
        print("AGT-09: Connected to audit ledger DB")

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
        """Write to append-only SQLite and JSON ledger per Section 5.1"""
        # SQLite write
        self.db.execute(
            "INSERT INTO audit_ledger (envelope_id, agent_id, event_type, payload, timestamp_utc) VALUES (?, ?, ?, ?, ?)",
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

    async def run(self):
        self.running = True
        self.connect_db()
        self.audit_file = open("data/audit_ledger.json", "a", encoding="utf-8")
        await self.connect_redis()
        print("AGT-09: Ledger agent started")

        while self.running:
            try:
                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message:
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


if __name__ == "__main__":
    agent = LedgerAgent()
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        asyncio.run(agent.stop())
