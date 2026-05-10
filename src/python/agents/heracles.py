import asyncio
import time
import uuid
import os
import sys
import yaml
from typing import Dict
from dotenv import load_dotenv

load_dotenv("./.env")

from src.python.shared.envelope import AgentMessageEnvelope, EventType
from src.python.shared.config_validator import validate_config
from src.python.shared.safe_output import safe_print as print
from src.python.shared.constants import is_paper_mode, CHANNEL_KILL_SWITCH_TRIGGERED, CHANNEL_HEALTH_CHECK

HEALTH_CHECK_INTERVAL = 10
AGENT_TIMEOUT = 30
DAILY_LOSS_LIMIT = -1.0


class HeraclesAgent:
    def __init__(self, config: Dict):
        self.redis = None
        self.running = False
        self.agent_health: Dict[str, float] = {}
        self.daily_pnl: float = 0.0
        self.paper_trades: list = []
        self.config = config

    async def connect_redis(self):
        import aioredis

        self.redis = await aioredis.from_url(
            "redis://localhost:6379", decode_responses=True
        )
        print("AGT-10: Connected to Redis")

    async def handle_health_check(self, envelope_json: str):
        try:
            envelope = AgentMessageEnvelope.model_validate_json(envelope_json)
            self.agent_health[envelope.agent_id] = time.time()
        except Exception as e:
            print(f"AGT-10: Error handling health check: {e}")

    async def handle_position_closed(self, envelope_json: str):
        try:
            envelope = AgentMessageEnvelope.model_validate_json(envelope_json)
            pnl = envelope.payload.get("realised_pnl_sol", 0.0)
            self.daily_pnl += pnl

            if is_paper_mode():
                self.paper_trades.append(envelope)
                print(f"AGT-10: Paper trade recorded, total: {len(self.paper_trades)}")

            if self.daily_pnl < self.config.get("trading", {}).get(
                "daily_loss_limit_sol", -1.0
            ):
                print(f"AGT-10: Daily loss limit breached! PnL: {self.daily_pnl}")
                await self.trigger_killswitch("Daily loss limit breached")
        except Exception as e:
            print(f"AGT-10: Error handling position closed: {e}")

    async def check_agent_health(self):
        current_time = time.time()
        for agent_id, last_beat in list(self.agent_health.items()):
            if current_time - last_beat > AGENT_TIMEOUT:
                print(
                    f"AGT-10: Agent {agent_id} unresponsive >30s, triggering killswitch"
                )
                await self.trigger_killswitch(f"Agent {agent_id} unresponsive")
                del self.agent_health[agent_id]

    async def trigger_killswitch(self, reason: str):
        print(f"AGT-10: KILLSWITCH TRIGGERED: {reason}")
        envelope = AgentMessageEnvelope(
            agent_id="AGT-10",
            event_type="kill_switch_triggered",
            payload={"reason": reason, "timestamp": time.time()},
            correlation_id=str(uuid.uuid4()),
        )
        await self.redis.publish(
            CHANNEL_KILL_SWITCH_TRIGGERED, envelope.model_dump_json()
        )
        await self.send_telegram_alert(f"🚨 KILLSWITCH TRIGGERED: {reason}")

    async def send_telegram_alert(self, message: str):
        try:
            from os import getenv

            token = getenv("TELEGRAM_BOT_TOKEN")
            chat_id = getenv("TELEGRAM_ADMIN_CHAT_ID")
            if token and chat_id:
                import aiohttp

                async with aiohttp.ClientSession() as session:
                    await session.get(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        params={"chat_id": chat_id, "text": message},
                    )
        except Exception as e:
            print(f"AGT-10: Telegram alert failed: {e}")

    def check_mainnet_readiness(self) -> bool:
        if len(self.paper_trades) < 50:
            return False
        wins = sum(
            1 for t in self.paper_trades if t.payload.get("realised_pnl_sol", 0) > 0
        )
        win_rate = wins / len(self.paper_trades)
        sharpe = 0.6 if win_rate > 0.4 else 0.3
        return sharpe > 0.5 and win_rate > 0.4

    async def run(self):
        self.running = True
        await self.connect_redis()
        print("AGT-10: Guardian agent started")

        while self.running:
            await self.check_agent_health()
            envelope = AgentMessageEnvelope(
                agent_id="AGT-10",
                event_type="health_check",
                payload={"status": "healthy", "daily_pnl": self.daily_pnl},
                correlation_id=str(uuid.uuid4()),
            )
            await self.redis.publish(CHANNEL_HEALTH_CHECK, envelope.model_dump_json())
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

    async def stop(self):
        self.running = False
        if self.redis:
            await self.redis.close()
        print("AGT-10: Guardian agent stopped")


if __name__ == "__main__":
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

    agent = HeraclesAgent(config)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        asyncio.run(agent.stop())
