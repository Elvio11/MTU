#!/usr/bin/env python3
"""
Test MTUS Bot Environment Setup
Verifies all APIs and connections work
"""

import os
import sys
from dotenv import load_dotenv

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
env_path = os.path.join(project_root, ".env")
load_dotenv(env_path)

src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

from python.shared.telegram_bot import TelegramBot, InlineKeyboard
from python.shared.telegram_auth import generate_otp, verify_otp
import aiohttp
import aioredis
import pytest


@pytest.mark.asyncio
async def test_helius_rpc():
    """Test Helius RPC connectivity"""
    print("\n[TEST] Helius RPC...")
    try:
        url = "https://mainnet.helius-rpc.com/?api-key=90b7db5c-9ecd-4f01-8c65-a886a8d1a67d"
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash"}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
                if "result" in data:
                    print(
                        f"   OK - Block hash: {data['result']['value']['blockhash'][:20]}..."
                    )
                    assert True
                else:
                    print(f"   ERROR: {data}")
                    assert False, f"Helius RPC error: {data}"
    except Exception as e:
        print(f"   ERROR: {e}")
        assert False, f"Helius RPC failed: {e}"


@pytest.mark.asyncio
async def test_alchemy_rpc():
    """Test Alchemy RPC connectivity"""
    print("[TEST] Alchemy RPC...")
    try:
        url = "https://solana-mainnet.g.alchemy.com/v2/_qcAnZERSDa8eRymPiKUx"
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getVersion"}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
                if "result" in data:
                    print(f"   OK - Version: {data['result']['solana-core']}")
                    assert True
                else:
                    print(f"   ERROR: {data}")
                    assert False, f"Alchemy RPC error: {data}"
    except Exception as e:
        print(f"   ERROR: {e}")
        assert False, f"Alchemy RPC failed: {e}"


@pytest.mark.asyncio
async def test_redis():
    """Test Redis connectivity"""
    print("[TEST] Redis...")
    try:
        redis = await aioredis.from_url("redis://localhost:6379", decode_responses=True)
        await redis.ping()
        await redis.close()
        print("   OK - Redis connected")
        assert True
    except Exception as e:
        print(f"   ERROR: {e}")
        assert False, f"Redis connection failed: {e}"


def test_telegram_bot():
    """Test Telegram bot initialization"""
    print("[TEST] Telegram Bot...")
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        admin_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")
        otp_seed = os.getenv("TELEGRAM_OTP_SEED", "")

        if not token or not admin_id or not otp_seed:
            print("   ERROR: Missing env variables")
            assert False, "Missing Telegram env variables"

        bot = TelegramBot(token, admin_id, otp_seed, "redis://localhost:6379")
        print(f"   OK - Bot initialized for admin: {admin_id}")

        otp = generate_otp(otp_seed)
        if verify_otp(otp_seed, otp):
            print(f"   OK - OTP working (code: {otp})")

        assert True
    except Exception as e:
        print(f"   ERROR: {e}")
        assert False, f"Telegram bot failed: {e}"


def test_env_variables():
    """Verify all required env variables are set"""
    print("\n[TEST] Environment Variables...")

    required_vars = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ADMIN_CHAT_ID",
        "TELEGRAM_OTP_SEED",
        "HELIUS_KEY",
        "ALCHEMY_URL",
        "REDIS_URL",
        "MTUS_ENVIRONMENT",
    ]

    all_ok = True
    for var in required_vars:
        value = os.getenv(var, "")
        if value:
            if "KEY" in var or "TOKEN" in var or "URL" in var:
                display = value[:10] + "..." if len(value) > 10 else value
            else:
                display = value
            print(f"   OK - {var}: {display}")
        else:
            print(f"   MISSING - {var}")
            all_ok = False

    assert all_ok, "Missing required environment variables"


async def main():
    print("=" * 60)
    print("MTUS Bot - Environment Setup Test")
    print("=" * 60)

    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    results = []

    results.append(("Environment Variables", test_env_variables()))
    results.append(("Redis", await test_redis()))
    results.append(("Helius RPC", await test_helius_rpc()))
    results.append(("Alchemy RPC", await test_alchemy_rpc()))
    results.append(("Telegram Bot", test_telegram_bot()))

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")
        if not result:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
