import asyncio
import aioredis
import aiohttp
import json
import os
import yaml
from typing import Dict, Optional, Any
from dotenv import load_dotenv
from src.python.shared.envelope import AgentMessageEnvelope, EventType
from src.python.shared.config_validator import validate_config
from src.python.shared.constants import (
    CHANNEL_SOCIAL_SCORED,
    CHANNEL_TOKEN_RECEIVED_SOCIAL,
)

load_dotenv("./.env")

DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"
TWITTER_API_V2 = "https://api.twitter.com/2/tweets/counts"


class CassandraAgent:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.redis = None
        self.pubsub = None
        self.running = False
        self.session = None

    async def connect_redis(self):
        self.redis = await aioredis.from_url(
            "redis://localhost:6379", decode_responses=True
        )
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe(CHANNEL_TOKEN_RECEIVED_SOCIAL)
        print("AGT-08: Subscribed to token_received_social")

    async def fetch_dexscreener_data(self, mint: str) -> Optional[Dict]:
        try:
            url = f"{DEXSCREENER_API}/{mint}"
            async with self.session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("pair", {})
        except Exception as e:
            print(f"AGT-08: DexScreener fetch failed: {e}")
        return None

    async def fetch_metadata_socials(self, uri: str) -> Dict[str, bool]:
        socials = {"twitter": False, "telegram": False, "website": False}
        try:
            async with self.session.get(uri, timeout=5) as resp:
                if resp.status == 200:
                    metadata = await resp.json()
                    social = (
                        metadata.get("social", {}) or metadata.get("Social", {}) or {}
                    )
                    socials["twitter"] = bool(
                        social.get("twitter") or social.get("x") or social.get("X")
                    )
                    socials["telegram"] = bool(
                        social.get("telegram") or social.get("telegram")
                    )
                    socials["website"] = bool(
                        social.get("website")
                        or social.get("website")
                        or social.get("url")
                    )
        except Exception as e:
            print(f"AGT-08: Metadata fetch error: {e}")
        return socials

    async def score_sentiment(self, token_payload: Dict) -> float:
        try:
            score = 50.0
            socials = {"twitter": False, "telegram": False, "website": False}

            mint = token_payload.get("mint", "")
            uri = token_payload.get("uri", "")

            if mint:
                dex_data = await self.fetch_dexscreener_data(mint)
                if dex_data:
                    info = dex_data.get("info", {})
                    twitter = info.get("twitter")
                    telegram = info.get("telegram")
                    website = info.get("website")

                    if twitter:
                        score += 15
                        socials["twitter"] = True
                    if telegram:
                        score += 15
                        socials["telegram"] = True
                    if website:
                        score += 10
                        socials["website"] = True

                    liquidity = dex_data.get("liquidity", {}).get("usd", 0)
                    if liquidity > 100000:
                        score += 10
                    elif liquidity > 10000:
                        score += 5

                    tx_count_24h = dex_data.get("txns", {}).get("h24", {})
                    buys = tx_count_24h.get("buys", 0)
                    sells = tx_count_24h.get("sells", 0)
                    if buys + sells > 100:
                        score += 5
                    if buys > sells:
                        score += 5
                    elif sells > buys * 2:
                        score -= 10

            if not any(socials.values()) and uri:
                metadata_socials = await self.fetch_metadata_socials(uri)
                if metadata_socials["twitter"]:
                    score += 15
                    socials["twitter"] = True
                if metadata_socials["telegram"]:
                    score += 15
                    socials["telegram"] = True
                if metadata_socials["website"]:
                    score += 10
                    socials["website"] = True

            token_age = token_payload.get("age", 0)
            if token_age > 86400:
                score += 5
            elif token_age < 3600:
                score -= 5

            return min(max(score, 0), 100)
        except Exception as e:
            print(f"AGT-08: Scoring error: {e}")
            return 0.0

    async def handle_token_received(self, envelope_json: str):
        try:
            envelope = AgentMessageEnvelope.model_validate_json(envelope_json)
            token = envelope.payload

            if not token.get("sentiment_score"):
                sentiment = await self.score_sentiment(token)
                token["sentiment_score"] = sentiment

            if not token.get("social_signals"):
                mint = token.get("mint", "")
                uri = token.get("uri", "")

                socials = {"twitter": False, "telegram": False, "website": False}
                if mint:
                    dex_data = await self.fetch_dexscreener_data(mint)
                    if dex_data:
                        info = dex_data.get("info", {})
                        socials["twitter"] = bool(info.get("twitter"))
                        socials["telegram"] = bool(info.get("telegram"))
                        socials["website"] = bool(info.get("website"))

                if not any(socials.values()) and uri:
                    socials = await self.fetch_metadata_socials(uri)

                token["social_signals"] = socials

            envelope.agent_id = "AGT-08"
            envelope.event_type = "social_scored"
            envelope.payload = token

            await self.redis.publish(CHANNEL_SOCIAL_SCORED, envelope.model_dump_json())
            print(
                f"AGT-08: Scored {token.get('symbol')}: {token.get('sentiment_score', 0)}"
            )

        except Exception as e:
            print(f"AGT-08: Error handling token: {e}")

    async def run(self):
        self.running = True
        await self.connect_redis()
        self.session = aiohttp.ClientSession()
        print("AGT-08: Cassandra agent started")

        while self.running:
            try:
                message = await self.pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    await self.handle_token_received(message["data"])
                await asyncio.sleep(0.01)
            except Exception as e:
                print(f"AGT-08: Error in run loop: {e}")
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
        print("AGT-08: Cassandra agent stopped")


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

    agent = CassandraAgent(config)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        asyncio.run(agent.stop())
