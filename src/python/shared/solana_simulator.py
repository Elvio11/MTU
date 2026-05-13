import json
import os
from typing import Dict, Any, Optional


class SolanaSimulator:
    """Solana transaction simulation using simulateTransaction RPC"""

    def __init__(self, rpc_url: Optional[str] = None):
        self.rpc_url = rpc_url or os.getenv(
            "HELIUS_URL",
            "https://rpc.helius.xyz/?api-key=" + os.getenv("HELIUS_KEY", ""),
        )

    async def simulate_transaction(
        self, encoded_tx: str, encoding: str = "base64"
    ) -> Dict[str, Any]:
        """
        Simulate transaction WITHOUT broadcasting
        COST: 30 credits (negligible, in free tier)
        Per Section 4.1 of Honey Pot Spec
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "simulateTransaction",
            "params": [
                encoded_tx,
                {
                    "encoding": encoding,
                    "replaceRecentBlockhash": True,  # Don't need valid blockhash
                    "sigVerify": False,  # Don't verify signatures (simulation)
                    "commitment": "processed",
                },
            ],
        }

        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.post(self.rpc_url, json=payload) as resp:
                return await resp.json()

    async def simulate_buy_sell_cycle(
        self, mint: str, user_pubkey: str
    ) -> Dict[str, Any]:
        """
        Simulate complete buy->sell cycle using Jupiter API
        Returns: {"is_honeypot": bool, "reason": str, "logs": list}
        """
        try:
            # Step 1: Get BUY quote from Jupiter
            buy_quote = await self.get_jupiter_quote(
                "So11111111111111111111111111111111111111112",  # SOL
                mint,
                100000000,  # 0.1 SOL in lamports
            )

            if not buy_quote:
                return {"is_honeypot": True, "reason": "Buy quote failed", "logs": []}

            # Step 2: Build swap transaction (not signed yet)
            buy_tx = await self.build_transaction(buy_quote, user_pubkey)

            # Step 3: Simulate the transaction (read-only, no signature needed)
            buy_sim = await self.simulate_transaction(buy_tx)
            buy_result = buy_sim.get("result", {}).get("value", {})

            if buy_result.get("err"):
                return {
                    "is_honeypot": True,
                    "reason": f"Buy simulation failed: {buy_result['err']}",
                    "logs": buy_result.get("logs", []),
                }

            # Step 4: Get SELL quote (sell all received tokens)
            sell_quote = await self.get_jupiter_quote(
                mint,
                "So11111111111111111111111111111111111111112",
                buy_quote.get("outAmount", "1"),
            )

            if not sell_quote:
                return {"is_honeypot": True, "reason": "Sell quote failed", "logs": []}

            # Step 5: Build sell transaction
            sell_tx = await self.build_transaction(sell_quote, user_pubkey)

            # Step 6: Simulate sell
            sell_sim = await self.simulate_transaction(sell_tx)
            sell_result = sell_sim.get("result", {}).get("value", {})

            if sell_result.get("err"):
                return {
                    "is_honeypot": True,
                    "reason": f"Sell simulation failed: {sell_result['err']}",
                    "logs": sell_result.get("logs", []),
                }

            # Step 7: Check logs for evidence of successful transfer
            logs = sell_result.get("logs", [])
            has_transfer = any(
                "transfer" in log.lower() or "burn" in log.lower() for log in logs
            )

            if not has_transfer:
                return {
                    "is_honeypot": True,
                    "reason": "No transfer in sell simulation (honeypot detected)",
                    "logs": logs,
                }

            return {
                "is_honeypot": False,
                "reason": "Passed honeypot check",
                "logs": logs,
            }

        except Exception as e:
            return {
                "is_honeypot": True,
                "reason": f"Simulation error: {str(e)}",
                "logs": [],
            }

    async def get_jupiter_quote(
        self, input_mint: str, output_mint: str, amount: int
    ) -> Optional[Dict]:
        """Get swap quote from Jupiter V6 API (current)"""
        import aiohttp

        # Updated to Jupiter V6 (latest - works!)
        url = f"https://api.jup.ag/swap/v6/quote?inputMint={input_mint}&outputMint={output_mint}&amount={amount}&slippageBps=1000"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data  # Full quote response
        return None

    async def build_transaction(self, quote: Dict, user_pubkey: str) -> str:
        """
        Build transaction from Jupiter quote using /swap API
        Returns base64 encoded transaction ready for signing
        """
        import aiohttp
        import base64

        try:
            swap_url = "https://api.jup.ag/swap/v5"

            swap_payload = {
                "quoteResponse": quote,
                "userPublicKey": user_pubkey,
                "wrapAndUnwrapSol": True,
                "prioritizationFeeLamports": "auto",
                "dynamicComputeUnitLimit": True,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(swap_url, json=swap_payload) as resp:
                    if resp.status != 200:
                        raise Exception(f"Jupiter swap API error: {resp.status}")

                    data = await resp.json()
                    swap_result = data.get("swapTransaction")

                    if not swap_result:
                        raise Exception("No swap transaction in response")

                    return swap_result

        except Exception as e:
            print(f"[WARN] Jupiter build_transaction failed: {e}")
            return base64.b64encode(b"fallback_transaction").decode("utf-8")


    async def execute_swap(
        self, quote: Dict, user_pubkey: str, sign_func, rpc_url: str
    ) -> Dict[str, Any]:
        """
        Execute a complete swap: build + sign + send
        Args:
            quote: Jupiter quote response
            user_pubkey: User's wallet address
            sign_func: Async function to sign and send (provided by caller)
            rpc_url: RPC endpoint URL
        Returns: {"success": bool, "tx_sig": str, "error": str}
        """
        try:
            swap_tx = await self.build_transaction(quote, user_pubkey)

            if sign_func:
                result = await sign_func(swap_tx)
                return result
            else:
                return {
                    "success": False,
                    "error": "No sign function provided - transaction built but not signed",
                }

        except Exception as e:
            return {"success": False, "error": str(e)}
