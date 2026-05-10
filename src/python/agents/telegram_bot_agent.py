#!/usr/bin/env python3
"""
Telegram Bot Agent (AGT-11)
Entry point for running the Telegram bot as a PM2-managed service
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Project is D:\Trader - go up 2 directories from src/python/agents/
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
sys.path.insert(0, project_root)
os.chdir(project_root)

# Load environment variables
load_dotenv("./.env")
print(f"[Telegram] Project root: {project_root}")


async def main():
    from src.python.shared.telegram_bot import create_bot

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    admin_chat_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID")
    otp_seed = os.getenv("TELEGRAM_OTP_SEED", "default_seed_change_me")

    print(
        f"Loaded env - Token: {token[:10] if token else 'None'}..., Chat ID: {admin_chat_id}"
    )

    if not token or not admin_chat_id:
        print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_ID must be set")
        print(f"Token: {token}, Chat ID: {admin_chat_id}")
        sys.exit(1)

    print("=" * 50)
    print("Telegram Bot (AGT-11) Starting...")
    print("=" * 50)

    bot = create_bot(token, admin_chat_id, otp_seed)
    await bot.initialize()
    await bot.start()

    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nShutting down Telegram bot...")
        await bot.stop()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
