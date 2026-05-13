import asyncio
import aioredis
import json
import os
import sys
import yaml
from typing import Dict, Any
from dotenv import load_dotenv
from src.python.shared.config_validator import validate_config
from src.python.shared.safe_output import safe_print as print

load_dotenv("./.env")

from src.python.shared.envelope import AgentMessageEnvelope, EventType
from src.python.shared.priority_queue import PriorityQueue
from src.python.shared.operational_window import is_operational_window_active
from src.python.shared.constants import (
    CHANNEL_TOKEN_RECEIVED,
    CHANNEL_TOKEN_RECEIVED_SOCIAL,
    EVENT_TOKEN_RECEIVED,
    EVENT_TOKEN_RECEIVED_SOCIAL,
)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


class HermesAgent:
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.redis = None
        self.pubsub = None
        self.running = False
        self.priority_queue = None

    async def connect_redis(self):
        self.redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
        self.priority_queue = PriorityQueue(self.redis)
        print("AGT-02: Connected to Redis and Priority Queue")

    async def handle_token_detected(self, envelope_json: str):
        try:
            envelope = AgentMessageEnvelope.model_validate_json(envelope_json)
            token_payload = envelope.payload
            correlation_id = envelope.correlation_id

            safety_envelope = AgentMessageEnvelope(
                agent_id="AGT-02",
                event_type=EVENT_TOKEN_RECEIVED,
                payload=token_payload,
                correlation_id=correlation_id,
            )
            await self.redis.publish(
                CHANNEL_TOKEN_RECEIVED, safety_envelope.model_dump_json()
            )
            await self.redis.lpush(
                f"event:{EVENT_TOKEN_RECEIVED}:0", safety_envelope.model_dump_json()
            )

            social_envelope = AgentMessageEnvelope(
                agent_id="AGT-02",
                event_type=EVENT_TOKEN_RECEIVED_SOCIAL,
                payload=token_payload,
                correlation_id=correlation_id,
            )
            await self.redis.publish(
                CHANNEL_TOKEN_RECEIVED_SOCIAL, social_envelope.model_dump_json()
            )
            await self.redis.lpush(
                f"event:{EVENT_TOKEN_RECEIVED_SOCIAL}:0",
                social_envelope.model_dump_json(),
            )

            print(
                f"AGT-02: Routed {token_payload.get('symbol')} to Anansi and Cassandra"
            )
        except Exception as e:
            print(f"AGT-02: Error handling token_detected: {e}")

    async def handle_token_migrated(self, envelope_json: str):
        try:
            envelope = AgentMessageEnvelope.model_validate_json(envelope_json)
            token_payload = envelope.payload
            correlation_id = envelope.correlation_id

            standardized_payload = {
                "mint": token_payload.get("mint"),
                "name": token_payload.get("name", "Unknown"),
                "symbol": token_payload.get("symbol", "UNK"),
                "program": token_payload.get("program", "unknown"),
                "signature": token_payload.get("signature", ""),
                "uri": token_payload.get("uri", ""),
            }

            safety_envelope = AgentMessageEnvelope(
                agent_id="AGT-02",
                event_type=EVENT_TOKEN_RECEIVED,
                payload=standardized_payload,
                correlation_id=correlation_id,
            )
            await self.redis.publish(
                CHANNEL_TOKEN_RECEIVED, safety_envelope.model_dump_json()
            )
            await self.redis.lpush(
                f"event:{EVENT_TOKEN_RECEIVED}:0", safety_envelope.model_dump_json()
            )

            social_envelope = AgentMessageEnvelope(
                agent_id="AGT-02",
                event_type=EVENT_TOKEN_RECEIVED_SOCIAL,
                payload=standardized_payload,
                correlation_id=correlation_id,
            )
            await self.redis.publish(
                CHANNEL_TOKEN_RECEIVED_SOCIAL, social_envelope.model_dump_json()
            )
            await self.redis.lpush(
                f"event:{EVENT_TOKEN_RECEIVED_SOCIAL}:0",
                social_envelope.model_dump_json(),
            )

            print(
                f"AGT-02: Routed migrated token {token_payload.get('mint', '')[:8]}... to Anansi and Cassandra"
            )
        except Exception as e:
            print(f"AGT-02: Error handling token_migrated: {e}")

    async def run(self):
        await self.connect_redis()
        self.running = True
        print("AGT-02: Starting queue processor...")

        while self.running:
            try:
                if not is_operational_window_active():
                    await asyncio.sleep(60)
                    continue

                result = await self.priority_queue.dequeue()

                if result:
                    data_dict, priority = result
                    if isinstance(data_dict, dict):
                        envelope_json = json.dumps(data_dict)
                    else:
                        envelope_json = data_dict

                    await self.handle_token_detected(envelope_json)
                    print(f"AGT-02: Processed priority {priority} item from queue")
                else:
                    await asyncio.sleep(0.1)

            except Exception as e:
                print(f"AGT-02: Error in queue processing: {e}")
                await asyncio.sleep(1)

    async def stop(self):
        self.running = False
        if self.pubsub:
            await self.pubsub.unsubscribe()
        if self.redis:
            await self.redis.close()


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

    agent = HermesAgent(config)
    try:
        await agent.run()
    except KeyboardInterrupt:
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
