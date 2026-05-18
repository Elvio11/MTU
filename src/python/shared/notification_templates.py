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
    """All notification templates for MTUS trading system in premium Infographic Dash style"""

    @staticmethod
    def token_qualified(token: Dict) -> str:
        """Token qualified - Infographic Dash style"""
        name = token.get("name", "N/A")
        symbol = token.get("symbol", "N/A")
        mint = token.get("mint", "N/A")
        
        mcap = token.get("market_cap") or token.get("market_cap_usd") or 0.0
        volume = token.get("volume_24h") or token.get("volume") or 0.0
        top10 = token.get("top10_holders_pct") or token.get("top10_holding", 0.0)
        rugcheck = token.get("rugcheck_score", "N/A")
        
        # Format numbers beautifully
        if isinstance(mcap, (int, float)):
            mcap_str = f"${mcap:,.2f}" if mcap > 0 else "N/A"
        else:
            mcap_str = str(mcap)
            
        if isinstance(volume, (int, float)):
            vol_str = f"${volume:,.2f}" if volume > 0 else "N/A"
        else:
            vol_str = str(volume)
            
        if isinstance(rugcheck, (int, float)):
            rugcheck_str = f"{rugcheck}"
        else:
            rugcheck_str = str(rugcheck)

        return f"""🟢 <b>TOKEN QUALIFIED</b>
━━━━━━━━━━━━━━━━━━━
<b>Token:</b> {name} ({symbol})
<b>Mint:</b>  <code>{mint}</code>

📊 <b>MARKET METRICS</b>
├─ <b>Market Cap:</b>  <code>{mcap_str}</code>
├─ <b>1h Volume:</b>   <code>{vol_str}</code>
├─ <b>Top 10 Holders:</b> <code>{top10:.2f}%</code>
└─ <b>RugCheck:</b>     <code>{rugcheck_str}</code>
━━━━━━━━━━━━━━━━━━━
<i>Ready for sniping...</i>"""

    @staticmethod
    def trade_opened(
        position_id: str,
        token: str,
        size_sol: float,
        entry_price: float,
        tp1_price: Optional[float] = None,
        tp2_price: Optional[float] = None,
        sl_price: Optional[float] = None,
    ) -> str:
        """Position opened - Infographic Dash style"""
        # Calculate default multipliers if not provided
        if not tp1_price:
            tp1_price = entry_price * 1.25
        if not tp2_price:
            tp2_price = entry_price * 1.50
        if not sl_price:
            sl_price = entry_price * 0.95

        tp1_pct = ((tp1_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
        tp2_pct = ((tp2_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
        sl_pct = ((sl_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0

        # Format signature of mint (token can be name or mint address)
        mint_str = token
        
        return f"""🚀 <b>POSITION OPENED</b>
━━━━━━━━━━━━━━━━━━━
<b>ID:</b>    <code>{position_id}</code>
<b>Mint:</b>  <code>{mint_str}</code>

💵 <b>TRADE DETAILS</b>
├─ <b>Size:</b>   <code>{size_sol:.4f} SOL</code>
├─ <b>Entry:</b>  <code>{entry_price:.6f} SOL</code>
├─ <b>TP1:</b>    <code>{tp1_price:.6f} SOL ({tp1_pct:+.1f}%)</code>
├─ <b>TP2:</b>    <code>{tp2_price:.6f} SOL ({tp2_pct:+.1f}%)</code>
└─ <b>SL:</b>     <code>{sl_price:.6f} SOL ({sl_pct:+.1f}%)</code>
━━━━━━━━━━━━━━━━━━━
<i>Monitoring real-time price feeds...</i>"""

    @staticmethod
    def tp1_hit(position_id: str, token: str, pnl_sol: float) -> str:
        """Take profit 1 hit - Infographic Dash style"""
        return f"""🎯 <b>TAKE PROFIT 1 HIT</b>
━━━━━━━━━━━━━━━━━━━
<b>ID:</b>    <code>{position_id}</code>
<b>Token:</b> <code>{token}</code>

📈 <b>PERFORMANCE</b>
├─ <b>PnL:</b>    <code>{pnl_sol:+.4f} SOL</code>
└─ <b>Action:</b> <code>50% position sold, 50% running</code>
━━━━━━━━━━━━━━━━━━━
<i>Trailing stop active...</i>"""

    @staticmethod
    def tp2_hit(position_id: str, token: str, pnl_sol: float) -> str:
        """Take profit 2 hit - Infographic Dash style"""
        return f"""🏆 <b>TAKE PROFIT 2 HIT (EXIT)</b>
━━━━━━━━━━━━━━━━━━━
<b>ID:</b>    <code>{position_id}</code>
<b>Token:</b> <code>{token}</code>

📈 <b>PERFORMANCE</b>
├─ <b>PnL:</b>    <code>{pnl_sol:+.4f} SOL</code>
└─ <b>Action:</b> <code>100% position fully closed</code>
━━━━━━━━━━━━━━━━━━━
<i>Trade complete!</i>"""

    @staticmethod
    def stop_loss(position_id: str, token: str, pnl_sol: float) -> str:
        """Stop loss hit - Infographic Dash style"""
        return f"""🛑 <b>STOP LOSS TRIGGERED</b>
━━━━━━━━━━━━━━━━━━━
<b>ID:</b>    <code>{position_id}</code>
<b>Token:</b> <code>{token}</code>

📈 <b>PERFORMANCE</b>
├─ <b>PnL:</b>    <code>{pnl_sol:+.4f} SOL</code>
└─ <b>Action:</b> <code>100% position fully closed</code>
━━━━━━━━━━━━━━━━━━━
<i>Trade complete!</i>"""

    @staticmethod
    def daily_summary(
        total_trades: int, winning_trades: int, total_pnl: float, env: str = "PAPER"
    ) -> str:
        """Daily trading summary"""
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        pnl_emoji = "📈" if total_pnl >= 0 else "📉"
        return f"""📊 <b>DAILY TRADING SUMMARY</b>
━━━━━━━━━━━━━━━━━━━
<b>Environment:</b> <code>{env}</code>

📈 <b>METRICS</b>
├─ <b>Total Trades:</b> <code>{total_trades}</code>
├─ <b>Win Rate:</b>     <code>{win_rate:.1f}% ({winning_trades} wins)</code>
└─ <b>Total PnL:</b>    <code>{total_pnl:+.4f} SOL {pnl_emoji}</code>
━━━━━━━━━━━━━━━━━━━
<i>Data from the last 24h</i>"""

    @staticmethod
    def system_alert(level: str, message: str) -> str:
        """General system alert"""
        emoji = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌", "CRITICAL": "🚨"}.get(
            level, "📢"
        )
        return f"""{emoji} <b>SYSTEM ALERT: {level}</b>
━━━━━━━━━━━━━━━━━━━
{message}
━━━━━━━━━━━━━━━━━━━
<i>Monitor active status</i>"""

    @staticmethod
    def trade_failed(
        mint: str,
        reason: str,
        token_details: Optional[Dict] = None
    ) -> str:
        """Trade failed - Infographic Dash style"""
        if token_details:
            name = token_details.get("name", "N/A")
            symbol = token_details.get("symbol", "N/A")
            
            mcap = token_details.get("market_cap") or token_details.get("market_cap_usd") or 0.0
            volume = token_details.get("volume_24h") or token_details.get("volume") or 0.0
            top10 = token_details.get("top10_holders_pct") or token_details.get("top10_holding", 0.0)
            rugcheck = token_details.get("rugcheck_score", "N/A")
            
            # Format numbers beautifully
            if isinstance(mcap, (int, float)):
                mcap_str = f"${mcap:,.2f}" if mcap > 0 else "N/A"
            else:
                mcap_str = str(mcap)
                
            if isinstance(volume, (int, float)):
                vol_str = f"${volume:,.2f}" if volume > 0 else "N/A"
            else:
                vol_str = str(volume)
                
            if isinstance(rugcheck, (int, float)):
                rugcheck_str = f"{rugcheck}"
            else:
                rugcheck_str = str(rugcheck)
                
            if isinstance(top10, (int, float)):
                top10_str = f"{top10:.2f}%"
            else:
                top10_str = str(top10)

            return f"""❌ <b>TRADE SKIPPED/FAILED</b>
━━━━━━━━━━━━━━━━━━━
<b>Mint:</b>   <code>{mint}</code>
<b>Reason:</b> <code>{reason}</code>

📊 <b>MARKET METRICS</b>
├─ <b>Token:</b>       <code>{name} ({symbol})</code>
├─ <b>Market Cap:</b>  <code>{mcap_str}</code>
├─ <b>1h Volume:</b>   <code>{vol_str}</code>
├─ <b>Top 10 Holders:</b> <code>{top10_str}</code>
└─ <b>RugCheck:</b>     <code>{rugcheck_str}</code>
━━━━━━━━━━━━━━━━━━━
<i>Waiting for the next setup...</i>"""
        else:
            return f"""❌ <b>TRADE SKIPPED/FAILED</b>
━━━━━━━━━━━━━━━━━━━
<b>Mint:</b>   <code>{mint}</code>
<b>Reason:</b> <code>{reason}</code>
━━━━━━━━━━━━━━━━━━━
<i>Waiting for the next setup...</i>"""

    @staticmethod
    def agent_status(agent_id: str, status: str, details: str = "") -> str:
        """Agent health status"""
        emoji = "✅" if status == "healthy" else "❌"
        return f"""🤖 <b>AGENT STATUS SUMMARY</b>
━━━━━━━━━━━━━━━━━━━
├─ <b>Agent:</b>   <code>{agent_id}</code>
├─ <b>Status:</b>  <code>{status.upper()} {emoji}</code>
└─ <b>Details:</b> <code>{details if details else "No issues detected"}</code>
━━━━━━━━━━━━━━━━━━━
<i>Self-healing monitor active</i>"""

    @staticmethod
    def price_alert(token: str, price: float, change_24h: float) -> str:
        """Price movement alert"""
        emoji = "🚀" if change_24h > 10 else "📉" if change_24h < -10 else "➡️"
        return f"""{emoji} <b>PRICE MOVEMENT ALERT</b>
━━━━━━━━━━━━━━━━━━━
├─ <b>Token:</b>    <code>{token}</code>
├─ <b>Price:</b>    <code>${price:.6f}</code>
└─ <b>24h Change:</b><code>{change_24h:+.1f}%</code>
━━━━━━━━━━━━━━━━━━━
<i>Volatility alert threshold triggered</i>"""

    @staticmethod
    def position_closed(
        position_id: str, token: str, pnl_sol: float, reason: str, env: str = "PAPER"
    ) -> str:
        """Position closed - Infographic Dash style"""
        emoji = "🏆" if pnl_sol > 0 else "🛑" if pnl_sol < 0 else "➖"
        title = "POSITION CLOSED"
        
        return f"""{emoji} <b>{title} [{env}]</b>
━━━━━━━━━━━━━━━━━━━
<b>ID:</b>    <code>{position_id}</code>
<b>Token:</b> <code>{token}</code>

📈 <b>PERFORMANCE</b>
├─ <b>PnL:</b>    <code>{pnl_sol:+.4f} SOL</code>
└─ <b>Reason:</b> <code>{reason}</code>
━━━━━━━━━━━━━━━━━━━
<i>Trade complete!</i>"""
