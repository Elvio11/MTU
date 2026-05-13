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
from src.python.shared.safe_output import safe_print as print
from src.python.shared.config_validator import validate_config
import yaml


async def main():
    from src.python.shared.telegram_bot import create_bot

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    config_path = os.path.join(project_root, "config", "config.yaml")

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        config = {}

    is_valid, error = validate_config(config)
    if not is_valid:
        print(f"[CONFIG] Configuration validation failed: {error}")
        sys.exit(1)

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
    await bot.start()

    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nShutting down Telegram bot...")
        await bot.stop()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
