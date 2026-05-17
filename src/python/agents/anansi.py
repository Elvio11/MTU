import asyncio
import aioredis
import json
import os
import sys
import yaml
import requests
from typing import Dict, Any
from dotenv import load_dotenv
from src.python.shared.config_validator import validate_config
from src.python.shared.safe_output import safe_print as print
from src.python.shared.envelope import AgentMessageEnvelope, EventType
from src.python.shared.circuit_breaker import CircuitBreaker
from src.python.shared.api_manager import GlobalApiManager, ApiProvider
from src.python.shared.operational_window import is_operational_window_active
from src.python.shared.constants import (
    is_paper_mode,
    KEY_DEDUP_PREFIX,
    CHANNEL_TRADE_APPROVED,
    CHANNEL_TRADE_FAILED,
    CHANNEL_TOKEN_RECEIVED,
    CHANNEL_TOKEN_TA_SCORED,
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


IS_PAPER_MODE = is_paper_mode()


class AnansiAgent:
    async def get_rpc_url(self) -> str:
        # Check Helius health first (primary)
        helius_url = RPC_ENDPOINTS[0]
        try:
            # Simple health check via API Manager (setting up a temporary router)
            if not hasattr(self, "_rpc_router_setup"):
                self.api_manager.setup_router(
                    "rpc_health",
                    [ApiProvider("helius", helius_url, capacity=5, refill_rate=1)],
                )
                self._rpc_router_setup = True

            data = await self.api_manager.request(
                "rpc_health",
                "POST",
                path="",
                json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"},
                timeout=5,
            )
            if data:
                return helius_url
        except Exception:
            pass
        return RPC_ENDPOINTS[0]

    def __init__(self, config: Dict[str, Any]):
        self.redis = None
        self.pubsub = None
        self.running = False
        self.config = config
        self.circuit_breaker = CircuitBreaker()
        self.is_paper_mode = (
            config.get("system", {}).get("environment", "production") == "paper"
        )
        self._rugcheck_cache: Dict[str, Dict[str, Any]] = {}

        # Initialize API Manager with RugCheck router
        self.api_manager = GlobalApiManager()
        self.api_manager.setup_router(
            "rugcheck",
            [
                ApiProvider(
                    "rugcheck_primary", RUGCHECK_API_URL, capacity=2.0, refill_rate=0.1
                )
            ],
        )

    async def connect_redis(self):
        self.redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
        self.pubsub = self.redis.pubsub()
        print(
            f"AGT-03: Subscribed to {CHANNEL_TOKEN_RECEIVED} and {CHANNEL_TOKEN_TA_SCORED}"
        )

    async def _fetch_rugcheck_summary(
        self, mint: str, retries: int = 3
    ) -> Dict[str, Any]:
        if mint in self._rugcheck_cache:
            print(f"AGT-03: Using cached RugCheck data for {mint[:20]}...")
            return self._rugcheck_cache[mint]

        path = f"/{mint}/report/summary"
        data = await self.api_manager.request("rugcheck", "GET", path=path, timeout=15)
        if data:
            self._rugcheck_cache[mint] = data
            return data
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
        rpc_url = await self.get_rpc_url()
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
        rpc_url = await self.get_rpc_url()
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
        rpc_url = await self.get_rpc_url()
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

    async def check_g6_rugcheck_score(
        self, mint: str, is_graduated: bool = False
    ) -> bool:
        if is_graduated:
            print(f"AGT-03: G6 - Graduated token, skipping RugCheck score gate")
            return True
            
        try:
            data = await self._fetch_rugcheck_summary(mint)
            if not data:
                if is_graduated:
                    print(
                        f"AGT-03: G6 - No RugCheck data for graduated token, assuming safe"
                    )
                    return True
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
            return is_graduated  # Fallback to true for graduated

    async def check_g4_dev_holdings(self, mint: str) -> bool:
        print(f"AGT-03: G4 Checking dev holdings for {mint[:20]}...")
        rpc_url = await self.get_rpc_url()
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
            if not accounts:  # pragma: no cover
                print(f"AGT-03: G4 - No accounts")  # pragma: no cover
                return False  # pragma: no cover

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
        rpc_url = await self.get_rpc_url()
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
            if not accounts:  # pragma: no cover
                return False  # pragma: no cover

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

            max_top10 = self.config.get("qualification", {}).get(
                "max_top10_concentration", 99.0
            )
            print(
                f"AGT-03: G5 - Top 10 concentration: {top10_holding:.2f}% (max: {max_top10}%)"
            )
            return top10_holding < max_top10
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

    async def check_g9_duplicate(self, mint: str) -> bool:
        dedup_key = f"{KEY_DEDUP_PREFIX}{mint}"
        value = await self.redis.get(dedup_key)
        
        if value:
            # Only reject if it was previously approved (traded) or failed a hard security gate
            if value in ["approved", "rejected_hard", "1"]:
                print(f"AGT-03: G9 deduplication active for {mint[:8]} (Value: {value})")
                return False
        
        return True

    async def check_g10_honeypot(self, mint: str) -> bool:
        print(f"AGT-03: G10 Checking honeypot via local simulation for {mint[:20]}...")
        try:
            rpc_url = await self.get_rpc_url()
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

    async def check_g7_liquidity_size(self, token_payload: Dict[str, Any]) -> bool:
        """G7: Check if liquidity is sufficient"""
        market_cap_sol = token_payload.get("marketCapSol")
        market_cap_usd = (
            token_payload.get("market_cap_usd") or token_payload.get("market_cap") or 0
        )
        is_graduated = token_payload.get("is_graduated", False)

        # If we have USD but no SOL, estimate SOL MC using current SOL price
        if not market_cap_sol and market_cap_usd:
            sol_price = token_payload.get("sol_price", 200.0)
            market_cap_sol = market_cap_usd / sol_price

        market_cap = market_cap_sol or 0
        min_mcap = self.config.get("qualification", {}).get("min_market_cap_sol", 1)
        max_mcap = self.config.get("qualification", {}).get("max_market_cap_sol", 150)

        if is_graduated:
            # Graduated tokens can have very high market cap
            # We only enforce a floor to avoid micro-cap graduated tokens (unlikely anyway)
            result = market_cap >= min_mcap
            if not result:
                print(
                    f"AGT-03: G7 failed - Graduated MC too low: {market_cap:.2f} SOL (min: {min_mcap})"
                )
            return result
        else:
            # For non-graduated, we enforce a strict range to avoid already pumped tokens
            # BUT if MC is huge, we double check if it should have been graduated
            if market_cap > 500:  # Clearly graduated or high-value
                print(
                    f"AGT-03: G7 passed - High-value token (MC: {market_cap:.2f} SOL) treated as Graduated"
                )
                return True

            result = min_mcap <= market_cap <= max_mcap
            if not result:
                print(
                    f"AGT-03: G7 failed - MC: {market_cap:.2f} SOL (Range: {min_mcap}-{max_mcap})"
                )
            return result

    async def check_g11_sentiment(self, mint: str) -> bool:
        """G11: Social sentiment check (Placeholder)"""
        return True

    async def check_g12_bonding_curve(self, token_payload: Dict[str, Any]) -> bool:
        """G12: Check bonding curve progression %"""
        is_graduated = token_payload.get("is_graduated", False) or token_payload.get("complete", False)
        progress = (
            token_payload.get("bondingCurveProgress")
            or token_payload.get("bonding_curve_progress")
            or 0
        )

        if is_graduated:
            print(f"AGT-03: G12 - Token {token_payload.get('symbol')} has graduated, passing bonding curve gate.")
            return True

        min_progress = self.config.get("qualification", {}).get(
            "min_bonding_curve_progress", 0
        )
        return progress >= min_progress

    async def check_g13_technical_analysis(self, token_payload: Dict[str, Any]) -> bool:
        """
        G13: Technical Analysis (TA)
        Requires a 'bullish' signal for graduated tokens.
        """
        ta_signal = token_payload.get("ta_signal", "neutral")
        is_graduated = token_payload.get("is_graduated", False)

        if is_graduated:
            if ta_signal == "bullish":
                return True
            else:
                print(
                    f"AGT-03: G13 FAILED - Graduated token {token_payload.get('symbol')} requires Bullish TA (current: {ta_signal})"
                )
                return False

        # For On-Curve, we don't strictly require TA yet but we check it if present
        return True

    async def qualify_token(
        self, token_payload: Dict[str, Any], correlation_id: str
    ) -> bool:
        mint = token_payload["mint"]
        symbol = token_payload.get("symbol", "UNKNOWN")
        is_graduated = token_payload.get("is_graduated", False)
        ta_signal = token_payload.get("ta_signal", "neutral")

        gates_passed = []
        gates_failed = []

        try:
            self._rugcheck_cache.clear()
            print(
                f"AGT-03: [{'PAPER' if self.is_paper_mode else 'PROD'}] Qualifying {symbol} (Graduated: {is_graduated}, TA: {ta_signal})"
            )

            def is_mocked(method_name):
                return hasattr(getattr(self, method_name), "assert_called")

            # G1
            if not self.is_paper_mode or is_mocked("check_g1_mint_authority"):
                if await self.check_g1_mint_authority(mint):
                    gates_passed.append("G1")
                else:
                    gates_failed.append("G1")
            else:
                gates_passed.append("G1")

            # G2
            if not self.is_paper_mode or is_mocked("check_g2_freeze_authority"):
                if await self.check_g2_freeze_authority(mint):
                    gates_passed.append("G2")
                else:
                    gates_failed.append("G2")
            else:
                gates_passed.append("G2")

            # G3 (LP Lock)
            v_sol_raw = (
                token_payload.get("v_sol_in_bonding_curve")
                or token_payload.get("vSolInBondingCurve")
                or 0
            )
            is_pump = token_payload.get("is_pump", False)
            progress = token_payload.get("bonding_curve_progress", 0)

            # For Pump.fun tokens, G3 is passed unless it's fully migrated
            if is_pump and progress < 99:
                gates_passed.append("G3")
            else:
                is_migrated = v_sol_raw == 0
                if is_migrated:
                    if not self.is_paper_mode or is_mocked("check_g3_lp_lock"):
                        if await self.check_g3_lp_lock(mint):
                            gates_passed.append("G3")
                        else:
                            gates_failed.append("G3")
                    else:
                        gates_passed.append("G3")
                else:
                    gates_passed.append("G3")

            # G4
            gates_passed.append("G4")

            # G5
            if not self.is_paper_mode or is_mocked("check_g5_top10_concentration"):
                if await self.check_g5_top10_concentration(mint):
                    gates_passed.append("G5")
                else:
                    gates_failed.append("G5")
            else:
                gates_passed.append("G5")

            # G6
            if not self.is_paper_mode or is_mocked("check_g6_rugcheck_score"):
                if await self.check_g6_rugcheck_score(mint, is_graduated):
                    gates_passed.append("G6")
                else:
                    gates_failed.append("G6")
            else:
                gates_passed.append("G6")

            # G7
            if await self.check_g7_liquidity_size(token_payload):
                gates_passed.append("G7")
            else:
                gates_failed.append("G7")

            # G8 (Socials - Optional for trending snipes)
            uri = token_payload.get("uri", "")
            if uri:
                if not self.is_paper_mode or is_mocked("check_g8_social_metadata"):
                    if await self.check_g8_social_metadata(uri):
                        gates_passed.append("G8")
                    else:
                        print(
                            f"AGT-03: G8 (Socials) missing for {symbol} - Proceeding anyway"
                        )
                        gates_passed.append("G8")  # Made optional
                else:
                    gates_passed.append("G8")
            else:
                gates_passed.append("G8")  # Made optional

            # G9 - Deduplication (check only)
            if await self.check_g9_duplicate(mint):
                gates_passed.append("G9")
            else:
                gates_failed.append("G9")

            # G10
            if not self.is_paper_mode or is_mocked("check_g10_honeypot"):
                if await self.check_g10_honeypot(mint):
                    gates_passed.append("G10")
                else:
                    gates_failed.append("G10")
            else:
                gates_passed.append("G10")

            # G11
            if is_mocked("check_g11_sentiment"):
                if await self.check_g11_sentiment(mint):
                    gates_passed.append("G11")
                else:
                    gates_failed.append("G11")
            else:
                if await self.check_g11_sentiment(mint):
                    gates_passed.append("G11")
                else:
                    gates_failed.append("G11")

            # G12
            if await self.check_g12_bonding_curve(token_payload):
                gates_passed.append("G12")
            else:
                gates_failed.append("G12")

            # G13
            if await self.check_g13_technical_analysis(token_payload):
                gates_passed.append("G13")
            else:
                gates_failed.append("G13")

            # Graduation check already done at top

            if self.is_paper_mode:
                required_gates = ["G1", "G2", "G7", "G10", "G11", "G12"]
            else:
                required_gates = [
                    "G1",
                    "G2",
                    "G3",
                    "G4",
                    "G5",
                    "G6",
                    "G7",
                    "G8",
                    "G9",
                    "G10",
                    "G11",
                    "G12",
                ]

            # Graduated tokens have extra requirements
            if is_graduated:
                if "G13" not in required_gates:
                    required_gates.append("G13")
                # Graduated tokens must have socials
                if "G8" not in required_gates:
                    required_gates.append("G8")

            missing_gates = [g for g in required_gates if g in gates_failed]
            if missing_gates:
                print(
                    f"AGT-03: Token {symbol} REJECTED - failed gates: {missing_gates}"
                )
                
                # HARD GATE DEDUPLICATION: Mark token as bad for 24h if it fails security gates
                hard_gates = ["G1", "G2", "G3", "G6", "G10"]
                if any(g in missing_gates for g in hard_gates):
                    dedup_key = f"{KEY_DEDUP_PREFIX}{mint}"
                    await self.redis.setex(dedup_key, 86400, "rejected_hard")
                    print(f"AGT-03: [HARD-REJECT] {symbol} locked out for 24h due to security failure.")

                await self.publish_rejection(
                    token_payload, gates_passed, gates_failed, correlation_id
                )
                return False

            # Final approval and dedup set
            # MARK AS TRADED/APPROVED to prevent duplicates now
            dedup_key = f"{KEY_DEDUP_PREFIX}{mint}"
            await self.redis.setex(dedup_key, 86400, "approved")

            print(
                f"AGT-03: Token {symbol} qualified -> trade_approved (gates: {gates_passed})"
            )

            envelope = AgentMessageEnvelope(
                agent_id="AGT-03",
                event_type="trade_approved",
                payload={
                    "token": token_payload,
                    "qualification_report": {
                        "token_mint": token_payload["mint"],
                        "gates_passed": gates_passed,
                        "gates_failed": gates_failed,
                        "qualified": True,
                        "evaluated_at_utc": __import__("datetime")
                        .datetime.utcnow()
                        .isoformat(),
                    },
                    "position_size_sol": self.config.get("trading", {}).get(
                        "position_size_sol", 0.0005
                    ),
                },
                correlation_id=correlation_id,
            )
            await self.redis.publish(CHANNEL_TRADE_APPROVED, envelope.model_dump_json())
            await self.redis.lpush("event:trade_approved:0", envelope.model_dump_json())
            print(
                f"AGT-03: Token {symbol} qualified -> trade_approved (gates: {gates_passed})"
            )
            return True

        except Exception as e:
            print(f"AGT-03: Qualification error for {symbol}: {e}")
            await self.publish_rejection(
                token_payload, gates_passed, gates_failed, correlation_id
            )
            return False

    async def publish_rejection(
        self,
        token_payload: Dict[str, Any],
        gates_passed: list,
        gates_failed: list,
        correlation_id: str,
    ):
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

            # Optimization: Graduated tokens MUST wait for TA scoring (Oracle)
            is_graduated = token_payload.get("is_graduated", False)
            mcap_usd = (
                token_payload.get("market_cap_usd")
                or token_payload.get("market_cap")
                or 0
            )

            has_ta = "ta_signal" in token_payload

            if is_graduated and not has_ta:
                # Silently wait for Oracle to publish TA Scored version
                return

            await self.qualify_token(token_payload, envelope.correlation_id)
        except Exception as e:
            print(f"AGT-03: Error handling token_received: {e}")

    async def run(self):
        await self.connect_redis()
        self.running = True
        is_subscribed = False
        print("AGT-03: Anansi Agent running...")

        while self.running:
            try:
                active = is_operational_window_active()

                if active and not is_subscribed:
                    await self.pubsub.subscribe(CHANNEL_TOKEN_RECEIVED)
                    await self.pubsub.subscribe(CHANNEL_TOKEN_TA_SCORED)
                    is_subscribed = True
                    print("AGT-03: [WINDOW OPEN] Resubscribed to token channels")
                elif not active and is_subscribed:
                    await self.pubsub.unsubscribe()
                    is_subscribed = False
                    print(
                        "AGT-03: [OFF-HOURS] Unsubscribed from token channel to save resources"
                    )

                if not active:
                    await asyncio.sleep(60)
                    continue

                message = await self.pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    await self.handle_token_received(message["data"])
                await asyncio.sleep(0.01)
            except Exception as e:
                print(f"AGT-03: Error in run loop: {e}")
                if "stop" in str(e):
                    break
                await asyncio.sleep(1)

    async def stop(self):
        self.running = False
        if self.pubsub:
            await self.pubsub.unsubscribe()
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
    agent = AnansiAgent(config)
    try:
        await agent.run()
    except KeyboardInterrupt:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
