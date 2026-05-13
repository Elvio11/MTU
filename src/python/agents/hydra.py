import asyncio
import aioredis
import json
import os
import sys
import yaml
import time
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from src.python.shared.api_manager import GlobalApiManager, ApiProvider
from src.python.shared.config_validator import validate_config
from src.python.shared.safe_output import safe_print as print
from src.python.shared.envelope import AgentMessageEnvelope, EventType
from src.python.shared.constants import (
    CHANNEL_TOKEN_RECEIVED,
    EVENT_TOKEN_RECEIVED,
)
from src.python.shared.bonding_curve import decode_bonding_curve, calculate_progress
from src.python.shared.operational_window import is_operational_window_active

load_dotenv("./.env")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SOLANA_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
PUMPFUN_API_URL = "https://frontend-api-v3.pump.fun/coins"
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

        # Initialize API Manager
        self.api_manager = GlobalApiManager()
        self.api_manager.setup_router("discovery", [
            ApiProvider("pumpfun", PUMPFUN_API_URL, weight=100, capacity=20, refill_rate=2, headers={
                "Origin": "https://pump.fun",
                "Referer": "https://pump.fun/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json"
            })
        ])

    async def connect_redis(self):
        self.redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
        print("AGT-12: Connected to Redis")

    async def fetch_trending_pumpfun(self) -> List[Dict[str, Any]]:
        """Fetch trending tokens from Pump.fun frontend API"""
        try:
            params = {
                "offset": 0,
                "limit": 50,
                "sort": "last_reply", # Alternative sorting
                "order": "DESC",
                "includeNsfw": "false"
            }
            data = await self.api_manager.request("discovery", "GET", provider="pumpfun", params=params, timeout=10)
            if data and isinstance(data, list):
                return data
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

        # Calculate progress from virtual_sol_reserves
        reserves = token_data.get("virtual_sol_reserves", 30000000000)
        current_progress = ((reserves - 30000000000) / 55000000000) * 100
        
        # We ONLY want tokens still on the bonding curve (below 100%)
        # And within the user's specific 15-65% target window
        min_p = self.min_progress
        max_p = self.config.get("qualification", {}).get("max_bonding_curve_progress", 65.0)
        
        if min_p <= current_progress <= max_p:
            print(f"AGT-12: Trending token identified: {token_data.get('symbol', '???')} ({mint[:8]}) Progress: {current_progress:.2f}%")
            
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
                    "market_cap_usd": token_data.get("usd_market_cap", 0),
                    "v_sol_in_bonding_curve": reserves / 1_000_000_000,
                    "is_pump": True,
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
                # Check operational window
                if not is_operational_window_active():
                    print("AGT-12: [OFF-HOURS] Outside operational window. Sleeping for 60s...")
                    await asyncio.sleep(60)
                    continue

                # 1. Fetch Trending from Pump.fun
                trending = await self.fetch_trending_pumpfun()
                # print(f"AGT-12: Polled {len(trending)} trending tokens") # Optional: very verbose
                
                for token in trending:
                    await self.process_token(token)
                
                if len(trending) > 0:
                    # Heartbeat log every successful fetch
                    print(f"AGT-12: Poller heartbeat - {len(trending)} tokens scanned from trending.") 

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
    
    agent = HydraAgent(config)
    try:
        await agent.run()
    except KeyboardInterrupt:
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
