import asyncio
import aioredis
import aiohttp
import json
import os
import sys
import yaml
import time
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# Load .env file
load_dotenv("./.env")

from src.python.shared.api_manager import GlobalApiManager, ApiProvider
from src.python.shared.operational_window import is_operational_window_active
from src.python.shared.envelope import AgentMessageEnvelope, EventType
from src.python.shared.config_validator import validate_config
from src.python.shared.safe_output import safe_print as print
from src.python.shared.constants import (
    CHANNEL_POSITION_OPENED,
    CHANNEL_PRICE_UPDATED,
    CHANNEL_PRICE_UNAVAILABLE,
    CHANNEL_TOKEN_RECEIVED,
    CHANNEL_TOKEN_TA_SCORED,
    EVENT_TOKEN_TA_SCORED,
)
from src.python.shared.indicators import calculate_rsi, calculate_volume_trend, analyze_trend

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
        
        # Initialize API Manager with Market Data router
        self.api_manager = GlobalApiManager()
        self.api_manager.setup_router("market_data", [
            ApiProvider("jupiter", JUPITER_V3_URL, weight=50, capacity=10, refill_rate=5),
            ApiProvider("dexscreener", DEXSCREENER_URL, weight=30, capacity=5, refill_rate=1),
            ApiProvider("birdeye", "https://api.birdeye.so/api/v3/token/price", key=BIRDEYE_API_KEY, weight=15, capacity=3, refill_rate=0.5),
            ApiProvider("coingecko", COINGECKO_API, weight=5, capacity=2, refill_rate=0.2)
        ])

    async def connect_redis(self):
        self.redis = await aioredis.from_url(
            "redis://localhost:6379", decode_responses=True
        )
        self.pubsub = self.redis.pubsub()

        self.birdeye_key = os.getenv("BIRDEYE_API_KEY")
        if self.birdeye_key:
            print("[AGT-04] Birdeye API key configured")
        print("[AGT-04] Jupiter V3 + DexScreener price sources ready")

    async def fetch_price_jupiter(self, mint: str) -> float:
        """Primary: Jupiter V3 API"""
        try:
            data = await self.api_manager.request("market_data", "GET", provider="jupiter", params={"ids": mint}, timeout=5)
            if data:
                token_data = data.get(mint, {})
                price = token_data.get("usdPrice")
                if price:
                    return float(price)
        except Exception:
            pass
        return 0.0

    async def fetch_price_dexscreener(self, mint: str) -> float:
        """Secondary: DexScreener API"""
        try:
            path = f"/{mint}"
            data = await self.api_manager.request("market_data", "GET", provider="dexscreener", path=path, timeout=5)
            if data:
                pairs = data.get("pairs", [])
                if pairs:
                    price = pairs[0].get("priceUsd")
                    if price:
                        return float(price)
        except Exception:
            pass
        return 0.0

    async def fetch_ohlcv_birdeye(self, mint: str, interval: str = "5m", limit: int = 20) -> List[float]:
        """Fetch historical price series from Birdeye for TA"""
        if not self.birdeye_key:
            return []
        try:
            # Birdeye /defi/history_price endpoint
            url = "https://public-api.birdeye.so/defi/history_price"
            now = int(time.time())
            # interval mapping: 5m -> 300, 15m -> 900
            seconds = 300 if interval == "5m" else 900
            time_from = now - (seconds * (limit + 5))
            
            params = {
                "address": mint,
                "address_type": "token",
                "type": interval,
                "time_from": time_from,
                "time_to": now
            }
            
            headers = {"X-API-KEY": self.birdeye_key}
            async with self.session.get(url, params=params, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        items = data.get("data", {}).get("items", [])
                        return [float(i.get("value", 0)) for i in items]
        except Exception as e:
            print(f"[AGT-04] OHLCV fetch failed: {e}")
        return []

    async def fetch_ta_data(self, mint: str, interval: str = "5m", limit: int = 20) -> Dict[str, List[float]]:
        """Fetch historical price and volume series from Birdeye"""
        ta_data = {"prices": [], "volumes": []}
        if not self.birdeye_key:
            return ta_data
            
        try:
            # Using Birdeye /defi/ohlcv endpoint for both price and volume
            url = "https://public-api.birdeye.so/defi/ohlcv"
            now = int(time.time())
            seconds = 300 if interval == "5m" else 900
            time_from = now - (seconds * (limit + 5))
            
            params = {
                "address": mint,
                "type": interval,
                "time_from": time_from,
                "time_to": now
            }
            
            headers = {"X-API-KEY": self.birdeye_key}
            async with self.session.get(url, params=params, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        items = data.get("data", {}).get("items", [])
                        ta_data["prices"] = [float(i.get("c", 0)) for i in items] # Close price
                        ta_data["volumes"] = [float(i.get("v", 0)) for i in items] # Volume
        except Exception as e:
            print(f"[AGT-04] TA data fetch failed: {e}")
        
        # Fallback to history_price if ohlcv fails
        if not ta_data["prices"]:
            ta_data["prices"] = await self.fetch_ohlcv_birdeye(mint, interval, limit)
            
        return ta_data

    async def fetch_ohlcv_dexscreener(self, mint: str) -> List[float]:
        """Fallback: Fetch rough OHLCV/Price history from DexScreener pairs"""
        # DexScreener doesn't provide easy historical series in public API
        # We'll just return an empty list or use current price if needed
        return []

    async def perform_ta_analysis(self, token_payload: Dict) -> Dict:
        """Calculate technical indicators and determine signal"""
        mint = token_payload.get("mint")
        data = await self.fetch_ta_data(mint)
        prices = data["prices"]
        volumes = data["volumes"]
        
        ta_data = {
            "rsi": None,
            "volume_trend": 1.0,
            "signal": "neutral"
        }
        
        if len(prices) >= 14:
            rsi = calculate_rsi(prices)
            ta_data["rsi"] = rsi
            
            # Use current vs prev price for trend
            trend = analyze_trend(prices)
            
            # Volume multiplier
            vol_trend = calculate_volume_trend(volumes)
            ta_data["volume_trend"] = vol_trend
            
            # Simple Signal Logic
            rsi_oversold = self.config.get("hydra", {}).get("ta_rsi_oversold", 35)
            rsi_bullish = self.config.get("hydra", {}).get("ta_rsi_bullish", 55)
            vol_mult = self.config.get("hydra", {}).get("ta_volume_multiplier_threshold", 1.5)
            
            if rsi and rsi < rsi_oversold:
                ta_data["signal"] = "bullish" # Oversold bounce
            elif rsi and rsi > rsi_bullish and trend == "bullish":
                ta_data["signal"] = "bullish" # Momentum breakout
            elif rsi and rsi > 45 and vol_trend is not None and vol_trend > vol_mult:
                ta_data["signal"] = "bullish" # Volume-led accumulation
            elif rsi and rsi > 80:
                ta_data["signal"] = "bearish" # Overbought
                
        return ta_data

    async def handle_token_received(self, envelope_json: str):
        """Handle new token discovery and perform TA scoring"""
        try:
            envelope = AgentMessageEnvelope.model_validate_json(envelope_json)
            token = envelope.payload
            
            is_graduated = token.get("is_graduated", False)
            if not is_graduated:
                # We don't perform TA on early/bonding-curve tokens as they don't have enough chart history
                return
                
            print(f"AGT-04: Received TA request for {token.get('symbol')} ({token.get('mint')[:8]})")
            
            # Perform TA
            ta_results = await self.perform_ta_analysis(token)
            token["ta_data"] = ta_results
            token["ta_signal"] = ta_results["signal"]
            token["sol_price"] = await self.get_sol_price() # Include current SOL price
            
            # Re-publish as TA scored
            envelope.agent_id = "AGT-04"
            envelope.event_type = EVENT_TOKEN_TA_SCORED
            envelope.payload = token
            
            await self.redis.publish(CHANNEL_TOKEN_TA_SCORED, envelope.model_dump_json())
            print(f"AGT-04: TA Scored {token.get('symbol')} -> Signal: {ta_results['signal']} (RSI: {ta_results['rsi']}, SOL: ${token['sol_price']:.2f})")
            
        except Exception as e:
            print(f"AGT-04: Error in TA analysis: {e}")

    async def fetch_price_birdeye(self, mint: str) -> float:
        """Tertiary: Birdeye"""
        try:
            data = await self.api_manager.request("market_data", "GET", provider="birdeye", params={"address": mint}, timeout=5)
            if data and data.get("success"):
                return float(data.get("data", {}).get("value", 0.0))
        except Exception:
            pass
        return 0.0

    async def fetch_price_coingecko(self, mint: str) -> float:
        """Last resort: CoinGecko"""
        try:
            # We use SOL as a proxy if the specific mint isn't tracked on CoinGecko Free API
            data = await self.api_manager.request("market_data", "GET", provider="coingecko", path="/simple/price", params={"ids": SOL_TOKEN_ID, "vs_currencies": "usd"}, timeout=10)
            if data:
                usd_price = data.get(SOL_TOKEN_ID, {}).get("usd", 0)
                return float(usd_price)
        except Exception as e:
            print(f"[AGT-04] CoinGecko SOL fetch failed: {e}")
        return 0.0

    async def get_sol_price(self) -> float:
        """Fetch SOL price with caching (60s) and Redis persistence"""
        now = time.time()
        if self._sol_price_cache and (now - self._sol_price_time) < 60:
            return self._sol_price_cache

        # Try Jupiter first
        price = await self.fetch_price_jupiter(SOL_MINT)
        if price <= 0:
            # Try CoinGecko
            price = await self.fetch_price_coingecko(SOL_MINT)

        if price > 0:
            self._sol_price_cache = price
            self._sol_price_time = now
            if self.redis:
                await self.redis.set("mtus:sol_price", str(price))
            return price
            
        return self._sol_price_cache or 200.0 # Extreme fallback

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
            position_id = payload.get("position_id") or envelope.correlation_id or f"pos_{int(time.time())}"
            mint = payload["mint"]
            entry_price = payload.get("entry_price_sol")
            if entry_price is None:
                entry_price = 0.0
                
            self.positions[position_id] = {
                "mint": mint,
                "last_prices": [float(entry_price)],
                "fail_count": 0,
            }
            print(f"AGT-04: Tracking position {position_id} for {mint}")
        except Exception as e:
            print(f"AGT-04: Error handling position_opened: {e}")

    async def run(self):
        self.running = True
        await self.connect_redis()
        self.session = aiohttp.ClientSession()
        is_subscribed = False
        print("AGT-04: Oracle agent starting loop...")

        while self.running:
            try:
                active = is_operational_window_active()

                if active and not is_subscribed:
                    await self.pubsub.subscribe(CHANNEL_POSITION_OPENED)
                    await self.pubsub.subscribe(CHANNEL_TOKEN_RECEIVED)
                    is_subscribed = True
                    print(f"AGT-04: Subscribed to {CHANNEL_POSITION_OPENED} and {CHANNEL_TOKEN_RECEIVED}")
                elif not active and is_subscribed:
                    await self.pubsub.unsubscribe()
                    is_subscribed = False
                    print("AGT-04: [OFF-HOURS] Unsubscribed from events to save resources")

                if not active:
                    await asyncio.sleep(60)
                    continue

                # Handle incoming position_opened messages
                message = await self.pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    channel = message["channel"]
                    if channel == CHANNEL_POSITION_OPENED:
                        await self.handle_position_opened(message["data"])
                    elif channel == CHANNEL_TOKEN_RECEIVED:
                        await self.handle_token_received(message["data"])

                # Update SOL price cache
                await self.get_sol_price()

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


async def main():
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
        sys.exit(1)

    is_valid, error = validate_config(config)
    if not is_valid:
        print(f"[CONFIG] Configuration validation failed: {error}")
        sys.exit(1)
    print("[CONFIG] Configuration is valid")

    agent = OracleAgent(config)
    try:
        await agent.run()
    except KeyboardInterrupt:
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
