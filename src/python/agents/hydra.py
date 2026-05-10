import asyncio
import aioredis
import json
import requests
import os
import sys
import yaml
import time
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from src.python.shared.config_validator import validate_config
from src.python.shared.safe_output import safe_print as print
from src.python.shared.envelope import AgentMessageEnvelope, EventType
from src.python.shared.constants import (
    CHANNEL_TOKEN_RECEIVED,
    EVENT_TOKEN_RECEIVED,
)
from src.python.shared.bonding_curve import decode_bonding_curve, calculate_progress

load_dotenv("./.env")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SOLANA_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
PUMPFUN_API_URL = "https://frontend-api.pump.fun/coins"
DEXSCREENER_API_URL = "https://api.dexscreener.com/token-profiles/latest/v1"

class HydraAgent:
    """
    AGT-12: Hydra Monitoring Agent
    Responsible for identifying trending tokens and monitoring bonding curve progression.
    """
    def __init__(self, config: Dict[str, Any]):
        self.redis = None
        self.running = False
        self.config = config
        self.rpc_url = SOLANA_RPC_URL
        self._processed_mints = set()
        self.polling_interval = config.get("hydra", {}).get("polling_interval_seconds", 30)
        self.min_progress = config.get("hydra", {}).get("min_bonding_curve_progress", 35.0)

    async def connect_redis(self):
        self.redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
        print("AGT-12: Connected to Redis")

    async def fetch_trending_pumpfun(self) -> List[Dict[str, Any]]:
        """Fetch trending tokens from Pump.fun frontend API"""
        try:
            # Sort by market cap or last reply to find trending
            params = {
                "offset": 0,
                "limit": 50,
                "sort": "market_cap",
                "order": "DESC",
                "includeNsfw": "false"
            }
            resp = requests.get(PUMPFUN_API_URL, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            print(f"AGT-12: Error fetching trending from Pump.fun: {e}")
            return []

    async def get_bonding_curve_data(self, mint: str) -> Optional[Dict[str, Any]]:
        """Fetch bonding curve account data from Solana RPC"""
        if not self.rpc_url:
            return None
            
        try:
            # We need the bonding curve address. For Pump.fun tokens, it's a PDA.
            # Simplified: Use the mint to find account info.
            # In a real scenario, we'd derive the PDA or use the 'bonding_curve' field from API.
            # For now, we'll assume we can get it or use a lookup.
            return None # Placeholder for actual RPC lookup
        except Exception as e:
            print(f"AGT-12: Error fetching bonding curve for {mint}: {e}")
            return None

    async def process_token(self, token_data: Dict[str, Any]):
        """Process a potential candidate token"""
        mint = token_data.get("mint")
        if not mint or mint in self._processed_mints:
            return

        # Calculate progress from API data if available, otherwise fallback to RPC
        progress = token_data.get("raydium_pool") # Some APIs flag migration status
        
        # Pump.fun API usually provides 'usd_market_cap' and 'progress'
        # Progress is often calculated on their frontend.
        current_progress = token_data.get("progress", 0)
        
        if current_progress >= self.min_progress:
            print(f"AGT-12: Trending token identified: {mint[:10]}... Progress: {current_progress:.2f}%")
            
            # Construct discovery envelope
            envelope = AgentMessageEnvelope(
                agent_id="AGT-12",
                event_type=EVENT_TOKEN_RECEIVED,
                payload={
                    "mint": mint,
                    "symbol": token_data.get("symbol", "UNKNOWN"),
                    "name": token_data.get("name", "Unknown Token"),
                    "bonding_curve_progress": current_progress,
                    "market_cap": token_data.get("usd_market_cap", 0),
                    "is_trending": True,
                    "timestamp": time.time()
                }
            )
            
            await self.redis.publish(CHANNEL_TOKEN_RECEIVED, envelope.model_dump_json())
            # Keep set size manageable
            if len(self._processed_mints) >= 1000:
                self._processed_mints.clear()
            self._processed_mints.add(mint)

    async def run(self):
        self.running = True
        await self.connect_redis()
        
        print(f"AGT-12: Hydra Monitoring Agent started (Min Progress: {self.min_progress}%)")
        
        while self.running:
            try:
                # 1. Fetch Trending from Pump.fun
                trending = await self.fetch_trending_pumpfun()
                for token in trending:
                    await self.process_token(token)
                
                await asyncio.sleep(self.polling_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"AGT-12: Run loop error: {e}")
                await asyncio.sleep(10)

    async def stop(self):
        self.running = False
        if self.redis:
            await self.redis.close()

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
    
    agent = HydraAgent(config)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        asyncio.run(agent.stop())
