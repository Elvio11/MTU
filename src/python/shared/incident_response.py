import asyncio
import aiohttp
import json
import time
from typing import Optional, Dict, Any
from datetime import datetime


class IncidentResponse:
    """P0/P1 incident response procedures for real trading"""

    def __init__(self, telegram_token: str = "", admin_chat_id: str = ""):
        self.telegram_token = telegram_token
        self.admin_chat_id = admin_chat_id
        self.incident_log: list = []
        self.emergency_mode = False

    async def send_telegram_alert(self, message: str, priority: str = "HIGH"):
        """Send urgent Telegram alert"""
        if not self.telegram_token or not self.admin_chat_id:
            print(f"[ALERT-{priority}] {message}")
            return

        try:
            async with aiohttp.ClientSession() as session:
                await session.get(
                    f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                    params={
                        "chat_id": self.admin_chat_id,
                        "text": f"[{priority}] {message}",
                        "parse_mode": "HTML",
                    },
                )
        except Exception as e:
            print(f"Telegram alert failed: {e}")

    async def handle_p0_sniper_compromise(self, reason: str, wallet_address: str = ""):
        """P0: Sniper Wallet compromise - immediate action required"""
        print(f"🚨 P0 INCIDENT: Sniper Wallet Compromise - {reason}")

        incident = {
            "type": "P0_SNIFFER_COMPROMISE",
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "wallet": wallet_address,
            "actions_taken": [],
        }

        await self.send_telegram_alert(
            "🚨 <b>P0 CRITICAL: Sniper Wallet Compromised</b>\n\n"
            f"Reason: {reason}\n"
            f"Wallet: {wallet_address}\n\n"
            "IMMEDIATE ACTION REQUIRED:\n"
            "1. Do NOT use the compromised wallet\n"
            "2. Transfer remaining funds to cold wallet\n"
            "3. Revoke token approvals\n"
            "4. Rotate all API keys\n"
            "5. Kill switch activated",
            "CRITICAL",
        )

        incident["actions_taken"].append("Telegram alert sent")

        self.emergency_mode = True
        self.incident_log.append(incident)

        return incident

    async def handle_p1_position_stuck(
        self, position_id: str, reason: str, current_state: str
    ):
        """P1: Position stuck - requires intervention"""
        print(f"⚠️ P1 INCIDENT: Position Stuck - {position_id} - {reason}")

        incident = {
            "type": "P1_POSITION_STUCK",
            "timestamp": datetime.now().isoformat(),
            "position_id": position_id,
            "reason": reason,
            "current_state": current_state,
            "actions_taken": [],
        }

        await self.send_telegram_alert(
            f"⚠️ <b>P1 Alert: Position Stuck</b>\n\n"
            f"Position ID: {position_id}\n"
            f"Current State: {current_state}\n"
            f"Reason: {reason}\n\n"
            "Possible actions:\n"
            "- Use /exit {position_id} to force close\n"
            "- Check RPC connectivity\n"
            "- Review transaction history",
            "HIGH",
        )

        incident["actions_taken"].append("Telegram alert sent")
        self.incident_log.append(incident)

        return incident

    async def handle_circuit_breaker_open(self, rpc_name: str):
        """Handle circuit breaker opening for RPC"""
        print(f"⚠️ ALERT: Circuit breaker opened for {rpc_name}")

        await self.send_telegram_alert(
            f"⚠️ <b>RPC Alert: {rpc_name} Circuit Breaker OPEN</b>\n\n"
            f"Time: {datetime.now().isoformat()}\n\n"
            "System will automatically:\n"
            "- Route requests to remaining RPCs\n"
            "- Attempt recovery in 60s\n"
            f"Monitor at /status",
            "MEDIUM",
        )

    async def handle_high_slippage(
        self, position_id: str, slippage_bps: int, token: str
    ):
        """Handle high slippage warning"""
        print(f"⚠️ ALERT: High slippage on {position_id}: {slippage_bps} bps")

        await self.send_telegram_alert(
            f"⚠️ <b>Slippage Warning</b>\n\n"
            f"Position: {position_id}\n"
            f"Token: {token}\n"
            f"Slippage: {slippage_bps} bps ({slippage_bps / 100}%)\n\n"
            "System will retry with higher slippage...",
            "MEDIUM",
        )

    def get_incident_report(self) -> Dict[str, Any]:
        """Get incident report"""
        return {
            "total_incidents": len(self.incident_log),
            "p0_count": sum(1 for i in self.incident_log if i["type"].startswith("P0")),
            "p1_count": sum(1 for i in self.incident_log if i["type"].startswith("P1")),
            "emergency_mode": self.emergency_mode,
            "recent_incidents": self.incident_log[-10:],
        }

    def clear_emergency(self):
        """Clear emergency mode after resolution"""
        self.emergency_mode = False
        print("✅ Emergency mode cleared")
