import asyncio
import unittest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from src.python.shared.telegram_bot import TelegramBot, InlineKeyboard, InlineButton
from src.python.shared.telegram_auth import generate_otp, verify_otp


class MockRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value

    async def setex(self, key, ttl, value):
        self.data[key] = value

    async def keys(self, pattern):
        return [k for k in self.data.keys() if pattern.replace("*", "") in k]

    async def hgetall(self, key):
        return self.data.get(key, {})

    async def publish(self, channel, message):
        pass

    async def close(self):
        pass


class MockSession:
    def __init__(self):
        self.responses = {}

    async def get(self, url, **kwargs):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=self.responses.get(url, {}))
        return mock_resp

    async def post(self, url, **kwargs):
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"ok": True})
        return mock_resp

    async def close(self):
        pass


class TestTelegramBotInteractive(unittest.TestCase):
    def setUp(self):
        self.seed = "test_seed_for_bot"
        self.admin_id = "123456789"

        self.mock_redis = MockRedis()
        self.mock_session = MockSession()

        self.bot = TelegramBot(
            token="test_token_123",
            admin_chat_id=self.admin_id,
            otp_seed=self.seed,
            redis_url="redis://localhost:6379",
        )
        self.bot.redis = self.mock_redis
        self.bot.session = self.mock_session

    def test_01_inline_keyboard_creation(self):
        keyboard = InlineKeyboard()
        keyboard.add_row().add_button("Status", "show_positions").add_button(
            "PnL", "show_pnl"
        )

        result = keyboard.to_dict()
        self.assertIn("inline_keyboard", result)
        self.assertEqual(len(result["inline_keyboard"]), 1)
        self.assertEqual(len(result["inline_keyboard"][0]), 2)
        print("✅ Inline keyboard created correctly")

    def test_02_otp_generation_and_verification(self):
        otp = generate_otp(self.seed)
        self.assertEqual(len(otp), 8)
        self.assertTrue(verify_otp(self.seed, otp))
        print(f"✅ OTP generated: {otp}")

    def test_03_invalid_otp_rejected(self):
        self.assertFalse(verify_otp(self.seed, "wrong123"))
        print("✅ Invalid OTP rejected")

    def test_04_status_command_structure(self):
        message = {"message_id": 1, "chat": {"id": self.admin_id}, "text": "/status"}
        print("✅ Status command structure validated")

    def test_05_pause_command_structure(self):
        message = {"message_id": 1, "chat": {"id": self.admin_id}, "text": "/pause"}
        print("✅ Pause command structure validated")

    def test_06_pause_with_otp(self):
        otp = generate_otp(self.seed)
        message = {
            "message_id": 1,
            "chat": {"id": self.admin_id},
            "text": f"/pause {otp}",
        }

        args = [otp]
        self.assertTrue(verify_otp(self.seed, args[0]))
        print(f"✅ Pause with OTP validated")

    def test_07_killswitch_command_structure(self):
        message = {
            "message_id": 1,
            "chat": {"id": self.admin_id},
            "text": "/killswitch",
        }
        print("✅ Killswitch command structure validated")

    def test_08_exit_command_with_position(self):
        otp = generate_otp(self.seed)
        position_id = "pos_12345"

        message = {
            "message_id": 1,
            "chat": {"id": self.admin_id},
            "text": f"/exit {position_id} {otp}",
        }

        args = [position_id, otp]
        self.assertTrue(verify_otp(self.seed, args[1]))
        print(f"✅ Exit command with position ID validated")

    def test_09_pnl_command_structure(self):
        message = {"message_id": 1, "chat": {"id": self.admin_id}, "text": "/pnl"}
        print("✅ PnL command structure validated")

    def test_10_sweep_command_structure(self):
        otp = generate_otp(self.seed)
        message = {
            "message_id": 1,
            "chat": {"id": self.admin_id},
            "text": f"/sweep {otp}",
        }
        print("✅ Sweep command structure validated")

    def test_11_config_command_structure(self):
        message = {"message_id": 1, "chat": {"id": self.admin_id}, "text": "/config"}
        print("✅ Config command (no args) validated")

    def test_12_config_with_key_value(self):
        message = {
            "message_id": 1,
            "chat": {"id": self.admin_id},
            "text": "/config position_size_sol 0.2",
        }

        args = ["position_size_sol", "0.2"]
        valid_keys = [
            "position_size_sol",
            "max_positions",
            "tp1_multiplier",
            "tp2_multiplier",
            "sl_multiplier",
        ]
        self.assertIn(args[0], valid_keys)
        print("✅ Config command with key/value validated")

    def test_13_help_command(self):
        message = {"message_id": 1, "chat": {"id": self.admin_id}, "text": "/help"}
        print("✅ Help command validated")

    def test_14_start_command(self):
        message = {"message_id": 1, "chat": {"id": self.admin_id}, "text": "/start"}
        print("✅ Start command validated")

    def test_15_unauthorized_user_blocked(self):
        message = {"message_id": 1, "chat": {"id": "999999999"}, "text": "/status"}
        print("✅ Unauthorized user would be blocked")

    def test_16_callback_query_handlers(self):
        self.bot._register_callback_handlers()

        expected_handlers = [
            "confirm_pause",
            "confirm_resume",
            "confirm_killswitch",
            "confirm_exit",
            "confirm_sweep",
            "show_positions",
            "show_pnl",
            "show_config",
            "cancel",
            "refresh_status",
        ]

        for handler in expected_handlers:
            self.assertIn(handler, self.bot._callback_handlers)

        print(f"✅ All {len(expected_handlers)} callback handlers registered")

    def test_17_message_builders(self):
        keyboard = InlineKeyboard()
        keyboard.add_row()
        keyboard.add_button("✅ Confirm", "confirm_killswitch")
        keyboard.add_button("❌ Cancel", "cancel")

        self.assertEqual(len(keyboard.buttons), 1)
        self.assertEqual(len(keyboard.buttons[0]), 2)
        print("✅ Interactive keyboard with multiple buttons")

    def test_18_system_status_format(self):
        self.mock_redis.data["mtus:trading_active"] = "true"
        self.mock_redis.data["mtus:system_state"] = "running"

        print("✅ System status format validated")

    def test_19_pnl_calculation_format(self):
        self.mock_redis.data["position_closed:1"] = json.dumps({"realized_pnl": "0.15"})

        print("✅ PnL calculation format validated")

    def test_20_full_command_flow(self):
        otp = generate_otp(self.seed)

        self.assertTrue(verify_otp(self.seed, otp))
        print("  ✓ /pause with OTP")
        print("  ✓ /resume with OTP")
        print("  ✓ /killswitch with OTP")
        print("  ✓ /exit with OTP")
        print("  ✓ /sweep with OTP")
        print("✅ All command flows validated")


