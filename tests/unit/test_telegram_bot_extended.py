import pytest
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock, ANY, PropertyMock
from src.python.shared.telegram_bot import TelegramBot, ButtonType, InlineButton, InlineKeyboard
from src.python.shared.constants import (
    REDIS_KEY_TRADING_ACTIVE,
    REDIS_KEY_KILL_SWITCH_TRIGGERED,
    CHANNEL_TRADING_PAUSED,
    CHANNEL_TRADING_RESUMED,
    CHANNEL_SWEEP_REQUESTED
)

@pytest.fixture
def bot():
    return TelegramBot(
        token="test_token",
        admin_chat_id="12345",
        otp_seed="test_seed"
    )

@pytest.mark.asyncio
async def test_handle_callback_query_invalid_user(bot):
    update = {
        "id": "cb_id",
        "from": {"id": 99999}, # Not admin
        "data": "any_data",
        "message": {"message_id": 1, "chat": {"id": 99999}} # Unauthorized chat
    }
    with patch.object(bot, "answer_callback", new_callable=AsyncMock) as mock_answer:
        await bot.handle_callback_query(update)
        mock_answer.assert_called_with(update["id"], "Unauthorized")

@pytest.mark.asyncio
async def test_handle_callback_query_valid(bot):
    update = {
        "id": "cb_id",
        "from": {"id": 12345},
        "data": "confirm_pause",
        "message": {"message_id": 1, "chat": {"id": 12345}}
    }
    mock_handler = AsyncMock()
    bot._callback_handlers["confirm_pause"] = mock_handler
    await bot.handle_callback_query(update)
    mock_handler.assert_called_once()

@pytest.mark.asyncio
async def test_handle_confirm_pause(bot):
    cb = {"id": "cb_id", "message": {"message_id": 1, "chat": {"id": 12345}}}
    with patch.object(bot, "edit_message", new_callable=AsyncMock) as mock_edit:
        await bot._handle_confirm_pause(cb)
        mock_edit.assert_called()
        assert "Confirm Pause" in mock_edit.call_args[0][2]

@pytest.mark.asyncio
async def test_execute_pause(bot):
    bot.redis = AsyncMock()
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot._execute_pause("12345")
        bot.redis.set.assert_called_with("mtus:trading_active", "false")
        mock_send.assert_called()

@pytest.mark.asyncio
async def test_execute_resume(bot):
    bot.redis = AsyncMock()
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot._execute_resume("12345")
        bot.redis.set.assert_called_with("mtus:trading_active", "true")
        mock_send.assert_called()

@pytest.mark.asyncio
async def test_execute_killswitch(bot):
    bot.redis = AsyncMock()
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot._execute_killswitch("12345")
        bot.redis.set.assert_any_call("mtus:killswitch_triggered", "true")
        mock_send.assert_called()

@pytest.mark.asyncio
async def test_handle_confirm_sweep(bot):
    bot.redis = AsyncMock()
    cb = {"id": "cb_id", "message": {"message_id": 1, "chat": {"id": 12345}}}
    await bot._handle_confirm_sweep(cb)
    # This just sends a confirmation message to chat

@pytest.mark.asyncio
async def test_handle_show_positions(bot):
    mock_redis = AsyncMock()
    mock_redis.keys.return_value = []
    mock_redis.get.return_value = "true"
    mock_redis.close = AsyncMock()
    
    cb = {"id": "cb_id", "message": {"message_id": 1, "chat": {"id": 12345}}}
    with patch("aioredis.from_url", new_callable=AsyncMock) as mock_from_url:
        mock_from_url.return_value = mock_redis
        with patch.object(bot, "edit_message", new_callable=AsyncMock) as mock_edit:
            await bot._handle_show_positions(cb)
            mock_edit.assert_called()

@pytest.mark.asyncio
async def test_handle_cancel(bot):
    cb = {"id": "cb_id", "message": {"message_id": 1, "chat": {"id": 12345}}}
    with patch.object(bot, "edit_message", new_callable=AsyncMock) as mock_edit:
        await bot._handle_cancel(cb)
        mock_edit.assert_called()

