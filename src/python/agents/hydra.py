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
DEXSCREENER_PROFILES_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
DEXSCREENER_BOOSTS_URL = "https://api.dexscreener.com/token-boosts/latest/v1"


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
        self.polling_interval = config.get("hydra", {}).get(
            "polling_interval_seconds", 30
        )
        self.min_progress = config.get("hydra", {}).get(
            "min_bonding_curve_progress", 35.0
        )

        # Initialize API Manager
        self.api_manager = GlobalApiManager()
        self.api_manager.setup_router(
            "discovery",
            [
                ApiProvider(
                    "pumpfun",
                    PUMPFUN_API_URL,
                    weight=100,
                    capacity=20,
                    refill_rate=2,
                    headers={
                        "Origin": "https://pump.fun",
                        "Referer": "https://pump.fun/",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "application/json",
                    },
                ),
                ApiProvider(
                    "dexscreener_boosts",
                    DEXSCREENER_BOOSTS_URL,
                    weight=80,
                    capacity=10,
                    refill_rate=0.5,
                    headers={"Accept": "application/json"},
                ),
            ],
        )

    async def connect_redis(self):
        self.redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
        print("AGT-12: Connected to Redis")

    async def fetch_trending_pumpfun(self) -> List[Dict[str, Any]]:
        """Fetch trending tokens from Pump.fun frontend API"""
        try:
            params = {
                "offset": 0,
                "limit": 50,
                "sort": "last_reply",
                "order": "DESC",
                "includeNsfw": "false",
            }
            data = await self.api_manager.request(
                "discovery", "GET", provider="pumpfun", params=params, timeout=10
            )
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"AGT-12: Error fetching trending from Pump.fun: {e}")
            return []

    async def fetch_top_marketcap_pumpfun(self) -> List[Dict[str, Any]]:
        """Fetch high market cap tokens from Pump.fun"""
        try:
            params = {
                "offset": 0,
                "limit": 30,
                "sort": "market_cap",
                "order": "DESC",
                "includeNsfw": "false",
            }
            data = await self.api_manager.request(
                "discovery", "GET", provider="pumpfun", params=params, timeout=10
            )
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"AGT-12: Error fetching top market cap from Pump.fun: {e}")
            return []

    async def fetch_boosted_dexscreener(self) -> List[str]:
        """Fetch latest boosted tokens from DexScreener"""
        try:
            data = await self.api_manager.request(
                "discovery", "GET", provider="dexscreener_boosts", timeout=10
            )
            if data and isinstance(data, list):
                # DexScreener boosts returns list of objects with 'tokenAddress'
                return [
                    item.get("tokenAddress")
                    for item in data
                    if item.get("tokenAddress")
                ]
            return []
        except Exception as e:
            print(f"AGT-12: Error fetching boosted from DexScreener: {e}")
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
            return None  # Placeholder for actual RPC lookup
        except Exception as e:  # pragma: no cover
            print(
                f"AGT-12: Error fetching bonding curve for {mint}: {e}"
            )  # pragma: no cover
            return None  # pragma: no cover

    async def get_sol_price(self) -> float:
        """Fetch SOL price from Redis (set by Oracle)"""
        try:
            if self.redis:
                price = await self.redis.get("mtus:sol_price")
                if price:
                    return float(price)
        except Exception:
            pass
        return 200.0  # Fallback

    async def process_token(self, token_data: Dict[str, Any]):
        """Process a potential candidate token"""
        mint = token_data.get("mint")
        if not mint or mint in self._processed_mints:
            return

        # Calculate progress from virtual_sol_reserves
        reserves = token_data.get("virtual_sol_reserves", 30000000000)
        current_progress = ((reserves - 30000000000) / 55000000000) * 100

        # ADVANCED FILTERING: Market Cap and Activity
        mcap_usd = token_data.get("usd_market_cap", 0)
        replies = token_data.get("reply_count", 0)

        # Reliability Markers: Socials
        has_socials = any(
            [
                token_data.get("twitter"),
                token_data.get("telegram"),
                token_data.get("website"),
            ]
        )

        min_mcap = self.config.get("hydra", {}).get(
            "min_market_cap_usd", 20000
        )  # Default $20k for 'high value'
        min_replies = self.config.get("hydra", {}).get("min_replies", 10)
        require_socials = self.config.get("hydra", {}).get("require_socials", True)

        if mcap_usd < min_mcap:
            return
        if replies < min_replies:
            return
        if require_socials and not has_socials:
            return

        # Categorize: On-Curve vs Graduated
        # If progress is 100%
        is_graduated = current_progress >= 100.0

        # Apply specific filters for graduated tokens
        if is_graduated:
            min_grad_mcap = self.config.get("hydra", {}).get(
                "graduated_min_market_cap_usd", 50000
            )
            if mcap_usd < min_grad_mcap:
                return
        else:
            # On-curve filters
            min_p = self.min_progress
            max_p = self.config.get("qualification", {}).get(
                "max_bonding_curve_progress", 95.0
            )
            if not (min_p <= current_progress <= max_p):
                return

        print(
            f"AGT-12: Discovery identified: {token_data.get('symbol', '???')} ({mint[:8]}) | Progress: {current_progress:.2f}% | Graduated: {is_graduated}"
        )

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
                "market_cap_sol": (
                    token_data.get("usd_market_cap", 0) / (await self.get_sol_price())
                )
                if token_data.get("usd_market_cap")
                else 0,
                "v_sol_in_bonding_curve": reserves / 1_000_000_000,
                "is_pump": not is_graduated,
                "is_trending": True,
                "is_graduated": is_graduated,
                "timestamp": time.time(),
            },
        )

        await self.redis.publish(CHANNEL_TOKEN_RECEIVED, envelope.model_dump_json())
        # Keep set size manageable
        if len(self._processed_mints) >= 1000:
            self._processed_mints.clear()
        self._processed_mints.add(mint)

    async def run(self):
        self.running = True
        await self.connect_redis()

        print(
            f"AGT-12: Hydra Monitoring Agent started (Min Progress: {self.min_progress}%)"
        )

        while self.running:
            try:
                # Check operational window
                if not is_operational_window_active():
                    print(
                        "AGT-12: [OFF-HOURS] Outside operational window. Sleeping for 60s..."
                    )
                    await asyncio.sleep(60)
                    continue

                # 1. Fetch High-Value from Pump.fun (Top Market Cap)
                high_value = await self.fetch_top_marketcap_pumpfun()
                for token in high_value:
                    await self.process_token(token)

                # 2. Fetch Boosted from DexScreener (Verified Visibility)
                boosted_mints = await self.fetch_boosted_dexscreener()
                # For boosted mints, we'd ideally fetch details for each.
                # To avoid massive API spam, we'll just log them if they appear in our trending scan
                # or add a targeted fetch if needed.

                # 3. Fetch Trending as fallback AND for early 5% tokens
                trending = await self.fetch_trending_pumpfun()
                for token in trending:
                    await self.process_token(token)

                total_scanned = len(high_value) + len(trending)
                if total_scanned > 0:
                    print(
                        f"AGT-12: Poller heartbeat - {total_scanned} tokens scanned (High Value focus)."
                    )

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
