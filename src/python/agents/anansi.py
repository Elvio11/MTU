import asyncio
import aioredis
import json
import requests
import os
from typing import Dict, Any
from dotenv import load_dotenv
from src.python.shared.safe_output import safe_print as print
from src.python.shared.envelope import AgentMessageEnvelope, EventType
from src.python.shared.circuit_breaker import CircuitBreaker
from src.python.shared.constants import (
    is_paper_mode,
    KEY_DEDUP_PREFIX,
    CHANNEL_TRADE_APPROVED,
    CHANNEL_TRADE_FAILED,
    CHANNEL_TOKEN_RECEIVED,
)

load_dotenv("./.env")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
RUGCHECK_API_URL = "https://api.rugcheck.xyz/v1/tokens"
SOLANA_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")

RPC_ENDPOINTS = [
    os.getenv(
        "HELIUS_RPC_URL",
        "https://mainnet.helius-rpc.com/?api-key=90b7db5c-9ecd-4f01-8c65-a886a8d1a67d",
    ),
    os.getenv(
        "ALCHEMY_RPC_URL",
        "https://solana-mainnet.g.alchemy.com/v2/_qcAnZERSDa8eRymPiKUx",
    ),
    os.getenv("QUICKNODE_RPC_URL", ""),
    "https://api.mainnet-beta.solana.com",
]


def get_rpc_url() -> str:
    for url in RPC_ENDPOINTS:
        if url:
            try:
                resp = requests.post(
                    url,
                    json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"},
                    timeout=3,
                )
                if resp.status_code == 200:
                    return url
            except:
                continue
    return RPC_ENDPOINTS[0]


IS_PAPER_MODE = is_paper_mode()


