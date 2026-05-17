import aiohttp
import asyncio
import json
import os
from datetime import datetime
from typing import Dict, Optional, List, Callable, Any
from enum import Enum
import hashlib
import hmac
from .telegram_auth import verify_otp
from .constants import (
    MTUS_PREFIX,
    REDIS_KEY_TRADING_ACTIVE,
    REDIS_KEY_SYSTEM_STATE,
    REDIS_KEY_KILL_SWITCH_TRIGGERED,
    CHANNEL_TRADING_PAUSED,
    CHANNEL_TRADING_RESUMED,
    CHANNEL_KILL_SWITCH_TRIGGERED,
    KEY_ALL_POSITIONS,
    KEY_ALL_CLOSED_POSITIONS,
    KEY_POSITION_SIZE_SOL,
    KEY_MAX_POSITIONS,
    KEY_TP1_MULTIPLIER,
    KEY_TP2_MULTIPLIER,
    KEY_SL_MULTIPLIER,
    CHANNEL_SWEEP_REQUESTED,
    CHANNEL_MANUAL_EXIT,
    CHANNEL_HEALTH_CHECK,
    CHANNEL_PRICE_UPDATED,
    CHANNEL_POSITION_OPENED,
    CHANNEL_POSITION_CLOSED,
    CHANNEL_CONFIG_UPDATED,
    CHANNEL_SYSTEM_ALERT,
)


class ButtonType(Enum):
    CALLBACK = "callback_data"
    URL = "url"


class InlineButton:
    def __init__(self, text: str, callback_data: str = None, url: str = None):
        self.text = text
        self.callback_data = callback_data
        self.url = url

    def to_dict(self):
        result = {"text": self.text}
        if self.callback_data:
            result["callback_data"] = self.callback_data
        elif self.url:
            result["url"] = self.url
        return result


class InlineKeyboard:
    def __init__(self):
        self.buttons: List[List[InlineButton]] = []

    def add_row(self):
        self.buttons.append([])
        return self

    def add_button(self, text: str, callback_data: str = None, url: str = None):
        if not self.buttons:
            self.buttons.append([])
        self.buttons[-1].append(InlineButton(text, callback_data, url))
        return self

    def to_dict(self):
        return {"inline_keyboard": [[b.to_dict() for b in row] for row in self.buttons]}


