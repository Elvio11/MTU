"""Telegram notification templates for MTUS"""

import os
from typing import Dict, Optional
from datetime import datetime

MTUS_ENVIRONMENT = os.getenv("MTUS_ENVIRONMENT", "paper").lower()


def add_environment_tag(message: str) -> str:
    """Add [PAPER] or [PROD] tag to notification per Section 8.4"""
    if MTUS_ENVIRONMENT == "paper":
        return f"[PAPER] {message}"
    return message


class NotificationTemplates:
    """All notification templates for MTUS trading system"""

    @staticmethod
    def token_qualified(token: Dict) -> str:
        """Token passed all gates - ready for trading"""
        return f"""✅ <b>Token Qualified</b>

Name: {token.get("name", "N/A")}
Symbol: {token.get("symbol", "N/A")}
Mint: {token.get("mint", "N/A")[:8]}...
MCap: ${token.get("market_cap", 0):.2f}
RugCheck: {token.get("rugcheck_score", "N/A")}

<i>Ready for trading</i>"""

    @staticmethod
    def trade_opened(
        position_id: str, token: str, size_sol: float, entry_price: float
    ) -> str:
        """Position opened"""
        return f"""📈 <b>Position Opened</b>

ID: {position_id}
Token: {token}
Size: {size_sol:.3f} SOL
Entry: ${entry_price:.6f}

<i>Monitoring TP/SL...</i>"""

    @staticmethod
    def tp1_hit(position_id: str, token: str, pnl_sol: float) -> str:
        """Take profit 1 hit - 50% sold"""
        return f"""🎯 <b>TP1 Hit!</b>

Position: {position_id}
Token: {token}
PnL: {pnl_sol:+.3f} SOL

<i>50% sold, 50% remaining</i>"""

    @staticmethod
    def tp2_hit(position_id: str, token: str, pnl_sol: float) -> str:
        """Take profit 2 hit - fully exited"""
        return f"""🎯 <b>TP2 Hit!</b>

Position: {position_id}
Token: {token}
Total PnL: {pnl_sol:+.3f} SOL

<i>Fully exited</i>"""

    @staticmethod
    def stop_loss(position_id: str, token: str, pnl_sol: float) -> str:
        """Stop loss hit"""
        return f"""🛑 <b>Stop Loss</b>

Position: {position_id}
Token: {token}
PnL: {pnl_sol:.3f} SOL

<i>Position closed</i>"""

    @staticmethod
    def daily_summary(
        total_trades: int, winning_trades: int, total_pnl: float, env: str = "PAPER"
    ) -> str:
        """Daily trading summary"""
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        return f"""📊 <b>Daily Summary [{env}]</b>

Trades: {total_trades}
Wins: {winning_trades} ({win_rate:.1f}%)
Total PnL: {total_pnl:+.4f} SOL

<i>Data from last 24h</i>"""

    @staticmethod
    def system_alert(level: str, message: str) -> str:
        """General system alert"""
        emoji = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌", "CRITICAL": "🚨"}.get(
            level, "📢"
        )
        return f"""{emoji} <b>System Alert: {level}</b>

{message}"""

    @staticmethod
    def trade_failed(
        mint: str,
        reason: str,
        token_details: Optional[Dict] = None
    ) -> str:
        """Trade failed notification with coin details"""
        if token_details:
            name = token_details.get("name", "N/A")
            symbol = token_details.get("symbol", "N/A")
            mcap = token_details.get("market_cap") or token_details.get("market_cap_usd") or 0.0
            volume = token_details.get("volume_24h") or token_details.get("volume") or 0.0
            
            # Format numbers beautifully
            if isinstance(mcap, (int, float)):
                mcap_str = f"${mcap:,.2f}" if mcap > 0 else "N/A"
            else:
                mcap_str = str(mcap)
                
            if isinstance(volume, (int, float)):
                vol_str = f"${volume:,.2f}" if volume > 0 else "N/A"
            else:
                vol_str = str(volume)
                
            return f"""❌ <b>Trade Failed</b>

<b>Token:</b> {name} ({symbol})
<b>Mint:</b> <code>{mint}</code>
<b>Reason:</b> {reason}

<b>Market Cap:</b> {mcap_str}
<b>24h Volume:</b> {vol_str}

<i>Skipped or execution failed</i>"""
        else:
            return f"""❌ <b>Trade Failed</b>

<b>Mint:</b> <code>{mint}</code>
<b>Reason:</b> {reason}

<i>Execution failed</i>"""

    @staticmethod
    def agent_status(agent_id: str, status: str, details: str = "") -> str:
        """Agent health status"""
        emoji = "✅" if status == "healthy" else "❌"
        return f"""🤖 <b>Agent Status</b>

{emoji} {agent_id}: {status}
{details}"""

    @staticmethod
    def price_alert(token: str, price: float, change_24h: float) -> str:
        """Price movement alert"""
        emoji = "🚀" if change_24h > 10 else "📉" if change_24h < -10 else "➡️"
        return f"""{emoji} <b>Price Alert</b>

Token: {token}
Price: ${price:.6f}
24h: {change_24h:+.1f}%"""

    @staticmethod
    def position_closed(
        position_id: str, token: str, pnl_sol: float, reason: str, env: str = "PAPER"
    ) -> str:
        """Position closed notification"""
        emoji = "✅" if pnl_sol > 0 else "❌" if pnl_sol < 0 else "➖"
        return f"""{emoji} <b>Position Closed [{env}]</b>

ID: {position_id}
Token: {token}
PnL: {pnl_sol:+.4f} SOL
Reason: {reason}"""