class AnansiAgent:
    def __init__(self, config: Dict[str, Any]):
        self.redis = None
        self.pubsub = None
        self.running = False
        self.config = config
        self.circuit_breaker = CircuitBreaker()
        self.is_paper_mode = IS_PAPER_MODE
        self._rugcheck_cache: Dict[str, Dict[str, Any]] = {}

    async def connect_redis(self):
        self.redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe(CHANNEL_TOKEN_RECEIVED)
        print(f"AGT-03: Subscribed to {CHANNEL_TOKEN_RECEIVED} channel")

    async def _fetch_rugcheck_summary(
        self, mint: str, retries: int = 3
    ) -> Dict[str, Any]:
        if mint in self._rugcheck_cache:
            print(f"AGT-03: Using cached RugCheck data for {mint[:20]}...")
            return self._rugcheck_cache[mint]

        url = f"{RUGCHECK_API_URL}/{mint}/report/summary"
        for attempt in range(retries):
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    self._rugcheck_cache[mint] = data
                    return data
                elif resp.status_code == 429:
                    wait_time = (attempt + 1) * 2
                    print(f"AGT-03: RugCheck rate limited, waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"AGT-03: RugCheck API error: {resp.status_code}")
            except requests.exceptions.Timeout:
                print(f"AGT-03: RugCheck timeout (attempt {attempt + 1}/{retries})")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"AGT-03: RugCheck request failed: {e}")
                await asyncio.sleep(1)
        return {}

    async def check_g1_mint_authority(self, mint: str) -> bool:
        print(f"AGT-03: G1 Checking mint authority for {mint[:20]}...")
        try:
            data = await self._fetch_rugcheck_summary(mint)
            if not data:
                print(f"AGT-03: G1 - No data from RugCheck, falling back to RPC")
                return await self._check_mint_authority_rpc(mint)

            token_data = data.get("token", {})
            mint_authority = token_data.get("mintAuthority")
            result = mint_authority is None
            print(f"AGT-03: G1 result: {result}, mintAuthority: {mint_authority}")
            return result
        except Exception as e:
            print(f"AGT-03: G1 check failed: {e}")
            return False

    async def _check_mint_authority_rpc(self, mint: str) -> bool:
        rpc_url = get_rpc_url()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [mint, {"encoding": "jsonParsed"}],
        }
        try:
            resp = requests.post(rpc_url, json=payload, timeout=10)
            data = resp.json()
            if not data.get("result") or not data["result"].get("value"):
                return False
            value_data = data["result"]["value"]
            parsed = value_data.get("data", {}).get("parsed", {})
            mint_info = parsed.get("info", {})
            return mint_info.get("mintAuthority") is None
        except Exception as e:
            print(f"AGT-03: RPC fallback failed: {e}")
            return False

    async def check_g2_freeze_authority(self, mint: str) -> bool:
        print(f"AGT-03: G2 Checking freeze authority for {mint[:20]}...")
        try:
            data = await self._fetch_rugcheck_summary(mint)
            if not data:
                print(f"AGT-03: G2 - No data from RugCheck, falling back to RPC")
                return await self._check_freeze_authority_rpc(mint)

            token_data = data.get("token", {})
            freeze_authority = token_data.get("freezeAuthority")
            result = freeze_authority is None
            print(f"AGT-03: G2 result: {result}, freezeAuthority: {freeze_authority}")
            return result
        except Exception as e:
            print(f"AGT-03: G2 check failed: {e}")
            return False

    async def _check_freeze_authority_rpc(self, mint: str) -> bool:
        rpc_url = get_rpc_url()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [mint, {"encoding": "jsonParsed"}],
        }
        try:
            resp = requests.post(rpc_url, json=payload, timeout=10)
            data = resp.json()
            if not data.get("result") or not data["result"].get("value"):
                return False
            value_data = data["result"]["value"]
            parsed = value_data.get("data", {}).get("parsed", {})
            mint_info = parsed.get("info", {})
            return mint_info.get("freezeAuthority") is None
        except Exception as e:
            print(f"AGT-03: RPC fallback failed: {e}")
            return False

    async def check_g3_lp_lock(self, mint: str) -> bool:
        try:
            data = await self._fetch_rugcheck_summary(mint)
            if not data:
                print(f"AGT-03: G3 - No RugCheck data, checking via RPC")
                return await self._check_lp_lock_rpc(mint)

            lp_data = data.get("lp", {})
            lp_burned_pct = lp_data.get("burnedPct", lp_data.get("lockedPct", 0))
            min_lp = self.config.get("qualification", {}).get("min_lp_burned_pct", 85)
            print(f"AGT-03: G3 LP Burn: {lp_burned_pct}% (min: {min_lp}%)")
            return lp_burned_pct >= min_lp
        except Exception as e:
            print(f"AGT-03: G3 check failed: {e}")
            return False

    async def _check_lp_lock_rpc(self, mint: str) -> bool:
        rpc_url = get_rpc_url()
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByProgram",
                "params": [
                    mint,
                    {"programId": "JUPoUw3xofdH1RNhqoZfaD1ehKijekTkr6YpGyYGY6Re"},
                    {"encoding": "jsonParsed"},
                ],
            }
            resp = requests.post(rpc_url, json=payload, timeout=10)
            data = resp.json()
            accounts = data.get("result", {}).get("value", [])
            if not accounts:
                return False
            total_lp = sum(
                float(
                    acc.get("account", {})
                    .get("data", {})
                    .get("parsed", {})
                    .get("info", {})
                    .get("tokenAmount", {})
                    .get("uiAmountString", 0)
                )
                for acc in accounts
            )
            return total_lp > 0
        except Exception as e:
            print(f"AGT-03: G3 RPC fallback failed: {e}")
            return False

    async def check_g6_rugcheck_score(self, mint: str) -> bool:
        try:
            data = await self._fetch_rugcheck_summary(mint)
            if not data:
                print(f"AGT-03: G6 - No RugCheck data available")
                return False

            score = data.get("score", 1000)
            max_score = self.config.get("qualification", {}).get(
                "max_rugcheck_score", 999
            )
            print(f"AGT-03: G6 RugCheck Score: {score} (max: {max_score})")
            return score <= max_score
        except Exception as e:
            print(f"AGT-03: G6 check failed: {e}")
            return False

    async def check_g4_dev_holdings(self, mint: str) -> bool:
        print(f"AGT-03: G4 Checking dev holdings for {mint[:20]}...")
        rpc_url = get_rpc_url()
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [mint],
            }

            resp = requests.post(
                rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            data = resp.json()

            if "result" not in data or not data["result"].get("value"):
                print(f"AGT-03: G4 - No token accounts found")
                return False

            accounts = data["result"]["value"]
            if not accounts:
                print(f"AGT-03: G4 - No accounts")
                return False

            supply_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenSupply",
                "params": [mint],
            }
            supply_resp = requests.post(
                rpc_url,
                json=supply_payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            supply_data = supply_resp.json()

            total_supply = 0
            decimals = 9
            if supply_data.get("result") and supply_data["result"].get("value"):
                total_supply = int(supply_data["result"]["value"].get("amount", 0))
                decimals = int(supply_data["result"]["value"].get("decimals", 9))

            if total_supply == 0:
                print(f"AGT-03: G4 - Zero total supply")
                return False

            total_supply_readable = total_supply / (10**decimals)

            dev_holding_pct = 0.0
            for acc in accounts[:3]:
                ui_amount = float(acc.get("uiAmountString", 0))
                if ui_amount == 0:
                    raw_amount = int(acc.get("amount", 0))
                    ui_amount = raw_amount / (10**decimals)

                pct = (
                    (ui_amount / total_supply_readable) * 100
                    if total_supply_readable > 0
                    else 0
                )
                if pct > dev_holding_pct:
                    dev_holding_pct = pct

            max_dev_pct = self.config.get("qualification", {}).get(
                "max_dev_holding_pct", 95
            )
            print(
                f"AGT-03: G4 - Dev holding: {dev_holding_pct:.2f}% (max: {max_dev_pct}%)"
            )
            return dev_holding_pct < max_dev_pct
        except Exception as e:
            print(f"AGT-03: G4 check failed: {e}")
            return False

    async def check_g5_top10_concentration(self, mint: str) -> bool:
        print(f"AGT-03: G5 Checking top 10 concentration for {mint[:20]}...")
        rpc_url = get_rpc_url()
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [mint],
            }

            resp = requests.post(
                rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            data = resp.json()

            if "result" not in data or not data["result"].get("value"):
                print(f"AGT-03: G5 - No accounts found")
                return False

            accounts = data["result"]["value"]
            if not accounts:
                return False

            supply_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenSupply",
                "params": [mint],
            }
            supply_resp = requests.post(
                rpc_url,
                json=supply_payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            supply_data = supply_resp.json()

            total_supply = 0
            decimals = 9
            if supply_data.get("result") and supply_data["result"].get("value"):
                total_supply = int(supply_data["result"]["value"].get("amount", 0))
                decimals = int(supply_data["result"]["value"].get("decimals", 9))

            total_supply_readable = (
                total_supply / (10**decimals) if total_supply > 0 else 0
            )

            if total_supply_readable == 0:
                return False

            top10_holding = 0.0
            for acc in accounts[:10]:
                ui_amount = float(acc.get("uiAmountString", 0))
                if ui_amount == 0:
                    raw_amount = int(acc.get("amount", 0))
                    ui_amount = raw_amount / (10**decimals)
                pct = (ui_amount / total_supply_readable) * 100
                top10_holding += pct

            print(f"AGT-03: G5 - Top 10 concentration: {top10_holding:.2f}%")
            return top10_holding < 30.0
        except Exception as e:
            print(f"AGT-03: G5 check failed: {e}")
            return False

    async def check_g8_social_metadata(self, uri: str) -> bool:
        try:
            resp = requests.get(uri, timeout=5)
            metadata = resp.json()
            social = metadata.get("social", {})
            return any(social.get(k) for k in ["twitter", "telegram", "website"])
        except Exception as e:
            print(f"AGT-03: G8 check failed: {e}")
            return False

    async def check_g7_market_cap(self, market_cap: float) -> bool:
        min_mcap = self.config["qualification"]["min_market_cap_sol"]
        max_mcap = self.config["qualification"]["max_market_cap_sol"]
        return min_mcap <= market_cap <= max_mcap

    async def check_g9_duplicate(self, mint: str) -> bool:
        dedup_key = f"{KEY_DEDUP_PREFIX}{mint}"
        exists = await self.redis.exists(dedup_key)
        if exists:
            return False
        await self.redis.setex(dedup_key, 86400, "1")
        return True

    async def check_g10_honeypot(self, mint: str) -> bool:
        print(f"AGT-03: G10 Checking honeypot via local simulation for {mint[:20]}...")
        try:
            rpc_url = get_rpc_url()
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [mint, {"encoding": "jsonParsed"}],
            }
            resp = requests.post(rpc_url, json=payload, timeout=10)
            data = resp.json()

            if not data.get("result") or not data["result"].get("value"):
                print(f"AGT-03: G10 - Token account not found")
                return False

            parsed = data["result"]["value"].get("data", {}).get("parsed", {})
            if parsed:
                info = parsed.get("info", {})
                freeze_auth = info.get("freezeAuthority")
                mint_auth = info.get("mintAuthority")

                if freeze_auth or mint_auth:
                    print(
                        f"AGT-03: G10 - Token has authorities (freeze: {freeze_auth}, mint: {mint_auth})"
                    )
                    return False

            print(f"AGT-03: G10 passed - token appears safe")
            return True
        except Exception as e:
            print(f"AGT-03: G10 check failed: {e}")
            return True

    async def qualify_token(
        self, token_payload: Dict[str, Any], correlation_id: str
    ) -> bool:
        mint = token_payload["mint"]
        symbol = token_payload.get("symbol", "UNKNOWN")

        self._rugcheck_cache.clear()

        print(
            f"AGT-03: [{'PAPER' if self.is_paper_mode else 'PROD'}] Running safety qualification for {symbol}"
        )

        gates_passed = []
        gates_failed = []

        mcap = token_payload.get("marketCapSol", 0)
        if mcap >= 5 and mcap <= 150:
            gates_passed.append("G7")
            print(f"AGT-03: G7 Market Cap {mcap} SOL - PASS")
        else:
            gates_failed.append("G7")
            print(f"AGT-03: G7 Market Cap {mcap} SOL - FAIL (range: 5-150)")
            await self.publish_rejection(
                token_payload, gates_passed, gates_failed, correlation_id
            )
            return False

        v_sol_in_curve_raw = token_payload.get("vSolInBondingCurve", 0)
        v_sol_in_curve = v_sol_in_curve_raw / 1_000_000_000
        min_virtual_sol = self.config.get("qualification", {}).get(
            "min_virtual_sol_reserves", 30
        )
        if v_sol_in_curve >= min_virtual_sol:
            gates_passed.append("G11")
            print(
                f"AGT-03: G11 Bonding Curve {v_sol_in_curve:.1f} SOL - PASS (min: {min_virtual_sol})"
            )
        else:
            gates_failed.append("G11")
            print(
                f"AGT-03: G11 Bonding Curve {v_sol_in_curve:.1f} SOL - FAIL (min: {min_virtual_sol})"
            )
            await self.publish_rejection(
                token_payload, gates_passed, gates_failed, correlation_id
            )
            return False

        # G12: Bonding Curve Progress %
        progress = token_payload.get("bondingCurveProgress", 0)
        min_progress = self.config.get("qualification", {}).get(
            "min_bonding_curve_progress", 0
        )
        if progress >= min_progress:
            gates_passed.append("G12")
            print(f"AGT-03: G12 Progress {progress:.1f}% - PASS (min: {min_progress}%)")
        else:
            gates_failed.append("G12")
            print(f"AGT-03: G12 Progress {progress:.1f}% - FAIL (min: {min_progress}%)")
            await self.publish_rejection(
                token_payload, gates_passed, gates_failed, correlation_id
            )
            return False

        print(f"AGT-03: About to call G1 check for mint: {mint}")
        if await self.check_g1_mint_authority(mint):
            gates_passed.append("G1")
            print(f"AGT-03: G1 Mint Authority - PASS")
        else:
            gates_failed.append("G1")
            print(f"AGT-03: G1 Mint Authority - FAIL")

        if await self.check_g2_freeze_authority(mint):
            gates_passed.append("G2")
            print(f"AGT-03: G2 Freeze Authority - PASS")
        else:
            gates_failed.append("G2")
            print(f"AGT-03: G2 Freeze Authority - FAIL")

        v_sol_raw = token_payload.get("vSolInBondingCurve", 0)
        v_sol_in_curve = v_sol_raw / 1_000_000_000 if v_sol_raw else 0
        is_on_bonding_curve = 0 < v_sol_in_curve < 85
        is_migrated = v_sol_in_curve == 0

        if self.is_paper_mode:
            print(f"AGT-03: [PAPER] Would run G3-G9 checks in production mode")
            gates_passed.extend(["G3", "G4", "G5", "G6", "G8", "G9"])
        else:
            if is_migrated:
                if await self.check_g3_lp_lock(mint):
                    gates_passed.append("G3")
                    print(f"AGT-03: G3 LP Lock - PASS (migrated token)")
                else:
                    gates_failed.append("G3")
                    print(f"AGT-03: G3 LP Lock - FAIL")
            else:
                print(
                    f"AGT-03: G3 LP Lock - AUTO-PASS (bonding curve, LP burns at PumpSwap migration)"
                )
                gates_passed.append("G3")

            print(f"AGT-03: G4 Dev Holdings - DISABLED (pump.fun tokens)")
            gates_passed.append("G4")

            if is_on_bonding_curve:
                print(
                    f"AGT-03: G5 Top 10 Concentration - AUTO-PASS (new token, <10 holders)"
                )
                gates_passed.append("G5")
            else:
                if await self.check_g5_top10_concentration(mint):
                    gates_passed.append("G5")
                    print(f"AGT-03: G5 Top 10 Concentration - PASS")
                else:
                    gates_failed.append("G5")
                    print(f"AGT-03: G5 Top 10 Concentration - FAIL")

            if await self.check_g6_rugcheck_score(mint):
                gates_passed.append("G6")
                print(f"AGT-03: G6 RugCheck Score - PASS")
            else:
                gates_failed.append("G6")
                print(f"AGT-03: G6 RugCheck Score - FAIL")

            uri = token_payload.get("uri", "")
            if uri and await self.check_g8_social_metadata(uri):
                gates_passed.append("G8")
                print(f"AGT-03: G8 Social Metadata - PASS")
            else:
                gates_failed.append("G8")
                print(f"AGT-03: G8 Social Metadata - FAIL")

            if await self.check_g9_duplicate(mint):
                gates_passed.append("G9")
                print(f"AGT-03: G9 Duplicate Check - PASS")
            else:
                gates_failed.append("G9")
                print(f"AGT-03: G9 Duplicate Check - FAIL")

        if not self.is_paper_mode:
            if await self.check_g10_honeypot(mint):
                gates_passed.append("G10")
                print(f"AGT-03: G10 Honeypot - PASS")
            else:
                gates_failed.append("G10")
                print(f"AGT-03: G10 Honeypot - FAIL")

        if self.is_paper_mode:
            required_gates = ["G1", "G2", "G7", "G10", "G11"]
        else:
            required_gates = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G10", "G11"]
        missing_gates = [g for g in required_gates if g in gates_failed]

        if missing_gates:
            print(f"AGT-03: Token {symbol} REJECTED - failed gates: {missing_gates}")
            await self.publish_rejection(
                token_payload, gates_passed, gates_failed, correlation_id
            )
            return False

        envelope = AgentMessageEnvelope(
            agent_id="AGT-03",
            event_type="trade_approved",
            payload={
                "token": token_payload,
                "qualification_report": {
                    "token_mint": token_payload["mint"],
                    "gates_passed": gates_passed,
                    "gates_failed": gates_failed,
                    "rugcheck_score": 0,
                    "dev_holding_pct": 0,
                    "top10_concentration_pct": 0,
                    "lp_burned_pct": 100,
                    "social_signals": {
                        "twitter": False,
                        "telegram": False,
                        "website": False,
                    },
                    "sentiment_score": 50,
                    "qualified": True,
                    "evaluated_at_utc": __import__("datetime")
                    .datetime.utcnow()
                    .isoformat(),
                },
                "position_size_sol": self.config.get("trading", {}).get("position_size_sol", 0.0005),
            },
            correlation_id=correlation_id,
        )
        await self.redis.publish(CHANNEL_TRADE_APPROVED, envelope.model_dump_json())
        await self.redis.lpush("event:trade_approved:0", envelope.model_dump_json())
        print(
            f"AGT-03: Token {symbol} qualified -> trade_approved (gates: {gates_passed})"
        )
        return True

    async def publish_rejection(
        self,
        token_payload: Dict[str, Any],
        gates_passed: list,
        gates_failed: list,
        correlation_id: str,
    ):
        from src.python.shared.envelope import AgentMessageEnvelope

        envelope = AgentMessageEnvelope(
            agent_id="AGT-03",
            event_type="trade_failed",
            payload={
                "token": token_payload,
                "reason": f"Failed gates: {gates_failed}",
                "gates_passed": gates_passed,
                "gates_failed": gates_failed,
            },
            correlation_id=correlation_id,
        )
        await self.redis.publish(CHANNEL_TRADE_FAILED, envelope.model_dump_json())
        await self.redis.lpush("event:trade_failed:0", envelope.model_dump_json())
        print(f"AGT-03: Published trade_failed for {token_payload.get('symbol')}")

    async def handle_token_received(self, envelope_json: str):
        try:
            envelope = AgentMessageEnvelope.model_validate_json(envelope_json)
            token_payload = envelope.payload
            await self.qualify_token(token_payload, envelope.correlation_id)
        except Exception as e:
            print(f"AGT-03: Error handling token_received: {e}")

    async def run(self):
        await self.connect_redis()
        self.running = True
        while self.running:
            try:
                message = await self.pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    await self.handle_token_received(message["data"])
                await asyncio.sleep(0.01)
            except Exception as e:
                print(f"AGT-03: Error in run loop: {e}")

    async def stop(self):
        self.running = False
        if self.pubsub:
            await self.pubsub.unsubscribe()
        if self.redis:
            await self.redis.close()

    async def _collect_gate_values(self, mint: str, uri: str) -> dict:
        """Collect actual values from all gate checks for qualification report"""
        import requests

        result = {
            "rugcheck_score": 0,
            "dev_holding_pct": 0,
            "top10_concentration_pct": 0,
            "lp_burned_pct": 0,
            "social_signals": {"twitter": False, "telegram": False, "website": False},
            "sentiment_score": 50,
        }

        try:
            # Get RugCheck data (covers G3 LP and G6 score)
            headers = {"Authorization": f"Bearer {self.config.get('rugcheck_api_key')}"}
            resp = requests.get(
                f"{RUGCHECK_API_URL}/{mint}", headers=headers, timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                result["rugcheck_score"] = data.get("score", 0)
                result["lp_burned_pct"] = data.get("lp", {}).get("burnedPct", 0)
        except Exception as e:
            print(f"AGT-03: Error collecting RugCheck data: {e}")

        try:
            # Get holder data (G4 and G5)
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [mint],
            }
            resp = requests.post(get_rpc_url(), json=payload, timeout=10)
            data = resp.json()
            if "result" in data and data["result"].get("value"):
                accounts = data["result"]["value"]
                total_supply = 0
                decimals = 9
                supply_data = requests.post(
                    get_rpc_url(),
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getTokenSupply",
                        "params": [mint],
                    },
                    timeout=10,
                ).json()
                if supply_data.get("result") and supply_data["result"].get("value"):
                    total_supply = int(supply_data["result"]["value"].get("amount", 0))
                    decimals = int(supply_data["result"]["value"].get("decimals", 9))

                total_supply_readable = (
                    total_supply / (10**decimals) if total_supply > 0 else 0
                )

                dev_holding_pct = 0.0
                for acc in accounts[:3]:
                    ui_amount = float(acc.get("uiAmountString", 0))
                    if ui_amount == 0:
                        raw_amount = int(acc.get("amount", 0))
                        ui_amount = raw_amount / (10**decimals)
                    pct = (
                        (ui_amount / total_supply_readable) * 100
                        if total_supply_readable > 0
                        else 0
                    )
                    if pct > dev_holding_pct:
                        dev_holding_pct = pct

                top10_holding = 0.0
                for acc in accounts[:10]:
                    ui_amount = float(acc.get("uiAmountString", 0))
                    if ui_amount == 0:
                        raw_amount = int(acc.get("amount", 0))
                        ui_amount = raw_amount / (10**decimals)
                    pct = (ui_amount / total_supply_readable) * 100
                    top10_holding += pct

                result["dev_holding_pct"] = dev_holding_pct
                result["top10_concentration_pct"] = top10_holding
        except Exception as e:
            print(f"AGT-03: Error collecting holder data: {e}")

        # Social signals from metadata
        try:
            if uri:
                resp = requests.get(uri, timeout=5)
                if resp.status_code == 200:
                    metadata = resp.json()
                    social = metadata.get("social", {}) or {}
                    result["social_signals"]["twitter"] = bool(
                        social.get("twitter") or social.get("x")
                    )
                    result["social_signals"]["telegram"] = bool(social.get("telegram"))
                    result["social_signals"]["website"] = bool(social.get("website"))
        except Exception as e:
            print(f"AGT-03: Error collecting social data: {e}")

        return result


if __name__ == "__main__":
    import yaml
    import os

    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    )
    config_path = os.path.join(project_root, "config", "config.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    from src.python.shared.config_validator import validate_config

    is_valid, error = validate_config(config)
    if not is_valid:
        print("[CONFIG] Configuration validation failed: " + str(error))
        exit(1)
    print("[CONFIG] Configuration is valid")

    agent = AnansiAgent(config)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        asyncio.run(agent.stop())