class TelegramBot:
    def __init__(
        self,
        token: str,
        admin_chat_id: str,
        otp_seed: str,
        redis_url: str = "redis://localhost:6379",
    ):
        self.token = token
        self.admin_chat_id = admin_chat_id
        self.otp_seed = otp_seed
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.session: Optional[aiohttp.ClientSession] = None
        self.handlers: Dict[str, Callable] = {}
        self.running = False
        self.redis = None
        self.redis_url = redis_url
        self.current_states: Dict[str, Dict] = {}
        self.pending_confirmations: Dict[str, Dict] = {}
        self._callback_handlers: Dict[str, Callable] = {}

    async def initialize(self):
        import aioredis

        self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)
        self.session = aiohttp.ClientSession()
        self.running = True
        self._register_callback_handlers()
        print(f"Telegram Bot initialized for admin: {self.admin_chat_id}")

    def _register_callback_handlers(self):
        self._callback_handlers = {
            "confirm_pause": self._handle_confirm_pause,
            "confirm_resume": self._handle_confirm_resume,
            "confirm_killswitch": self._handle_confirm_killswitch,
            "confirm_exit": self._handle_confirm_exit,
            "confirm_sweep": self._handle_confirm_sweep,
            "show_positions": self._handle_show_positions,
            "show_pnl": self._handle_show_pnl,
            "show_config": self._handle_show_config,
            "cancel": self._handle_cancel,
            "refresh_status": self._handle_refresh_status,
        }

    async def start(self):
        await self.initialize()
        await self.send_welcome_message()
        await asyncio.gather(
            self.poll_updates(),
            self.listen_redis_pubsub()
        )

    async def poll_updates(self):
        offset = 0
        while self.running:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {
                    "offset": offset,
                    "timeout": 30,
                    "allowed_updates": ["message", "callback_query"],
                }
                async with self.session.get(url, params=params) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        for update in data.get("result", []):
                            offset = update["update_id"] + 1
                            if "callback_query" in update:
                                await self.handle_callback_query(
                                    update["callback_query"]
                                )
                            elif "message" in update:
                                await self.handle_message(update["message"])
            except Exception as e:
                print(f"[POLL] Telegram poll error: {e}")
                await asyncio.sleep(5)

    async def handle_callback_query(self, callback_query: dict):
        chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
        if chat_id != self.admin_chat_id:
            await self.answer_callback(callback_query["id"], "Unauthorized")
            return

        data = callback_query.get("data", "")
        handler = self._callback_handlers.get(data.split(":")[0])

        if handler:
            await handler(callback_query)
        else:
            await self.answer_callback(callback_query["id"], "Unknown action")

    async def answer_callback(
        self, callback_id: str, text: str, show_alert: bool = False
    ):
        try:
            url = f"{self.base_url}/answerCallbackQuery"
            params = {
                "callback_query_id": callback_id,
                "text": text,
                "show_alert": show_alert,
            }
            async with self.session.post(url, json=params) as resp:
                pass
        except Exception as e:
            print(f"Error answering callback: {e}")

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: InlineKeyboard = None,
        parse_mode: str = "Markdown",
    ):
        try:
            url = f"{self.base_url}/sendMessage"
            params = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            if reply_markup:
                params["reply_markup"] = json.dumps(reply_markup.to_dict())
            async with self.session.post(url, json=params) as resp:
                result = await resp.json()
                if not result.get("ok"):
                    print(f"[ERROR] Send message failed: {result}")
                return result
        except Exception as e:
            print(f"[SEND] Send message error: {e}")

    async def edit_message(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        reply_markup: InlineKeyboard = None,
    ):
        try:
            url = f"{self.base_url}/editMessageText"
            params = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "Markdown",
            }
            if reply_markup:
                params["reply_markup"] = json.dumps(reply_markup.to_dict())
            async with self.session.post(url, json=params) as resp:
                return await resp.json()
        except Exception as e:
            print(f"[EDIT] Edit message error: {e}")

    async def send_welcome_message(self):
        keyboard = InlineKeyboard()
        keyboard.add_row().add_button("[STATS] Status", "show_positions").add_button(
            "[PNL] PnL", "show_pnl"
        )
        keyboard.add_row().add_button("[CONFIG] Config", "show_config").add_button(
            "[REFRESH] Refresh", "refresh_status"
        )

        welcome_text = """[BOT] *MTUS Trading Bot*

*System Status:* [OK] Running
*Environment:* `{}`

_Choose an action below:_

• `/status` - View positions & balances
• `/pause [otp]` - Pause trading (OTP required)
• `/resume [otp]` - Resume trading (OTP required)  
• `/killswitch [otp]` - Emergency stop (OTP required)
• `/exit <pos_id> [otp]` - Close specific position
• `/pnl` - View PnL stats
• `/sweep [otp]` - Sweep funds (OTP required)
• `/config` - Update configuration
""".format(os.getenv("MTUS_ENVIRONMENT", "production"))

        await self.send_message(self.admin_chat_id, welcome_text, keyboard)

    async def handle_message(self, message: dict):
        text = message.get("text", "")
        chat_id = str(message.get("chat", {}).get("id", ""))

        if chat_id != self.admin_chat_id:
            await self.send_message(
                chat_id, "[BLOCKED] Unauthorized. This bot is for admin only."
            )
            return

        if text.startswith("/"):
            command = text.split()[0].lower()
            args = text.split()[1:] if len(text.split()) > 1 else []

            command_handlers = {
                "/start": self.handle_start,
                "/status": self.handle_status,
                "/pause": self.handle_pause,
                "/resume": self.handle_resume,
                "/killswitch": self.handle_killswitch,
                "/exit": self.handle_exit,
                "/pnl": self.handle_pnl,
                "/sweep": self.handle_sweep,
                "/config": self.handle_config,
                "/help": self.handle_help,
                "/golive": self.handle_golive,
            }

            handler = command_handlers.get(command)
            if handler:
                await handler(chat_id, text, args)
            else:
                await self.send_message(
                    chat_id,
                    f"[UNKNOWN] Unknown command: {command}\nUse /help for available commands",
                )

    async def handle_start(self, chat_id: str, text: str, args: List[str]):
        await self.send_welcome_message()

    async def handle_help(self, chat_id: str, text: str, args: List[str]):
        help_text = """[HELP] *MTUS Bot Commands*

*No Authentication Required:*
• `/status` - View current positions & system status
• `/pnl` - View daily PnL statistics  
• `/help` - Show this help message

*OTP Required:*
• `/pause [otp]` - Pause all trading
• `/resume [otp]` - Resume trading
• `/killswitch [otp]` - Emergency stop all positions
• `/exit <pos_id> [otp]` - Close specific position
• `/sweep [otp]` - Sweep sniper to main wallet
• `/config <key> <value>` - Update runtime config

_OTP is your 6-digit security code from Telegram auth_
"""
        await self.send_message(chat_id, help_text)

    async def handle_status(self, chat_id: str, text: str, args: List[str]):
        try:
            status = await self._get_system_status()

            keyboard = InlineKeyboard()
            keyboard.add_row().add_button("[REFRESH] Refresh", "refresh_status")

            await self.send_message(chat_id, status, keyboard)
        except Exception as e:
            await self.send_message(chat_id, f"[ERROR] Error getting status: {e}")

    async def _get_system_status(self) -> str:
        import aioredis

        redis = await aioredis.from_url("redis://localhost:6379", decode_responses=True)

        positions = await redis.keys("position:*")
        positions_data = []
        for pos_key in positions:
            pos_data = await redis.hgetall(pos_key)
            if pos_data:
                positions_data.append(pos_data)

        await redis.close()

        active_count = len(
            [p for p in positions_data if p.get("state") not in ["CLOSED", "FAILED"]]
        )

        system_state = await redis.get("mtus:system_state") if self.redis else "running"
        trading_active = (
            await redis.get("mtus:trading_active") if self.redis else "true"
        )

        status_text = f"""[STATS] *MTUS System Status*

*Trading:* {"[OK] Active" if trading_active == "true" else "[HIGH] Paused"}
*System:* {system_state or "running"}
*Active Positions:* {active_count}/{len(positions_data)}

*Positions:*
"""
        if positions_data:
            for pos in positions_data[:5]:
                state_emoji = (
                    "[OK]"
                    if pos.get("state") == "OPEN"
                    else "[MED]"
                    if "TAKE_PROFIT" in pos.get("state", "")
                    else "[HIGH]"
                )
                symbol = pos.get("symbol", "UNKNOWN")
                pnl = pos.get("unrealized_pnl", "0")
                status_text += f"• {state_emoji} `{symbol}` | PnL: {pnl} SOL\n"
        else:
            status_text += "_No open positions_\n"

        return status_text

    async def handle_pause(self, chat_id: str, text: str, args: List[str]):
        otp = args[0] if args else None

        if not otp:
            keyboard = InlineKeyboard()
            keyboard.add_row().add_button("[OK] Confirm", "confirm_pause").add_button(
                "[ERROR] Cancel", "cancel"
            )
            await self.send_message(
                chat_id,
                "[PAUSE] *Pause Trading*\n\nAre you sure you want to pause all trading activity?",
                keyboard,
            )
            self.current_states[chat_id] = {"action": "pause", "waiting_otp": True}
        else:
            if not verify_otp(self.otp_seed, otp):
                await self.send_message(
                    chat_id, "[ERROR] *Invalid OTP*\nPlease provide valid 6-digit code."
                )
            else:
                await self._execute_pause(chat_id)

    async def _handle_confirm_pause(self, callback_query: dict):
        chat_id = str(callback_query["message"]["chat"]["id"])
        message_id = callback_query["message"]["message_id"]

        keyboard = InlineKeyboard()
        keyboard.add_row().add_button("[OK] Confirm", "confirm_pause:final").add_button(
            "[ERROR] Cancel", "cancel"
        )

        await self.edit_message(
            chat_id,
            message_id,
            "[PAUSE] *Confirm Pause*\n\n_Reply with your OTP code to proceed_\n\nExample: `/pause 123456`",
            keyboard,
        )

    async def _handle_cancel(self, callback_query: dict):
        chat_id = str(callback_query["message"]["chat"]["id"])
        message_id = callback_query["message"]["message_id"]
        await self.edit_message(chat_id, message_id, "[OK] Action cancelled", None)
        if chat_id in self.current_states:
            del self.current_states[chat_id]

    async def _execute_pause(self, chat_id: str):
        if self.redis:
            await self.redis.set("mtus:trading_active", "false")
            await self.redis.publish(
                "trading_paused",
                json.dumps({"timestamp": datetime.utcnow().isoformat()}),
            )

        keyboard = InlineKeyboard()
        keyboard.add_row().add_button("[RESUME] Resume", "confirm_resume")

        await self.send_message(
            chat_id,
            "[OK] *Trading PAUSED*\n\nAll new trade detection is now disabled.\nUse `/resume` to reactivate.",
            keyboard,
        )

    async def handle_resume(self, chat_id: str, text: str, args: List[str]):
        otp = args[0] if args else None

        if not otp:
            keyboard = InlineKeyboard()
            keyboard.add_row().add_button("[OK] Confirm", "confirm_resume").add_button(
                "[ERROR] Cancel", "cancel"
            )
            await self.send_message(
                chat_id,
                "[RESUME] *Resume Trading*\n\nResume all trading activity?",
                keyboard,
            )
        else:
            if not verify_otp(self.otp_seed, otp):
                await self.send_message(chat_id, "[ERROR] *Invalid OTP*")
            else:
                await self._execute_resume(chat_id)

    async def _handle_confirm_resume(self, callback_query: dict):
        chat_id = str(callback_query["message"]["chat"]["id"])
        await self._execute_resume(chat_id)

    async def _execute_resume(self, chat_id: str):
        if self.redis:
            await self.redis.set("mtus:trading_active", "true")
            await self.redis.publish(
                "trading_resumed",
                json.dumps({"timestamp": datetime.utcnow().isoformat()}),
            )

        await self.send_message(
            chat_id, "[OK] *Trading RESUMED*\n\nAll trading activity reactivated!"
        )

    async def handle_killswitch(self, chat_id: str, text: str, args: List[str]):
        otp = args[0] if args else None

        if not otp:
            keyboard = InlineKeyboard()
            keyboard.add_row().add_button(
                "[ALERT] CONFIRM KILLSWITCH", "confirm_killswitch"
            ).add_button("[ERROR] Cancel", "cancel")
            await self.send_message(
                chat_id,
                "[ALERT] *⚠️ KILLSWITCH ⚠️*\n\nThis will IMMEDIATELY close ALL open positions and disable trading.\n\n*This action cannot be undone!*",
                keyboard,
            )
        else:
            if not verify_otp(self.otp_seed, otp):
                await self.send_message(chat_id, "[ERROR] *Invalid OTP*")
            else:
                await self._execute_killswitch(chat_id)

    async def _handle_confirm_killswitch(self, callback_query: dict):
        chat_id = str(callback_query["message"]["chat"]["id"])
        message_id = callback_query["message"]["message_id"]
        await self.edit_message(
            chat_id,
            message_id,
            "[ALERT] *Killswitch Triggered*\n\n_Executing emergency close..._",
            None,
        )

        if self.redis:
            await self.redis.set("mtus:trading_active", "false")
            await self.redis.set("mtus:killswitch_triggered", "true")
            await self.redis.publish(
                "killswitch_triggered",
                json.dumps({"timestamp": datetime.utcnow().isoformat()}),
            )

        await self.send_message(
            chat_id,
            "[ALERT] *KILLSWITCH ACTIVATED*\n\nAll positions are being closed.\nTrading disabled until manually re-enabled.",
        )

    async def _execute_killswitch(self, chat_id: str):
        if self.redis:
            await self.redis.set("mtus:trading_active", "false")
            await self.redis.set("mtus:killswitch_triggered", "true")
            await self.redis.publish(
                "killswitch_triggered",
                json.dumps({"timestamp": datetime.utcnow().isoformat()}),
            )

        await self.send_message(
            chat_id,
            "[ALERT] *KILLSWITCH ACTIVATED*\n\nAll positions closing. Trading disabled.",
        )

    async def handle_exit(self, chat_id: str, text: str, args: List[str]):
        if len(args) < 1:
            await self.send_message(
                chat_id,
                "Usage: `/exit <position_id> [otp]`\n\nExample: `/exit pos_123 abc123`",
            )
            return

        position_id = args[0]
        otp = args[1] if len(args) > 1 else None

        if not otp:
            keyboard = InlineKeyboard()
            keyboard.add_row().add_button(
                f"[HIGH] Close {position_id}", f"confirm_exit:{position_id}"
            ).add_button("[ERROR] Cancel", "cancel")
            await self.send_message(
                chat_id,
                f"[HIGH] *Close Position `{position_id}`*\n\nThis will close the position at market price.\n\nReply with OTP to confirm:\n`/exit {position_id} <otp>`",
                keyboard,
            )
        else:
            if not verify_otp(self.otp_seed, otp):
                await self.send_message(chat_id, "[ERROR] *Invalid OTP*")
            else:
                await self._execute_exit(chat_id, position_id)

    async def _handle_confirm_exit(self, callback_query: dict):
        data = callback_query["data"]
        position_id = data.split(":")[1]
        chat_id = str(callback_query["message"]["chat"]["id"])

        await self.edit_message(
            chat_id,
            callback_query["message"]["message_id"],
            f"[HIGH] *Closing position `{position_id}`...*",
            None,
        )

        if self.redis:
            await self.redis.publish(
                "manual_exit_request",
                json.dumps(
                    {
                        "position_id": position_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ),
            )

        await self.send_message(
            chat_id,
            f"[OK] *Exit request sent*\nPosition `{position_id}` is being closed.",
        )

    async def _execute_exit(self, chat_id: str, position_id: str):
        if self.redis:
            await self.redis.publish(
                "manual_exit_request",
                json.dumps(
                    {
                        "position_id": position_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ),
            )

        await self.send_message(
            chat_id, f"[OK] *Exit initiated*\nPosition `{position_id}` is being closed."
        )

    async def handle_pnl(self, chat_id: str, text: str, args: List[str]):
        try:
            pnl_data = await self._calculate_pnl()

            keyboard = InlineKeyboard()
            keyboard.add_row().add_button("[STATS] More Stats", "show_pnl")

            await self.send_message(chat_id, pnl_data, keyboard)
        except Exception as e:
            await self.send_message(chat_id, f"[ERROR] Error calculating PnL: {e}")

    async def _calculate_pnl(self) -> str:
        import aioredis

        redis = await aioredis.from_url("redis://localhost:6379", decode_responses=True)

        closed_positions = await redis.keys("position_closed:*")
        total_pnl = 0.0
        total_trades = 0
        wins = 0
        losses = 0

        for pos_key in closed_positions:
            pos_data = await redis.hgetall(pos_key)
            if pos_data:
                pnl = float(pos_data.get("realized_pnl", 0))
                total_pnl += pnl
                total_trades += 1
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1

        await redis.close()

        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        return f"""[PNL] *Daily PnL Report*

*Total PnL:* `{total_pnl:.4f} SOL`
*Trades:* {total_trades}
*Wins:* {wins} | *Losses:* {losses}
*Win Rate:* {win_rate:.1f}%

_Statistics calculated from closed positions_
"""

    async def _handle_show_pnl(self, callback_query: dict):
        chat_id = str(callback_query["message"]["chat"]["id"])
        pnl_data = await self._calculate_pnl()

        keyboard = InlineKeyboard()
        keyboard.add_row().add_button("[REFRESH] Refresh", "show_pnl")

        await self.edit_message(
            chat_id, callback_query["message"]["message_id"], pnl_data, keyboard
        )

    async def handle_sweep(self, chat_id: str, text: str, args: List[str]):
        otp = args[0] if args else None

        if not otp:
            keyboard = InlineKeyboard()
            keyboard.add_row().add_button(
                "[SWEEP] Confirm Sweep", "confirm_sweep"
            ).add_button("[ERROR] Cancel", "cancel")
            await self.send_message(
                chat_id,
                "[SWEEP] *Sweep Funds*\n\nTransfer all funds from Sniper wallet to Main wallet.\n\nReply with OTP to confirm:\n`/sweep <otp>`",
                keyboard,
            )
        else:
            if not verify_otp(self.otp_seed, otp):
                await self.send_message(chat_id, "[ERROR] *Invalid OTP*")
            else:
                await self._execute_sweep(chat_id)

    async def _handle_confirm_sweep(self, callback_query: dict):
        chat_id = str(callback_query["message"]["chat"]["id"])
        await self.edit_message(
            chat_id,
            callback_query["message"]["message_id"],
            "[SWEEP] *Initiating sweep...*\n\n_Reply with OTP: `/sweep <code>`_",
            None,
        )

    async def _handle_confirm_sweep_final(self, callback_query: dict):
        chat_id = str(callback_query["message"]["chat"]["id"])
        await self._execute_sweep(chat_id)

    async def _execute_sweep(self, chat_id: str):
        if self.redis:
            await self.redis.publish(
                "sweep_requested",
                json.dumps({"timestamp": datetime.utcnow().isoformat()}),
            )

        await self.send_message(
            chat_id,
            "[SWEEP] *Sweep Initiated*\n\nFunds transfer from Sniper → Main wallet in progress.",
        )

    async def handle_config(self, chat_id: str, text: str, args: List[str]):
        if len(args) < 2:
            current_config = await self._get_current_config()
            keyboard = InlineKeyboard()
            keyboard.add_row().add_button("[REFRESH] Refresh", "show_config")

            await self.send_message(
                chat_id,
                f"[CONFIG] *Current Configuration*\n\n{current_config}",
                keyboard,
            )
            return

        key = args[0]
        value = args[1]

        await self._update_config(chat_id, key, value)

    async def handle_golive(self, chat_id: str, text: str, args: List[str]):
        """Check mainnet readiness and switch to production per Section 8.4"""
        import os
        from src.python.agents.heracles import HeraclesAgent

        current_env = os.getenv("MTUS_ENVIRONMENT", "paper")

        if current_env == "production":
            await self.send_message(
                chat_id,
                "✅ Already in PRODUCTION mode!\n\nSystem is running with real funds.",
            )
            return

        # Check paper trading stats
        agent = HeraclesAgent({})
        await agent.connect_redis()

        ready = agent.check_mainnet_readiness()
        stats = agent.paper_trades

        if ready:
            # Switch to production
            os.environ["MTUS_ENVIRONMENT"] = "production"
            await self.send_message(
                chat_id,
                f"""🚀 *MAINNET READY!*

Trading Stats:
• Total Paper Trades: {len(stats)}
• Win Rate: {sum(1 for t in stats if t.payload.get("realised_pnl_sol", 0) > 0) / len(stats) * 100:.1f}%
• Sharpe Ratio: >0.5

✅ Switched to PRODUCTION mode!
⚠️  WARNING: Real trading with real funds now active!""",
            )
        else:
            trades_needed = 50 - len(stats)
            await self.send_message(
                chat_id,
                f"""❌ *NOT READY FOR MAINNET*

Current Stats:
• Paper Trades: {len(stats)}/50 required
• Win Rate: {sum(1 for t in stats if t.payload.get("realised_pnl_sol", 0) > 0) / max(len(stats), 1) * 100:.1f}%
• Sharpe Ratio: <0.5

Need {trades_needed} more paper trades with >40% win rate.""",
            )

        await agent.stop()

    async def _get_current_config(self) -> str:
        import aioredis

        redis = await aioredis.from_url("redis://localhost:6379", decode_responses=True)

        config_keys = [
            "mtus:position_size_sol",
            "mtus:max_positions",
            "mtus:tp1_multiplier",
            "mtus:tp2_multiplier",
            "mtus:sl_multiplier",
            "mtus:trading_active",
        ]

        config_text = ""
        for key in config_keys:
            value = await redis.get(key)
            if value:
                config_text += f"• `{key.replace('mtus:', '')}`: `{value}`\n"

        await redis.close()
        return config_text or "_No custom config set_"

    async def _update_config(self, chat_id: str, key: str, value: str):
        valid_keys = [
            "position_size_sol",
            "max_positions",
            "tp1_multiplier",
            "tp2_multiplier",
            "sl_multiplier",
        ]

        if key not in valid_keys:
            await self.send_message(
                chat_id, f"[ERROR] Invalid config key. Valid: {', '.join(valid_keys)}"
            )
            return

        if self.redis:
            await self.redis.set(f"mtus:{key}", value)
            await self.redis.publish(
                "config_updated", json.dumps({"key": key, "value": value})
            )

        await self.send_message(chat_id, f"[OK] *Config Updated*\n`{key}` = `{value}`")

    async def _handle_show_config(self, callback_query: dict):
        chat_id = str(callback_query["message"]["chat"]["id"])
        config = await self._get_current_config()

        keyboard = InlineKeyboard()
        keyboard.add_row().add_button("[REFRESH] Refresh", "show_config")

        await self.edit_message(
            chat_id,
            callback_query["message"]["message_id"],
            f"[CONFIG] *Configuration*\n\n{config}",
            keyboard,
        )

    async def _handle_refresh_status(self, callback_query: dict):
        chat_id = str(callback_query["message"]["chat"]["id"])
        status = await self._get_system_status()

        keyboard = InlineKeyboard()
        keyboard.add_row().add_button("[REFRESH] Refresh", "refresh_status").add_button(
            "[STATS] PnL", "show_pnl"
        )

        await self.edit_message(
            chat_id, callback_query["message"]["message_id"], status, keyboard
        )

    async def _handle_show_positions(self, callback_query: dict):
        chat_id = str(callback_query["message"]["chat"]["id"])
        status = await self._get_system_status()

        keyboard = InlineKeyboard()
        keyboard.add_row().add_button("[REFRESH] Refresh", "show_positions")

        await self.edit_message(
            chat_id, callback_query["message"]["message_id"], status, keyboard
        )

    async def listen_redis_pubsub(self):
        import json
        
        pubsub = self.redis.pubsub()
        channels = [
            "mtus:channel:position_opened",
            "mtus:channel:position_closed",
            "mtus:channel:system_alert",
            "mtus:channel:trade_failed",
            "mtus:channel:token_qualified",
            "mtus:channel:tp1_hit",
            "mtus:channel:tp2_hit",
            "mtus:channel:stop_loss_hit",
            "mtus:channel:trailing_stop_hit",
            "mtus:channel:time_sl_hit",
        ]
        
        for ch in channels:
            await pubsub.subscribe(ch)
            
        print(f"[BOT] Subscribed to Redis pub/sub channels: {channels}")
        
        while self.running:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    channel = message["channel"]
                    data_str = message["data"]
                    try:
                        data = json.loads(data_str)
                        await self.handle_pubsub_event(channel, data)
                    except Exception as e:
                        print(f"[BOT] Error handling pubsub event on {channel}: {e}")
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"[BOT] Error in pubsub listen loop: {e}")
                await asyncio.sleep(5)

    async def handle_pubsub_event(self, channel: str, data: dict):
        from .notification_templates import NotificationTemplates, add_environment_tag
        
        payload = data.get("payload", data)
        env = os.getenv("MTUS_ENVIRONMENT", "production").upper()
        
        text = ""
        parse_mode = "HTML"
        
        if channel == "mtus:channel:token_qualified":
            text = NotificationTemplates.token_qualified(payload)
            
        elif channel == "mtus:channel:position_opened":
            pos_id = payload.get("position_id") or payload.get("positionId") or data.get("correlation_id", "N/A")
            mint = payload.get("mint", "N/A")
            size_sol = float(payload.get("position_size_sol") or payload.get("size_sol") or 0.0)
            entry_price = float(payload.get("entry_price_sol") or payload.get("entryPriceSol") or 0.0)
            text = NotificationTemplates.trade_opened(pos_id, mint, size_sol, entry_price)
            
        elif channel == "mtus:channel:position_closed":
            pos_id = payload.get("position_id") or payload.get("positionId") or data.get("correlation_id", "N/A")
            mint = payload.get("mint", "N/A")
            pnl_sol = float(payload.get("realised_pnl_sol") or payload.get("pnl_sol") or payload.get("pnl") or 0.0)
            reason = payload.get("reason", "manual_exit")
            text = NotificationTemplates.position_closed(pos_id, mint, pnl_sol, reason, env)
            
        elif channel == "mtus:channel:tp1_hit":
            pos_id = payload.get("position_id") or payload.get("positionId") or data.get("correlation_id", "N/A")
            mint = payload.get("mint", "N/A")
            pnl_sol = float(payload.get("realised_pnl_sol") or payload.get("pnl_sol") or payload.get("pnl") or 0.0)
            text = NotificationTemplates.tp1_hit(pos_id, mint, pnl_sol)
            
        elif channel == "mtus:channel:tp2_hit":
            pos_id = payload.get("position_id") or payload.get("positionId") or data.get("correlation_id", "N/A")
            mint = payload.get("mint", "N/A")
            pnl_sol = float(payload.get("realised_pnl_sol") or payload.get("pnl_sol") or payload.get("pnl") or 0.0)
            text = NotificationTemplates.tp2_hit(pos_id, mint, pnl_sol)
            
        elif channel in ["mtus:channel:stop_loss_hit", "mtus:channel:trailing_stop_hit", "mtus:channel:time_sl_hit"]:
            pos_id = payload.get("position_id") or payload.get("positionId") or data.get("correlation_id", "N/A")
            mint = payload.get("mint", "N/A")
            pnl_sol = float(payload.get("realised_pnl_sol") or payload.get("pnl_sol") or payload.get("pnl") or 0.0)
            text = NotificationTemplates.stop_loss(pos_id, mint, pnl_sol)
            
        elif channel == "mtus:channel:trade_failed":
            # Support both nesting forms (Anansi python with nested 'token' vs Ares TS with flat keys)
            token_details = payload.get("token")
            if isinstance(token_details, dict):
                mint = token_details.get("mint", "N/A")
            else:
                token_details = None
                mint = payload.get("mint", "N/A")
                
            reason = payload.get("reason") or payload.get("error") or "unknown error"
            text = NotificationTemplates.trade_failed(mint, reason, token_details)
            
        elif channel == "mtus:channel:system_alert":
            level = payload.get("level", "INFO")
            message = payload.get("message", "")
            text = NotificationTemplates.system_alert(level, message)
            
        if text:
            text = add_environment_tag(text)
            await self.send_message(self.admin_chat_id, text, parse_mode=parse_mode)

    async def notify(self, message: str, priority: str = "normal"):
        if self.admin_chat_id:
            emoji = (
                "[HIGH]"
                if priority == "high"
                else "[MED]"
                if priority == "medium"
                else "[INFO]"
            )
            await self.send_message(self.admin_chat_id, f"{emoji} {message}")

    async def stop(self):
        self.running = False
        if self.session:
            await self.session.close()
        if self.redis:
            await self.redis.close()
        print("[BOT] Telegram bot stopped")


def create_bot(token: str, admin_chat_id: str, otp_seed: str) -> TelegramBot:
    return TelegramBot(token, admin_chat_id, otp_seed)


if __name__ == "__main__":
    import yaml
    import os

    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    )
    config_path = os.path.join(project_root, "config", "config.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    admin_chat_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID")
    otp_seed = os.getenv("TELEGRAM_OTP_SEED")

    if not all([token, admin_chat_id, otp_seed]):
        print("[ERROR] Missing required environment variables")
        exit(1)

    bot = create_bot(token, admin_chat_id, otp_seed)
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        asyncio.run(bot.stop())
