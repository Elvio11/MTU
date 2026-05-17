import asyncio
import aioredis
import json
import os
import sys
import yaml
from typing import Dict
from dotenv import load_dotenv

load_dotenv("./.env")

from src.python.shared.db import get_connection
from src.python.shared.envelope import AgentMessageEnvelope
from src.python.shared.constants import (
    CHANNEL_POSITION_CLOSED,
    KEY_POSITION_SIZE_SOL,
    AGENT_LEDGER,
)
from src.python.shared.operational_window import is_operational_window_active
from src.python.shared.config_validator import validate_config
from src.python.shared.safe_output import safe_print as print

class PortfolioSizerAgent:
    """
    AGT-12: Dynamic Portfolio Sizer
    Listens to position closures, calculates cumulative PnL, and updates position size.
    """
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.redis = None
        self.pubsub = None
        self.running = False
        
        # Sizing parameters
        trading_cfg = self.config.get("trading", {})
        self.base_size = trading_cfg.get("position_size_sol", 0.0005)
        self.max_size = trading_cfg.get("max_position_size_sol", 0.01)
        self.compounding_pct = trading_cfg.get("compounding_pct", 0.1) 
        self.growth_enabled = trading_cfg.get("dynamic_growth_enabled", False)

    async def connect_redis(self):
        self.redis = await aioredis.from_url(
            self.config.get("redis", {}).get("url", "redis://localhost:6379"), 
            decode_responses=True
        )
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe(CHANNEL_POSITION_CLOSED)
        print(f"AGT-12: PortfolioSizerAgent subscribed to {CHANNEL_POSITION_CLOSED}")

    def calculate_new_size(self):
        """Query PostgreSQL for cumulative realized PnL and apply growth formula."""
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT SUM(realised_pnl_sol) FROM positions WHERE state = 'CLOSED'"
                )
                row = cur.fetchone()
                total_pnl = (row["sum"] if row and row["sum"] is not None else 0.0)
            conn.close()

            if not self.growth_enabled:
                return self.base_size

            if total_pnl <= 0:
                return self.base_size

            # Growth formula: Base + (Compounding % * Realized PnL)
            growth = total_pnl * self.compounding_pct
            new_size = self.base_size + growth
            
            # Cap at max_size
            return min(new_size, self.max_size)
        except Exception as e:
            print(f"AGT-12: Error calculating size: {e}")
            return self.base_size

    async def update_redis_config(self):
        """Update Redis with the calculated dynamic size."""
        try:
            new_size = self.calculate_new_size()
            await self.redis.set(KEY_POSITION_SIZE_SOL, str(new_size))
            print(f"AGT-12: Position size updated to {new_size:.6f} SOL based on performance")
        except Exception as e:
            print(f"AGT-12: Error updating Redis config: {e}")

    async def run(self):
        self.running = True
        await self.connect_redis()
        
        # Initial sizing
        await self.update_redis_config()
        
        print("AGT-12: PortfolioSizerAgent started")

        while self.running:
            try:
                active = is_operational_window_active()
                
                message = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    # Position closed event received
                    print("AGT-12: Position closure detected, recalculating sizing...")
                    await self.update_redis_config()
                
                await asyncio.sleep(0.1 if active else 5.0)
                
            except Exception as e:
                print(f"AGT-12: Error in run loop: {e}")
                await asyncio.sleep(1)

    async def stop(self):
        self.running = False
        if self.pubsub:
            await self.pubsub.unsubscribe()
        if self.redis:
            await self.redis.close()
        print("AGT-12: PortfolioSizerAgent stopped")

async def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
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
    
    agent = PortfolioSizerAgent(config)
    try:
        await agent.run()
    except KeyboardInterrupt:
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
