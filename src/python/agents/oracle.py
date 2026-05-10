import asyncio
import aioredis
import aiohttp
import json
import os
import yaml
import time
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# Load .env file
load_dotenv("./.env")

from src.python.shared.envelope import AgentMessageEnvelope, EventType
from src.python.shared.config_validator import validate_config
from src.python.shared.constants import (
    CHANNEL_POSITION_OPENED,
    CHANNEL_PRICE_UPDATED,
    CHANNEL_PRICE_UNAVAILABLE,
)

BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY")

# Updated to latest Jupiter V3 endpoint (works!)
JUPITER_V3_URL = "https://api.jup.ag/price/v3"
DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens"
COINGECKO_API = "https://api.coingecko.com/api/v3"
POLLING_INTERVAL = 5
MAX_CONSECUTIVE_FAILURES = 3

SOL_MINT = "So11111111111111111111111111111111111111112"
SOL_TOKEN_ID = "solana"


class OracleAgent:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.redis = None
        self.pubsub = None
        self.positions: Dict[str, Dict] = {}
        self.running = False
        self.session = None
        self.birdeye_key = None
        self._sol_price_cache = None
        self._sol_price_time = 0

    async def connect_redis(self):
        self.redis = await aioredis.from_url(
            "redis://localhost:6379", decode_responses=True
        )
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe(CHANNEL_POSITION_OPENED)

        self.birdeye_key = os.getenv("BIRDEYE_API_KEY")
        if self.birdeye_key:
            print("[AGT-04] Birdeye API key configured")
        print("[AGT-04] Jupiter V3 + DexScreener price sources ready")

    async def fetch_price_jupiter(self, mint: str) -> float:
        """Primary: Jupiter V3 API - returns USD price directly"""
        try:
            async with self.session.get(
                f"{JUPITER_V3_URL}?ids={mint}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # New V3 format: data[mint]["usdPrice"]
                    token_data = data.get(mint, {})
                    price = token_data.get("usdPrice")
                    if price:
                        return float(price)
        except Exception as e:
            print(f"[AGT-04] Jupiter V3 failed for {mint}: {e}")
        return 0.0

    async def fetch_price_dexscreener(self, mint: str) -> float:
        """Secondary: DexScreener API"""
        try:
            async with self.session.get(
                f"{DEXSCREENER_URL}/{mint}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pairs = data.get("pairs", [])
                    if pairs and len(pairs) > 0:
                        price = pairs[0].get("priceUsd")
                        if price:
                            return float(price)
        except Exception as e:
            print(f"[AGT-04] DexScreener failed for {mint}: {e}")
        return 0.0

    async def fetch_price_birdeye(self, mint: str) -> float:
        """Tertiary: Birdeye - try alternative endpoint"""
        if not self.birdeye_key:
            return 0.0

        # Try the newer v3 API endpoint
        try:
            url = f"https://api.birdeye.so/api/v3/token/price?address={mint}"
            headers = {"X-API-KEY": self.birdeye_key}
            async with self.session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data.get("data", {}).get("value", 0.0))
        except Exception as e:
            pass

        # Fallback to older endpoint
        try:
            url = f"https://public-api.birdeye.so/public/price?address={mint}"
            headers = {"X-API-KEY": self.birdeye_key}
            async with self.session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data.get("data", {}).get("value", 0.0))
        except Exception as e:
            print(f"[AGT-04] Birdeye failed for {mint}: {e}")
        return 0.0

    async def fetch_price_coingecko(self, mint: str) -> float:
        """Last resort: CoinGecko"""
        try:
            async with self.session.get(
                f"{COINGECKO_API}/simple/price?ids={SOL_TOKEN_ID}&vs_currencies=usd",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    usd_price = data.get(SOL_TOKEN_ID, {}).get("usd", 0)
                    if usd_price > 0 and self._sol_price_cache:
                        token_usd = self._sol_price_cache / usd_price
                        return token_usd
        except Exception as e:
            print(f"[AGT-04] CoinGecko fallback failed: {e}")
        return 0.0

    async def update_position_price(self, position_id: str, mint: str):
        pos = self.positions[position_id]
        price = 0.0
        source = "none"

        # Primary: Jupiter V3 (free, most reliable)
        price = await self.fetch_price_jupiter(mint)
        if price > 0:
            source = "jupiter_v3"
            pos["fail_count"] = 0
        else:
            # Secondary: DexScreener (free, great fallback)
            price = await self.fetch_price_dexscreener(mint)
            if price > 0:
                source = "dexscreener"
                pos["fail_count"] = 0
            else:
                # Tertiary: Birdeye (if API key provided)
                price = await self.fetch_price_birdeye(mint)
                if price > 0:
                    source = "birdeye"
                    pos["fail_count"] = 0
                else:
                    pos["fail_count"] += 1
                    print(
                        f"[AGT-04] Price fetch failed for {mint} (tried: Jupiter, DexScreener, Birdeye)"
                    )

        if price <= 0:
            if pos["fail_count"] >= MAX_CONSECUTIVE_FAILURES:
                envelope = AgentMessageEnvelope(
                    agent_id="AGT-04",
                    event_type="price_unavailable",
                    payload={"position_id": position_id, "mint": mint},
                )
                await self.redis.publish(
                    CHANNEL_PRICE_UNAVAILABLE, envelope.model_dump_json()
                )
                print(
                    f"[AGT-04] Price unavailable for {mint} after {pos['fail_count']} failures"
                )
                return
        else:
            pos["fail_count"] = 0

        # Update price buffer
        pos["last_prices"].append(price)
        if len(pos["last_prices"]) > 10:
            pos["last_prices"].pop(0)
        peak_price = max(pos["last_prices"]) if pos["last_prices"] else price

        # Emit price_updated event
        envelope = AgentMessageEnvelope(
            agent_id="AGT-04",
            event_type="price_updated",
            payload={
                "position_id": position_id,
                "mint": mint,
                "price": price,
                "peak_price": peak_price,
            },
        )
        await self.redis.publish(CHANNEL_PRICE_UPDATED, envelope.model_dump_json())

    async def handle_position_opened(self, envelope_json: str):
        try:
            envelope = AgentMessageEnvelope.model_validate_json(envelope_json)
            payload = envelope.payload
            position_id = payload["position_id"]
            mint = payload["mint"]
            self.positions[position_id] = {
                "mint": mint,
                "last_prices": [payload.get("entry_price_sol", 0.0)],
                "fail_count": 0,
            }
            print(f"AGT-04: Tracking position {position_id} for {mint}")
        except Exception as e:
            print(f"AGT-04: Error handling position_opened: {e}")

    async def run(self):
        self.running = True
        await self.connect_redis()
        self.session = aiohttp.ClientSession()
        print("AGT-04: Oracle agent started")

        while self.running:
            try:
                # Handle incoming position_opened messages
                message = await self.pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    await self.handle_position_opened(message["data"])

                # Poll prices for all open positions
                for pos_id in list(self.positions.keys()):
                    pos = self.positions[pos_id]
                    await self.update_position_price(pos_id, pos["mint"])

                await asyncio.sleep(POLLING_INTERVAL)
            except Exception as e:
                print(f"AGT-04: Error in run loop: {e}")
                if "stop loop" in str(e):
                    break
                await asyncio.sleep(1)

    async def stop(self):
        self.running = False
        if self.session:
            await self.session.close()
        if self.pubsub:
            await self.pubsub.unsubscribe()
        if self.redis:
            await self.redis.close()
        print("AGT-04: Oracle agent stopped")


if __name__ == "__main__":
    # Find project root

    # Find project root
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    config_path = os.path.join(project_root, "config", "config.yaml")

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"[CONFIG] Error loading config: {e}")
        exit(1)

    is_valid, error = validate_config(config)
    if not is_valid:
        print(f"[CONFIG] Configuration validation failed: {error}")
        exit(1)
    print("[CONFIG] Configuration is valid")

    agent = OracleAgent(config)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        asyncio.run(agent.stop())
