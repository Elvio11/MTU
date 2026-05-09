import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from src.python.shared.telegram_bot import InlineButton, InlineKeyboard, TelegramBot
from src.python.shared.telegram_auth import generate_otp


class TestInlineKeyboard(unittest.TestCase):
    def test_01_create_inline_button_with_callback(self):
        btn = InlineButton("Test", callback_data="test_data")
        result = btn.to_dict()
        self.assertEqual(result["text"], "Test")
        self.assertEqual(result["callback_data"], "test_data")

    def test_02_create_inline_button_with_url(self):
        btn = InlineButton("Link", url="https://example.com")
        result = btn.to_dict()
        self.assertEqual(result["text"], "Link")
        self.assertEqual(result["url"], "https://example.com")

    def test_03_add_row_and_buttons(self):
        keyboard = InlineKeyboard()
        keyboard.add_row()
        keyboard.add_button("Button1", callback_data="btn1")
        keyboard.add_button("Button2", callback_data="btn2")

        result = keyboard.to_dict()
        self.assertIn("inline_keyboard", result)
        self.assertEqual(len(result["inline_keyboard"]), 1)
        self.assertEqual(len(result["inline_keyboard"][0]), 2)

    def test_04_multiple_rows(self):
        keyboard = InlineKeyboard()
        keyboard.add_row().add_button("A", callback_data="a")
        keyboard.add_row().add_button("B", callback_data="b")

        result = keyboard.to_dict()
        self.assertEqual(len(result["inline_keyboard"]), 2)


class TestTelegramBot(unittest.TestCase):
    def setUp(self):
        self.seed = "test_seed_123"
        self.admin_id = "123456789"

    def test_01_bot_initialization(self):
        bot = TelegramBot("test_token", self.admin_id, self.seed)
        self.assertEqual(bot.token, "test_token")
        self.assertEqual(bot.admin_chat_id, self.admin_id)
        self.assertEqual(bot.otp_seed, self.seed)
        self.assertEqual(bot.base_url, "https://api.telegram.org/bottest_token")

    def test_02_callback_registration(self):
        bot = TelegramBot("test_token", self.admin_id, self.seed)
        bot._register_callback_handlers()
        self.assertIn("confirm_pause", bot._callback_handlers)
        self.assertIn("confirm_resume", bot._callback_handlers)
        self.assertIn("confirm_killswitch", bot._callback_handlers)
        self.assertIn("show_positions", bot._callback_handlers)
        self.assertIn("show_pnl", bot._callback_handlers)
        self.assertIn("cancel", bot._callback_handlers)

    def test_03_otp_verification(self):
        otp = generate_otp(self.seed)
        self.assertEqual(len(otp), 8)
        from src.python.shared.telegram_auth import verify_otp

        self.assertTrue(verify_otp(self.seed, otp))

    def test_04_invalid_otp_rejected(self):
        from src.python.shared.telegram_auth import verify_otp

        self.assertFalse(verify_otp(self.seed, "invalid_otp"))


if __name__ == "__main__":
    unittest.main()
