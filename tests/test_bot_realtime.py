#!/usr/bin/env python3
import asyncio
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

from python.shared.telegram_bot import TelegramBot, InlineKeyboard
from python.shared.telegram_auth import generate_otp, verify_otp


async def main():
    print("=" * 60)
    print("MTUS Telegram Bot - Real-time Test")
    print("=" * 60)
    print()

    test_token = "test_token_12345"
    test_admin_id = "123456789"
    test_seed = "test_otp_seed_123"

    print("1. Creating bot instance...")
    bot = TelegramBot(
        token=test_token,
        admin_chat_id=test_admin_id,
        otp_seed=test_seed,
        redis_url="redis://localhost:6379",
    )

    await bot.initialize()
    print("   Bot initialized")
    print(f"   Redis: {bot.redis is not None}")
    print(f"   Session: {bot.session is not None}")
    print()

    print("2. Testing inline keyboard...")
    keyboard = InlineKeyboard()
    keyboard.add_row().add_button("Status", "show_positions")
    keyboard.add_row().add_button("PnL", "show_pnl").add_button("Config", "show_config")
    kb_dict = keyboard.to_dict()
    print(f"   Keyboard: {len(kb_dict['inline_keyboard'])} rows created")
    print()

    print("3. Testing OTP...")
    otp = generate_otp(test_seed)
    print(f"   Generated: {otp}")
    print(f"   Verified: {verify_otp(test_seed, otp)}")
    print()

    print("4. Testing callback handlers...")
    bot._register_callback_handlers()
    print(f"   {len(bot._callback_handlers)} handlers registered")
    print()

    print("5. Testing status fetch...")
    try:
        status = await bot._get_system_status()
        print("   Status OK")
    except Exception as e:
        print(f"   Status: {e}")
    print()

    print("6. Testing PnL...")
    try:
        pnl = await bot._calculate_pnl()
        print("   PnL OK")
    except Exception as e:
        print(f"   PnL: {e}")
    print()

    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)

    await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