@pytest.mark.asyncio
async def test_send_welcome_message(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.send_welcome_message()
        mock_send.assert_called()

@pytest.mark.asyncio
async def test_handle_sweep_command(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.handle_sweep("12345", "/sweep", [])
        mock_send.assert_called()
        # The handle_sweep command actually asks for OTP if no args
        assert "Confirm" in mock_send.call_args[0][1] or "OTP" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_help_command(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.handle_help("12345", "/help", [])
        mock_send.assert_called()
        assert "[HELP]" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_initialize(bot):
    with patch("aiohttp.ClientSession") as mock_session:
        await bot.initialize()
        assert bot.session is not None

@pytest.mark.asyncio
async def test_notify(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.notify("Test notification")
        mock_send.assert_called()

@pytest.mark.asyncio
async def test_handle_killswitch_no_otp(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.handle_killswitch("12345", "/killswitch", [])
        mock_send.assert_called()
        assert "KILLSWITCH" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_killswitch_invalid_otp(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        # OTP is TOTP based, 123456 is likely invalid for test seed
        await bot.handle_killswitch("12345", "/killswitch 123456", ["123456"])
        mock_send.assert_called()
        assert "Invalid OTP" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_config_no_args(bot):
    with patch.object(bot, "_get_current_config", new_callable=AsyncMock, return_value="{}"):
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            await bot.handle_config("12345", "/config", [])
            mock_send.assert_called()
            assert "[CONFIG]" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_config_with_args(bot):
    with patch.object(bot, "_update_config", new_callable=AsyncMock) as mock_update:
        await bot.handle_config("12345", "/config key value", ["key", "value"])
        mock_update.assert_called_with("12345", "key", "value")

@pytest.mark.asyncio
async def test_handle_golive_no_args(bot):
    mock_agent = MagicMock()
    mock_agent.connect_redis = AsyncMock()
    mock_agent.check_mainnet_readiness.return_value = True
    mock_agent.stop = AsyncMock()
    
    # Mock data as objects with payload attribute
    mock_trade = MagicMock()
    mock_trade.payload = {"realised_pnl_sol": 0.1}
    mock_agent.paper_trades = [mock_trade]
    
    # Mock os.getenv to ensure we are in paper mode for the test
    with patch("os.getenv", return_value="paper"):
        with patch("src.python.agents.heracles.HeraclesAgent", return_value=mock_agent):
            with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
                await bot.handle_golive("12345", "/golive", [])
                mock_send.assert_called()
                assert "MAINNET READY" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_resume_no_otp(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.handle_resume("12345", "/resume", [])
        mock_send.assert_called()
        assert "RESUME" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_exit_no_otp(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.handle_exit("12345", "/exit", [])
        mock_send.assert_called()
        assert "Usage: `/exit" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_status_command(bot):
    with patch.object(bot, "_get_system_status", new_callable=AsyncMock, return_value="Status OK") as mock_status:
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            await bot.handle_status("12345", "/status", [])
            mock_status.assert_called_once()
            mock_send.assert_called_with("12345", "Status OK", ANY)

@pytest.mark.asyncio
async def test_handle_pnl_command(bot):
    with patch.object(bot, "_calculate_pnl", new_callable=AsyncMock, return_value="PnL Data") as mock_pnl:
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            await bot.handle_pnl("12345", "/pnl", [])
            mock_pnl.assert_called_once()
            mock_send.assert_called_with("12345", "PnL Data", ANY)

@pytest.mark.asyncio
async def test_calculate_pnl(bot):
    mock_redis = AsyncMock()
    mock_redis.keys.return_value = ["position_closed:1"]
    mock_redis.hgetall.return_value = {"realized_pnl": "0.5"}
    mock_redis.close = AsyncMock()
    
    with patch("aioredis.from_url", new_callable=AsyncMock) as mock_from_url:
        mock_from_url.return_value = mock_redis
        result = await bot._calculate_pnl()
        assert "0.5000 SOL" in result
        assert "Win Rate:* 100.0%" in result

@pytest.mark.asyncio
async def test_handle_show_pnl(bot):
    with patch.object(bot, "_calculate_pnl", new_callable=AsyncMock, return_value="PnL Info") as mock_calc:
        with patch.object(bot, "edit_message", new_callable=AsyncMock) as mock_edit:
            cb = {"id": "cb_id", "message": {"message_id": 1, "chat": {"id": 12345}}}
            await bot._handle_show_pnl(cb)
            mock_edit.assert_called()
            assert "PnL Info" in mock_edit.call_args[0][2]

@pytest.mark.asyncio
async def test_update_config_valid(bot):
    bot.redis = AsyncMock()
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot._update_config("12345", "position_size_sol", "0.5")
        bot.redis.set.assert_called()
        mock_send.assert_called()
        assert "Config Updated" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_confirm_killswitch(bot):
    bot.redis = AsyncMock()
    with patch.object(bot, "edit_message", new_callable=AsyncMock) as mock_edit:
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            cb = {"id": "cb_id", "message": {"message_id": 1, "chat": {"id": 12345}}}
            await bot._handle_confirm_killswitch(cb)
            mock_edit.assert_called()
            mock_send.assert_called()

@pytest.mark.asyncio
async def test_handle_confirm_exit(bot):
    bot.redis = AsyncMock()
    with patch.object(bot, "edit_message", new_callable=AsyncMock) as mock_edit:
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            cb = {"id": "cb_id", "data": "confirm_exit:pos_1", "message": {"message_id": 1, "chat": {"id": 12345}}}
            await bot._handle_confirm_exit(cb)
            mock_edit.assert_called()
            mock_send.assert_called()
            bot.redis.publish.assert_called()

@pytest.mark.asyncio
async def test_handle_refresh_status(bot):
    with patch.object(bot, "_get_system_status", new_callable=AsyncMock, return_value="Refreshed Status") as mock_status:
        with patch.object(bot, "edit_message", new_callable=AsyncMock) as mock_edit:
            cb = {"id": "cb_id", "message": {"message_id": 1, "chat": {"id": 12345}}}
            await bot._handle_refresh_status(cb)
            mock_edit.assert_called()
            assert "Refreshed Status" in mock_edit.call_args[0][2]

@pytest.mark.asyncio
async def test_handle_message_dispatcher(bot):
    with patch.object(bot, "handle_help", new_callable=AsyncMock) as mock_help:
        message = {
            "text": "/help",
            "chat": {"id": 12345}
        }
        await bot.handle_message(message)
        mock_help.assert_called()

@pytest.mark.asyncio
async def test_poll_updates(bot):
    mock_resp = AsyncMock()
    mock_resp.json.return_value = {
        "ok": True,
        "result": [
            {
                "update_id": 100,
                "message": {"text": "/help", "chat": {"id": 12345}}
            }
        ]
    }
    mock_resp.__aenter__.return_value = mock_resp
    
    bot.session = MagicMock()
    bot.session.get.return_value = mock_resp
    bot.running = True
    
    # Run poll_updates but make it stop after one iteration
    def stop_after_call(*args, **kwargs):
        bot.running = False
        return mock_resp
    
    bot.session.get.side_effect = stop_after_call
    
    with patch.object(bot, "handle_message", new_callable=AsyncMock) as mock_handle:
        await bot.poll_updates()
        mock_handle.assert_called()

@pytest.mark.asyncio
async def test_stop(bot):
    bot.session = AsyncMock()
    bot.redis = AsyncMock()
    await bot.stop()
    assert bot.running is False
    bot.session.close.assert_called()
    bot.redis.close.assert_called()

@pytest.mark.asyncio
async def test_handle_cancel(bot):
    with patch.object(bot, "edit_message", new_callable=AsyncMock) as mock_edit:
        cb = {"id": "cb_id", "message": {"message_id": 1, "chat": {"id": 12345}}}
        await bot._handle_cancel(cb)
        mock_edit.assert_called()
        assert "Action cancelled" in mock_edit.call_args[0][2]

@pytest.mark.asyncio
async def test_calculate_pnl_with_loss(bot):
    mock_redis = AsyncMock()
    mock_redis.keys.return_value = ["pos_1", "pos_2"]
    # One win, one loss
    mock_redis.hgetall.side_effect = [{"realized_pnl": "1.0"}, {"realized_pnl": "-0.5"}]
    mock_redis.close = AsyncMock()
    
    with patch("aioredis.from_url", new_callable=AsyncMock) as mock_from_url:
        mock_from_url.return_value = mock_redis
        result = await bot._calculate_pnl()
        assert "0.5000 SOL" in result
        assert "Win Rate:* 50.0%" in result

@pytest.mark.asyncio
async def test_handle_resume_with_otp(bot):
    with patch("src.python.shared.telegram_bot.verify_otp", return_value=True):
        with patch.object(bot, "_execute_resume", new_callable=AsyncMock) as mock_exec:
            await bot.handle_resume("12345", "/resume 123456", ["123456"])
            mock_exec.assert_called_once()

@pytest.mark.asyncio
async def test_handle_resume_invalid_otp(bot):
    with patch("src.python.shared.telegram_bot.verify_otp", return_value=False):
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            await bot.handle_resume("12345", "/resume 123456", ["123456"])
            mock_send.assert_called()
            assert "Invalid OTP" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_message_unauthorized(bot):
    bot.admin_chat_id = "999"
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.handle_message({"text": "/help", "chat": {"id": 12345}})
        mock_send.assert_called()
        assert "Unauthorized" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_notify(bot):
    bot.admin_chat_id = "12345"
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.notify("System alert", priority="high")
        mock_send.assert_called_with("12345", "[HIGH] System alert")

@pytest.mark.asyncio
async def test_send_message_exception(bot):
    mock_resp = AsyncMock()
    mock_resp.status = 400
    mock_resp.text = AsyncMock(return_value="Bad Request")
    mock_resp.__aenter__.return_value = mock_resp
    
    bot.session = MagicMock()
    bot.session.post.return_value = mock_resp
    
    # Should not raise, just log
    await bot.send_message("12345", "test")
    bot.session.post.assert_called()

@pytest.mark.asyncio
async def test_update_config_invalid_key(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot._update_config("12345", "invalid_key", "value")
        mock_send.assert_called()
        assert "Invalid config key" in mock_send.call_args[0][1]
