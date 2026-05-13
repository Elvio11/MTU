import asyncio
import json
import os
import sys
import re
import yaml
import websockets
import aioredis
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime
from dotenv import load_dotenv
from src.python.shared.config_validator import validate_config
from src.python.shared.envelope import AgentMessageEnvelope, EventType
from src.python.shared.operational_window import is_operational_window_active
from src.python.shared.token_payload import PumpPortalTokenPayload
from src.python.shared.circuit_breaker import CircuitBreaker
from src.python.shared.priority_queue import PriorityQueue, calculate_priority
from src.python.shared.constants import is_paper_mode
from src.python.shared.safe_output import safe_print as print

load_dotenv("./.env")

PUMP_PORTAL_WS_URL = "wss://pumpdev.io/ws"
WHISTLE_WS_URL = "wss://pump.whistle.ninja/ws"
PUMP4DEV_WS_URL = "wss://pump-api.pump4dev.fun/ws"

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
MAX_EVENTS_PER_SECOND = 10
RECONNECT_BASE_DELAY = 1
RECONNECT_MAX_DELAY = 30

RAYDIUM_AMM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"


class NofxAgent:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.is_paper_mode = is_paper_mode()
        self.redis = None
        self.ws = None
        self.helius_ws = None
        self.running = False
        self.event_count = 0
        self.last_reset = datetime.utcnow().timestamp()
        self.circuit_breaker = CircuitBreaker()
        self.helius_ws_url = None
        self._seen_mints = set()
        self.priority_queue = None

    async def connect_redis(self):
        self.redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
        self.priority_queue = PriorityQueue(self.redis)
        print("AGT-01: Connected to Redis and Priority Queue")

    async def connect_pumpdev(self, delay: int = 0):
        if delay > 0:
            await asyncio.sleep(delay)

        ws_url = PUMP_PORTAL_WS_URL

        try:
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    ws_url,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=5,
                ),
                timeout=15.0,
            )
            print("AGT-01: Connected to PumpDev WebSocket")
        except Exception as pump_err:
            print(f"AGT-01: PumpDev failed: {pump_err}, trying Whistle...")
            try:
                ws_url = WHISTLE_WS_URL
                self.ws = await asyncio.wait_for(
                    websockets.connect(
                        ws_url,
                        ping_interval=30,
                        ping_timeout=10,
                        close_timeout=5,
                    ),
                    timeout=15.0,
                )
                print("AGT-01: Connected to Whistle WebSocket (fallback)")
            except Exception as whistle_err:
                print(f"AGT-01: Whistle failed: {whistle_err}, trying Pump4Dev...")
                try:
                    ws_url = PUMP4DEV_WS_URL
                    self.ws = await asyncio.wait_for(
                        websockets.connect(
                            ws_url,
                            ping_interval=30,
                            ping_timeout=10,
                            close_timeout=5,
                        ),
                        timeout=15.0,
                    )
                    print("AGT-01: Connected to Pump4Dev WebSocket (fallback)")
                except Exception as p4d_err:
                    print(f"AGT-01: Pump4Dev also failed: {p4d_err}")
                    return False

        # if "whistle" in ws_url:
        #     sub_msg = json.dumps({"type": "subscribe", "channel": "pumpfun:new"})
        #     print(f"AGT-01: Sending (Whistle): {sub_msg}")
        #     await self.ws.send(sub_msg)
        #     print("AGT-01: Subscribed to Whistle pumpfun:new channel")
        #     return True

        # sub_msg = json.dumps({"method": "subscribeNewToken"})
        # print(f"AGT-01: Sending: {sub_msg}")
        # await self.ws.send(sub_msg)

        # trade_msg = json.dumps(
        #     {
        #         "method": "subscribeTokenTrade",
        #         "keys": [],
        #     }
        # )
        # print(f"AGT-01: Sending: {trade_msg}")
        # await self.ws.send(trade_msg)

        wallet_msg = json.dumps({"method": "subscribeAccountTrade", "keys": []})
        print(f"AGT-01: Sending: {wallet_msg}")
        await self.ws.send(wallet_msg)

        try:
            migration_msg = json.dumps({"method": "subscribeMigration"})
            print(f"AGT-01: Sending: {migration_msg}")
            await self.ws.send(migration_msg)
        except:
            pass

        print("AGT-01: Subscribed to: NewToken, TokenTrade, AccountTrade, Migration")
        return True

    async def poll_for_tokens_http(self):
        try:
            resp = requests.get(
                "https://api.dexscreener.com/latest/dex/tokens/solana", timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get("pairs", [])

                pump_tokens = [p for p in pairs if p.get("dexId") == "pumpfun"]

                for pair in pump_tokens[:10]:
                    token_info = pair.get("baseToken", {})
                    if token_info:
                        mint = token_info.get("address", "")
                        if mint and mint not in self._seen_mints:
                            self._seen_mints.add(mint)

                            payload = {
                                "mint": mint,
                                "name": token_info.get("name", "Unknown"),
                                "symbol": token_info.get("symbol", "???"),
                                "uri": token_info.get("uri") or None,
                                "initialBuy": 0.0,
                                "marketCapSol": float(pair.get("marketCap", 0)) / 1e9
                                if pair.get("marketCap")
                                else 0,
                                "bondingCurveKey": pair.get("pool") or "11111111111111111111111111111111",
                                "vSolInBondingCurve": float(
                                    pair.get("liquidity", {}).get("sol", 0)
                                )
                                * 1e9
                                if pair.get("liquidity", {}).get("sol")
                                else 0,
                                "traderPublicKey": token_info.get("creator") or "11111111111111111111111111111111",
                            }
                            await self._handle_new_token(payload)

        except Exception as e:
            print(f"AGT-01: HTTP polling error: {e}")

    def get_backoff_delay(self, attempt: int) -> int:
        delay = RECONNECT_BASE_DELAY * (2**attempt)
        return min(delay, RECONNECT_MAX_DELAY)

    async def connect_helius_ws(self):
        from os import getenv

        self.helius_ws_url = getenv(
            "HELIUS_WS_URL",
            "wss://mainnet.helius-rpc.com/?api-key=" + getenv("HELIUS_KEY", ""),
        )
        try:
            self.helius_ws = await websockets.connect(self.helius_ws_url)

            await self.helius_ws.send(
                json.dumps(
                    {
                        "method": "subscribeProgram",
                        "params": [RAYDIUM_AMM_V4],
                    }
                )
            )
            print("AGT-01: Connected to Helius WS for Raydium")
            return True
        except Exception as e:
            print(f"AGT-01: Failed to connect to Helius WS: {e}")
            return False

    async def handle_pumpdev_message(self, payload: dict):
        if not isinstance(payload, dict):
            return

        tx_type = payload.get("txType")

        if tx_type == "create":
            await self._handle_new_token(payload)

        elif tx_type == "complete":
            print(
                f"AGT-01: Migration starting (PumpSwap): {payload.get('mint', '')[:8]}..."
            )

        elif tx_type == "create_pool":
            print(
                f"AGT-01: Migration complete (PumpSwap): {payload.get('mint', '')[:8]}... -> {payload.get('pool', '')[:8]}..."
            )
            await self._publish_migration(payload)

        elif tx_type == "migration":
            print(
                f"AGT-01: Token migrated to PumpSwap: {payload.get('mint', '')[:8]}... -> {payload.get('poolAddress', '')[:8]}..."
            )
            await self._publish_migration(payload)

        elif tx_type == "whale":
            sol_amount = payload.get("solAmount", 0)
            print(
                f"AGT-01: [WHALE] ALERT: {sol_amount} SOL trade on {payload.get('mint', '')[:8]}... (MC: {payload.get('marketCapSol', 0):.1f} SOL)"
            )

        elif tx_type == "devSell":
            print(
                f"AGT-01: [DEV SELL]: Creator sold {payload.get('tokenAmount', 0)} tokens from {payload.get('mint', '')[:8]}..."
            )

        elif tx_type == "koth":
            print(
                f"AGT-01: [KOTH] KING OF THE HILL: {payload.get('mint', '')[:8]}... at {payload.get('bondingCurveProgress', 0):.1f}%"
            )
            await self._handle_new_token(payload)

        elif tx_type == "graduatingSoon":
            print(
                f"AGT-01: [GRADUATE] GRADUATING SOON: {payload.get('mint', '')[:8]}... at {payload.get('bondingCurveProgress', 0):.1f}%"
            )
            await self._handle_new_token(payload)

        elif tx_type in ("buy", "sell"):
            source = payload.get("source", "bonding_curve")
            sol_amount = payload.get("solAmount", 0)
            mint = payload.get("mint", "")
            mcap = payload.get("marketCapSol", 0)

            print(
                f"AGT-01: {tx_type.upper()} on {source}: {mint[:8]}... ({sol_amount} SOL, MC: {mcap:.1f} SOL)"
            )

            if sol_amount >= 1: # Only track significant activity to avoid spam
                await self._handle_token_activity(payload)
            
            if sol_amount >= 5:
                print(
                    f"AGT-01: [WHALE] ALERT: {sol_amount} SOL {tx_type} on {mint[:8]}... (MC: {mcap:.1f} SOL)"
                )

        elif "type" in payload:
            print(
                f"AGT-01: PumpDev {payload.get('type')}: {payload.get('message', '')}"
            )

    async def _handle_new_token(self, payload: dict):
        try:
            from jsonschema import validate

            schema = {
                "type": "object",
                "properties": {
                    "mint": {"type": "string"},
                    "name": {"type": "string"},
                    "symbol": {"type": "string"},
                    "uri": {"type": "string"},
                    "initialBuy": {"type": "number"},
                    "marketCapSol": {"type": "number"},
                    "bondingCurveKey": {"type": "string"},
                    "vSolInBondingCurve": {"type": "number"},
                    "traderPublicKey": {"type": "string"},
                    "signature": {"type": "string"},
                    "txType": {"type": "string"},
                },
                "required": [
                    "mint",
                    "name",
                    "symbol",
                    "marketCapSol",
                ],
            }
            validate(instance=payload, schema=schema)

            token_data = {
                "mint": payload["mint"],
                "name": payload["name"],
                "symbol": payload["symbol"],
                "uri": payload.get("uri", ""),
                "initialBuy": payload.get("initialBuy", 0),
                "marketCapSol": payload["marketCapSol"],
                "bondingCurveKey": payload.get("bondingCurveKey", ""),
                "vSolInBondingCurve": payload.get("vSolInBondingCurve", 0),
                "creator": payload.get("traderPublicKey", ""),
            }
            token = PumpPortalTokenPayload(**token_data)
        except Exception as e:
            print(f"AGT-01: Invalid token payload: {e}")
            return

        if not self.check_rate_limit():
            print("AGT-01: Rate limit exceeded, skipping token")
            return

        envelope = AgentMessageEnvelope(
            agent_id="AGT-01", event_type="token_detected", payload=token.model_dump()
        )

        if self.priority_queue:
            priority = calculate_priority(
                payload.get("txType", "create"), payload.get("vSolInBondingCurve", 0)
            )
            await self.priority_queue.enqueue(envelope.model_dump(), priority)
            queue_lengths = await self.priority_queue.get_queue_lengths()
            print(
                f"AGT-01: Queued {token.symbol} (priority {priority}), queue: {queue_lengths['total']}/100"
            )
        else:
            print(
                f"AGT-01: WARNING - No priority queue configured, token not queued: {token.symbol}"
            )

    async def _handle_token_activity(self, payload: dict):
        token = None
        try:
            token_data = {
                "mint": payload["mint"],
                "name": payload.get("name", "Unknown"),
                "symbol": payload.get("symbol", "???"),
                "uri": payload.get("uri") or None,  # None avoids HTTPS validator on empty string
                "initialBuy": payload.get("initialBuy", 0),
                "marketCapSol": payload.get("marketCapSol", 0),
                "vSolInBondingCurve": payload.get("vSolInBondingCurve", 0),
                "bondingCurveProgress": payload.get("bondingCurveProgress", 0),
            }
            token = PumpPortalTokenPayload(**token_data)
        except Exception as e:
            # We expect missing name/symbol here, so we ignore validation errors for activity
            pass

        if token is None:
            return

        envelope = AgentMessageEnvelope(
            agent_id="AGT-01", event_type="token_activity", payload=token.model_dump()
        )

        if self.priority_queue:
            # Re-evaluations have higher priority than fresh snipes if they show activity
            priority = 2
            await self.priority_queue.enqueue(envelope.model_dump(), priority)

    async def _publish_migration(self, payload: dict):
        try:
            mint = payload.get("mint", "")
            if not mint or mint in self._seen_mints:
                return
            self._seen_mints.add(mint)

            envelope = AgentMessageEnvelope(
                agent_id="AGT-01",
                event_type="token_migrated",
                payload={
                    "mint": mint,
                    "program": "pumpswap",
                    "signature": payload.get("signature", ""),
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            if self.priority_queue:
                await self.priority_queue.enqueue(
                    envelope.model_dump(),
                    PriorityQueue.PRIORITY_MIGRATION,
                )
                queue_lengths = await self.priority_queue.get_queue_lengths()
                print(
                    f"AGT-01: Published token_migrated for {mint[:8]}..., queue: {queue_lengths['total']}/100"
                )
            else:
                print(f"AGT-01: Published token_migrated for {mint[:8]}...")

        except Exception as e:
            print(f"AGT-01: Error publishing migration: {e}")

    async def handle_helius_message(self, message: str):
        try:
            data = json.loads(message)
            if data.get("method") == "programNotification":
                logs = data["params"]["result"]["value"]["logs"]
                if "InitializeInstruction" in logs:
                    mint = self.extract_mint_from_logs(logs)
                    if mint:
                        envelope = AgentMessageEnvelope(
                            agent_id="AGT-01",
                            event_type="token_gradated",
                            payload={"mint": mint},
                        )
                        if self.priority_queue:
                            await self.priority_queue.enqueue(
                                envelope.model_dump(), PriorityQueue.PRIORITY_MIGRATION
                            )
                            queue_lengths = (
                                await self.priority_queue.get_queue_lengths()
                            )
                            print(
                                f"AGT-01: Queued gradated token (priority 1), queue: {queue_lengths['total']}/100"
                            )
                        else:
                            print(
                                f"AGT-01: WARNING - No priority queue configured, token not queued: {mint}"
                            )
        except Exception as e:
            print(f"AGT-01: Error handling Helius message: {e}")

    def extract_mint_from_logs(self, logs: list) -> str:
        for log in logs:
            match = re.search(r"initialize.*?([1-9A-HJ-NP-Za-km-z]{32,44})", log)
            if match:
                return match.group(1)
        return ""

    def check_rate_limit(self) -> bool:
        now = datetime.utcnow().timestamp()
        if now - self.last_reset >= 1:
            self.event_count = 0
            self.last_reset = now
        if self.event_count >= MAX_EVENTS_PER_SECOND:
            return False
        self.event_count += 1
        return True

    async def check_trading_state(self) -> bool:
        if not self.redis:
            return True

        try:
            kill_switch = await self.redis.get("mtus:kill_switch")
            if kill_switch == "active":
                if (
                    self.ws
                    and hasattr(self.ws, "close_code")
                    and self.ws.close_code is None
                ):
                    print("AGT-01: Kill switch active - closing WebSocket")
                    await self.ws.close()
                return False

            paused = await self.redis.get("mtus:trading_paused")
            if paused == "true":
                if (
                    self.ws
                    and hasattr(self.ws, "close_code")
                    and self.ws.close_code is None
                ):
                    print("AGT-01: Trading paused - closing WebSocket")
                    await self.ws.close()
                return False

            if not self.is_paper_mode and not is_operational_window_active():
                # Close PumpDev/Whistle WS
                if (
                    self.ws
                    and hasattr(self.ws, "close_code")
                    and self.ws.close_code is None
                ):
                    print("AGT-01: Outside operational window - closing PumpDev WebSocket")
                    await self.ws.close()
                
                # Close Helius WS
                if (
                    self.helius_ws
                    and hasattr(self.helius_ws, "close_code")
                    and self.helius_ws.close_code is None
                ):
                    print("AGT-01: Outside operational window - closing Helius WebSocket")
                    await self.helius_ws.close()
                
                return False

            return True
        except Exception as e:
            print(f"AGT-01: Error checking trading state: {e}")
            return True

    async def run(self):
        await self.connect_redis()
        self.running = True
        delay = RECONNECT_BASE_DELAY

        if not await self.connect_pumpdev(0):
            delay = min(delay * 2, RECONNECT_MAX_DELAY)

        while self.running:
            try:
                if not await self.check_trading_state():
                    await asyncio.sleep(5)
                    continue

                try:
                    if self.ws:
                        try:
                            ws_closed = self.ws.close_code is not None
                        except:
                            ws_closed = True
                    else:
                        ws_closed = True
                except Exception as e:
                    ws_closed = True
                    print(f"AGT-01: WS closed check error: {e}")

                if not self.ws or ws_closed:
                    print("AGT-01: WS not connected, using HTTP polling fallback")
                    await self.poll_for_tokens_http()

                    if not await self.connect_pumpdev(delay):
                        delay = min(delay * 2, RECONNECT_MAX_DELAY)
                        await asyncio.sleep(5)
                        continue
                    delay = RECONNECT_BASE_DELAY
                else:
                    try:
                        message = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                        if isinstance(message, bytes):
                            message = message.decode("utf-8")
                        payload = json.loads(message)
                        msg_type = payload.get("type") or payload.get("txType")
                        print(f"AGT-01: Received: type={msg_type}")
                        await self.handle_pumpdev_message(payload)
                    except asyncio.TimeoutError:
                        pass
                    except Exception as e:
                        print(f"AGT-01: Error: {e}")
                        if "stop" in str(e):
                            break
                        await asyncio.sleep(1)
            except Exception as e:
                print(f"AGT-01: Error in run loop body: {e}")
                if "stop" in str(e):
                    break
                await asyncio.sleep(1)

    async def stop(self):
        self.running = False

        if self.ws:
            try:
                await self.ws.send(json.dumps({"method": "unsubscribeNewToken"}))
                await self.ws.send(
                    json.dumps({"method": "unsubscribeTokenTrade", "keys": []})
                )
                await self.ws.send(
                    json.dumps({"method": "unsubscribeAccountTrade", "keys": []})
                )
                print("AGT-01: Sent unsubscribe messages")
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"AGT-01: Unsubscribe error: {e}")

        if self.ws:
            await self.ws.close()
            print("AGT-01: PumpDev WebSocket closed")

        if self.helius_ws:
            await self.helius_ws.close()
            print("AGT-01: Helius WebSocket closed")

        if self.redis:
            await self.redis.close()
            print("AGT-01: Redis connection closed")


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

    agent = NofxAgent(config)
    try:
        await agent.run()
    except KeyboardInterrupt:
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
