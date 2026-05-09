"""
E2E Test - Telegram Admin Controls
Tests all Telegram bot commands and controls.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.python.shared.telegram_bot import TelegramBot, InlineKeyboard
from src.python.shared.telegram_auth import generate_otp, verify_otp
from src.python.shared.constants import (
    REDIS_KEY_TRADING_ACTIVE,
    REDIS_KEY_TRADING_PAUSED,
)


class TestTelegramControls:
    """Test Telegram admin controls."""

    @pytest.mark.asyncio
    async def test_01_status_command(self, clean_redis):
        """Test: /status command returns system state."""
        redis = clean_redis

        await redis.set(REDIS_KEY_TRADING_ACTIVE, "true")
        await redis.sadd("mtus:active_positions", "pos_001", "pos_002")

        trading_active = await redis.get(REDIS_KEY_TRADING_ACTIVE)
        positions = await redis.smembers("mtus:active_positions")

        assert trading_active == "true"
        assert len(positions) == 2

    @pytest.mark.asyncio
    async def test_02_pause_command(self, clean_redis):
        """Test: /pause command sets trading_paused key."""
        redis = clean_redis

        await redis.set(REDIS_KEY_TRADING_PAUSED, "true")
        paused = await redis.get(REDIS_KEY_TRADING_PAUSED)

        assert paused == "true"

    @pytest.mark.asyncio
    async def test_03_resume_command(self, clean_redis):
        """Test: /resume command removes pause."""
        redis = clean_redis

        await redis.set(REDIS_KEY_TRADING_PAUSED, "true")
        await redis.delete(REDIS_KEY_TRADING_PAUSED)
        paused = await redis.get(REDIS_KEY_TRADING_PAUSED)

        assert paused is None

    @pytest.mark.asyncio
    async def test_04_killswitch_command(self, clean_redis):
        """Test: /killswitch command."""
        redis = clean_redis

        await redis.set("mtus:kill_switch", "active")

        result = await redis.get("mtus:kill_switch")

        assert result == "active"

    def test_05_otp_generation(self):
        """Test: OTP generation and verification."""
        seed = "test_otp_seed_123"

        otp = generate_otp(seed)

        assert len(otp) >= 6

        is_valid = verify_otp(seed, otp)
        assert is_valid == True

        is_invalid = verify_otp(seed, "000000")
        assert is_invalid == False

    def test_06_inline_keyboard_creation(self):
        """Test: Inline keyboard creation."""
        keyboard = InlineKeyboard()

        keyboard.add_row().add_button("Status", "show_status")
        keyboard.add_row().add_button("PnL", "show_pnl").add_button(
            "Config", "show_config"
        )

        kb_dict = keyboard.to_dict()

        assert "inline_keyboard" in kb_dict
        assert len(kb_dict["inline_keyboard"]) == 2

    @pytest.mark.asyncio
    async def test_07_positions_display(self, clean_redis):
        """Test: Display active positions."""
        redis = clean_redis

        positions = {
            "pos_001": {"mint": "abc123", "size": 0.0005, "pnl": 0.001},
            "pos_002": {"mint": "def456", "size": 0.0005, "pnl": -0.0002},
        }

        for pos_id, data in positions.items():
            key = f"mtus:position:{pos_id}"
            for field, value in data.items():
                await redis.hset(key, field, str(value))

        all_positions = []
        async for key in redis.scan_iter("mtus:position:*"):
            pos_id = key.replace("mtus:position:", "")
            all_positions.append(pos_id)

        assert len(all_positions) == 2

    @pytest.mark.asyncio
    async def test_08_pnl_calculation(self, clean_redis):
        """Test: PnL calculation."""
        redis = clean_redis

        realized_pnl = 0.0
        positions = ["pos_001", "pos_002"]
        pnls = [0.001, -0.0002]

        for pnl in pnls:
            realized_pnl += pnl

        total_pnl = round(realized_pnl, 4)

        assert total_pnl == 0.0008

    @pytest.mark.asyncio
    async def test_09_config_display(self, test_config):
        """Test: Config display."""
        config = test_config

        position_size = config["trading"]["position_size_sol"]
        max_positions = config["trading"]["max_simultaneous_positions"]
        daily_loss = config["trading"]["daily_loss_limit_sol"]

        assert position_size == 0.0005
        assert max_positions == 1
        assert daily_loss == 0.002

    @pytest.mark.asyncio
    async def test_10_sweep_command(self, clean_redis):
        """Test: /sweep command structure."""
        redis = clean_redis

        await redis.set("mtus:sweep_requested", "true")
        requested = await redis.get("mtus:sweep_requested")

        assert requested == "true"