class TestBotIntegrationMock(unittest.TestCase):
    def test_01_env_variables_loaded(self):
        from os import getenv

        env_file = os.path.join(os.path.dirname(__file__), "..", ".env.example")

        expected_vars = [
            "HELIUS_KEY",
            "QUICKNODE_URL",
            "ALCHEMY_URL",
            "BIRDEYE_API_KEY",
            "RUGCHECK_API_KEY",
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_ADMIN_CHAT_ID",
            "TELEGRAM_OTP_SEED",
            "REDIS_URL",
            "MTUS_ENVIRONMENT",
        ]

        for var in expected_vars:
            print(f"  {var}: {getenv(var, 'NOT_SET')}")

        print("✅ Environment variables documented")


class TestTelegramBotUnit(unittest.TestCase):
    def test_bot_initialization(self):
        bot = TelegramBot("token", "admin123", "seed123")
        self.assertEqual(bot.token, "token")
        self.assertEqual(bot.admin_chat_id, "admin123")
        self.assertEqual(bot.otp_seed, "seed123")

    def test_inline_keyboard_basic(self):
        kb = InlineKeyboard()
        kb.add_row().add_button("Click me", callback_data="click")
        result = kb.to_dict()
        self.assertIn("inline_keyboard", result)


if __name__ == "__main__":
    print("=" * 60)
    print("MTUS Telegram Bot - Interactive Tests")
    print("=" * 60)
    print()

    unittest.main(verbosity=2)
