import pytest
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock, ANY, PropertyMock, mock_open
from src.python.shared.telegram_bot import (
    TelegramBot,
    ButtonType,
    InlineButton,
    InlineKeyboard,
)
from src.python.shared.constants import (
    REDIS_KEY_TRADING_ACTIVE,
    REDIS_KEY_KILL_SWITCH_TRIGGERED,
    CHANNEL_TRADING_PAUSED,
    CHANNEL_TRADING_RESUMED,
    CHANNEL_SWEEP_REQUESTED,
)


@pytest.fixture
def bot():
    return TelegramBot(token="test_token", admin_chat_id="12345", otp_seed="test_seed")


@pytest.mark.asyncio
async def test_handle_callback_query_invalid_user(bot):
    update = {
        "id": "cb_id",
        "from": {"id": 99999},  # Not admin
        "data": "any_data",
        "message": {"message_id": 1, "chat": {"id": 99999}},  # Unauthorized chat
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
        "message": {"message_id": 1, "chat": {"id": 12345}},
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
        assert (
            "Confirm" in mock_send.call_args[0][1] or "OTP" in mock_send.call_args[0][1]
        )


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
    with patch.object(
        bot, "_get_current_config", new_callable=AsyncMock, return_value="{}"
    ):
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
    with patch.object(
        bot, "_get_system_status", new_callable=AsyncMock, return_value="Status OK"
    ) as mock_status:
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            await bot.handle_status("12345", "/status", [])
            mock_status.assert_called_once()
            mock_send.assert_called_with("12345", "Status OK", ANY)


@pytest.mark.asyncio
async def test_handle_pnl_command(bot):
    with patch.object(
        bot, "_calculate_pnl", new_callable=AsyncMock, return_value="PnL Data"
    ) as mock_pnl:
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
    with patch.object(
        bot, "_calculate_pnl", new_callable=AsyncMock, return_value="PnL Info"
    ) as mock_calc:
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
            cb = {
                "id": "cb_id",
                "data": "confirm_exit:pos_1",
                "message": {"message_id": 1, "chat": {"id": 12345}},
            }
            await bot._handle_confirm_exit(cb)
            mock_edit.assert_called()
            mock_send.assert_called()
            bot.redis.publish.assert_called()


@pytest.mark.asyncio
async def test_handle_refresh_status(bot):
    with patch.object(
        bot,
        "_get_system_status",
        new_callable=AsyncMock,
        return_value="Refreshed Status",
    ) as mock_status:
        with patch.object(bot, "edit_message", new_callable=AsyncMock) as mock_edit:
            cb = {"id": "cb_id", "message": {"message_id": 1, "chat": {"id": 12345}}}
            await bot._handle_refresh_status(cb)
            mock_edit.assert_called()
            assert "Refreshed Status" in mock_edit.call_args[0][2]


@pytest.mark.asyncio
async def test_handle_message_dispatcher(bot):
    with patch.object(bot, "handle_help", new_callable=AsyncMock) as mock_help:
        message = {"text": "/help", "chat": {"id": 12345}}
        await bot.handle_message(message)
        mock_help.assert_called()


@pytest.mark.asyncio
async def test_poll_updates(bot):
    mock_resp = AsyncMock()
    mock_resp.json.return_value = {
        "ok": True,
        "result": [
            {"update_id": 100, "message": {"text": "/help", "chat": {"id": 12345}}}
        ],
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


# ═══════════════════════════════════════════════════════════════════════════════
# Coverage gap tests for telegram_bot.py remaining uncovered lines
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_inline_button_url(bot):
    btn = InlineButton("Link", url="https://example.com")
    result = btn.to_dict()
    assert result["text"] == "Link"
    assert result["url"] == "https://example.com"
    assert "callback_data" not in result


@pytest.mark.asyncio
async def test_start_method(bot):
    bot.redis = AsyncMock()
    with patch.object(bot, "initialize", new_callable=AsyncMock) as mock_init:
        with patch.object(
            bot, "send_welcome_message", new_callable=AsyncMock
        ) as mock_welcome:
            with patch.object(bot, "poll_updates", new_callable=AsyncMock) as mock_poll:
                with patch.object(bot, "listen_redis_pubsub", new_callable=AsyncMock) as mock_redis_pub:
                    await bot.start()
                    mock_init.assert_called_once()
                    mock_welcome.assert_called_once()
                    mock_poll.assert_called_once()
                    mock_redis_pub.assert_called_once()


@pytest.mark.asyncio
async def test_poll_updates_callback_query(bot):
    mock_resp = AsyncMock()
    mock_resp.json.return_value = {
        "ok": True,
        "result": [
            {
                "update_id": 100,
                "callback_query": {
                    "id": "cb1",
                    "data": "confirm_pause",
                    "message": {"chat": {"id": 12345}},
                },
            },
            {"update_id": 101, "message": {"text": "/help", "chat": {"id": 12345}}},
        ],
    }
    mock_resp.__aenter__.return_value = mock_resp
    bot.session = MagicMock()
    bot.session.get.return_value = mock_resp
    bot.running = True

    def stop_after(*args, **kwargs):
        bot.running = False
        return mock_resp

    bot.session.get.side_effect = stop_after

    with patch.object(bot, "handle_callback_query", new_callable=AsyncMock) as mock_cb:
        with patch.object(bot, "handle_message", new_callable=AsyncMock) as mock_msg:
            await bot.poll_updates()
            mock_cb.assert_called_once()
            mock_msg.assert_called_once()


@pytest.mark.asyncio
async def test_poll_updates_exception(bot):
    bot.session = MagicMock()
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        bot.running = False
        raise Exception("Network error")

    bot.session.get.side_effect = side_effect
    bot.running = True

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await bot.poll_updates()
        assert mock_sleep.called


@pytest.mark.asyncio
async def test_handle_callback_query_unknown_action(bot):
    cb = {
        "id": "cb_unknown",
        "from": {"id": 12345},
        "data": "nonexistent_action",
        "message": {"message_id": 1, "chat": {"id": 12345}},
    }
    with patch.object(bot, "answer_callback", new_callable=AsyncMock) as mock_answer:
        await bot.handle_callback_query(cb)
        mock_answer.assert_called_with(cb["id"], "Unknown action")


@pytest.mark.asyncio
async def test_answer_callback_success(bot):
    bot.session = MagicMock()
    mock_response = MagicMock()
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock()
    bot.session.post.return_value = mock_response

    await bot.answer_callback("cb_id", "Action complete")
    url = bot.session.post.call_args[0][0]
    assert "answerCallbackQuery" in url


@pytest.mark.asyncio
async def test_answer_callback_exception(bot):
    bot.session = MagicMock()
    bot.session.post.side_effect = Exception("API error")

    with patch("builtins.print") as mock_print:
        await bot.answer_callback("cb_id", "Test")
        mock_print.assert_called_with("Error answering callback: API error")


@pytest.mark.asyncio
async def test_send_message_api_failure(bot):
    bot.session = MagicMock()
    mock_response = MagicMock()
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock()
    mock_response.json = AsyncMock(
        return_value={"ok": False, "description": "Bad Request"}
    )
    bot.session.post.return_value = mock_response

    with patch("builtins.print") as mock_print:
        result = await bot.send_message("12345", "test")
        mock_print.assert_called()
        assert "Send message failed" in str(mock_print.call_args)
        assert result == {"ok": False, "description": "Bad Request"}


@pytest.mark.asyncio
async def test_edit_message_with_keyboard(bot):
    bot.session = MagicMock()
    mock_response = MagicMock()
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock()
    mock_response.json = AsyncMock(return_value={"ok": True})
    bot.session.post.return_value = mock_response

    keyboard = InlineKeyboard().add_button("OK", "confirm")
    result = await bot.edit_message("12345", 1, "New text", keyboard)
    args, kwargs = bot.session.post.call_args
    assert "editMessageText" in args[0]
    assert "reply_markup" in kwargs["json"]
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_edit_message_without_keyboard(bot):
    bot.session = MagicMock()
    mock_response = MagicMock()
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock()
    mock_response.json = AsyncMock(return_value={"ok": True})
    bot.session.post.return_value = mock_response

    result = await bot.edit_message("12345", 1, "New text")
    args, kwargs = bot.session.post.call_args
    assert "editMessageText" in args[0]
    assert "reply_markup" not in kwargs["json"]
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_handle_message_unknown_command(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.handle_message({"text": "/foobar", "chat": {"id": 12345}})
        mock_send.assert_called_once()
        assert "UNKNOWN" in mock_send.call_args[0][1]


@pytest.mark.asyncio
async def test_handle_start(bot):
    with patch.object(
        bot, "send_welcome_message", new_callable=AsyncMock
    ) as mock_welcome:
        await bot.handle_start("12345", "/start", [])
        mock_welcome.assert_called_once()


@pytest.mark.asyncio
async def test_handle_status_exception(bot):
    with patch.object(
        bot,
        "_get_system_status",
        new_callable=AsyncMock,
        side_effect=Exception("Redis down"),
    ):
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            await bot.handle_status("12345", "/status", [])
            mock_send.assert_called_once()
            assert "Redis down" in mock_send.call_args[0][1]


@pytest.mark.asyncio
async def test_handle_pause_no_otp(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.handle_pause("12345", "/pause", [])
        mock_send.assert_called_once()
        assert "Pause Trading" in mock_send.call_args[0][1]
        assert "12345" in bot.current_states
        assert bot.current_states["12345"]["action"] == "pause"


@pytest.mark.asyncio
async def test_handle_pause_invalid_otp(bot):
    with patch("src.python.shared.telegram_bot.verify_otp", return_value=False):
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            with patch.object(
                bot, "_execute_pause", new_callable=AsyncMock
            ) as mock_exec:
                await bot.handle_pause("12345", "/pause 000000", ["000000"])
                mock_send.assert_called_once()
                assert "Invalid OTP" in mock_send.call_args[0][1]
                mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_handle_cancel_with_state_cleanup(bot):
    bot.current_states["12345"] = {"action": "pause", "waiting_otp": True}
    cb = {"id": "cb_id", "message": {"message_id": 1, "chat": {"id": 12345}}}
    with patch.object(bot, "edit_message", new_callable=AsyncMock):
        await bot._handle_cancel(cb)
        assert "12345" not in bot.current_states


@pytest.mark.asyncio
async def test_handle_confirm_resume(bot):
    cb = {
        "id": "cb_id",
        "data": "confirm_resume",
        "message": {"message_id": 1, "chat": {"id": 12345}},
    }
    with patch.object(bot, "_execute_resume", new_callable=AsyncMock) as mock_exec:
        await bot._handle_confirm_resume(cb)
        mock_exec.assert_called_with("12345")


@pytest.mark.asyncio
async def test_handle_killswitch_valid_otp(bot):
    with patch("src.python.shared.telegram_bot.verify_otp", return_value=True):
        with patch.object(
            bot, "_execute_killswitch", new_callable=AsyncMock
        ) as mock_exec:
            await bot.handle_killswitch("12345", "/killswitch 123456", ["123456"])
            mock_exec.assert_called_once_with("12345")


@pytest.mark.asyncio
async def test_handle_exit_with_position_no_otp(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.handle_exit("12345", "/exit pos_1", ["pos_1"])
        mock_send.assert_called_once()
        assert "Close Position" in mock_send.call_args[0][1]


@pytest.mark.asyncio
async def test_handle_exit_invalid_otp(bot):
    with patch("src.python.shared.telegram_bot.verify_otp", return_value=False):
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            with patch.object(
                bot, "_execute_exit", new_callable=AsyncMock
            ) as mock_exec:
                await bot.handle_exit(
                    "12345", "/exit pos_1 000000", ["pos_1", "000000"]
                )
                mock_send.assert_called_once()
                assert "Invalid OTP" in mock_send.call_args[0][1]
                mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_execute_exit_with_redis(bot):
    bot.redis = AsyncMock()
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot._execute_exit("12345", "pos_1")
        bot.redis.publish.assert_called_once()
        args, _ = bot.redis.publish.call_args
        assert args[0] == "manual_exit_request"
        assert "pos_1" in args[1]
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_execute_exit_without_redis(bot):
    bot.redis = None
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot._execute_exit("12345", "pos_1")
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_handle_pnl_exception(bot):
    with patch.object(
        bot, "_calculate_pnl", new_callable=AsyncMock, side_effect=Exception("DB error")
    ):
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            await bot.handle_pnl("12345", "/pnl", [])
            mock_send.assert_called_once()
            assert "DB error" in mock_send.call_args[0][1]


@pytest.mark.asyncio
async def test_handle_sweep_invalid_otp(bot):
    with patch("src.python.shared.telegram_bot.verify_otp", return_value=False):
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            with patch.object(
                bot, "_execute_sweep", new_callable=AsyncMock
            ) as mock_exec:
                await bot.handle_sweep("12345", "/sweep 000000", ["000000"])
                mock_send.assert_called_once()
                assert "Invalid OTP" in mock_send.call_args[0][1]
                mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_handle_confirm_sweep_final(bot):
    cb = {"id": "cb_id", "message": {"message_id": 1, "chat": {"id": 12345}}}
    with patch.object(bot, "_execute_sweep", new_callable=AsyncMock) as mock_exec:
        await bot._handle_confirm_sweep_final(cb)
        mock_exec.assert_called_with("12345")


@pytest.mark.asyncio
async def test_execute_sweep_with_redis(bot):
    bot.redis = AsyncMock()
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot._execute_sweep("12345")
        bot.redis.publish.assert_called_once()
        args, _ = bot.redis.publish.call_args
        assert args[0] == "sweep_requested"
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_execute_sweep_without_redis(bot):
    bot.redis = None
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot._execute_sweep("12345")
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_handle_golive_already_production(bot):
    with patch("os.getenv", return_value="production"):
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            await bot.handle_golive("12345", "/golive", [])
            mock_send.assert_called_once()
            assert "Already in PRODUCTION" in mock_send.call_args[0][1]


@pytest.mark.asyncio
async def test_get_current_config_with_values(bot):
    mock_redis = AsyncMock()
    mock_redis.get.return_value = "0.5"
    mock_redis.close = AsyncMock()
    mock_redis.keys.return_value = []

    with patch("aioredis.from_url", new_callable=AsyncMock, return_value=mock_redis):
        result = await bot._get_current_config()
        assert "position_size_sol" in result
        assert "0.5" in result


@pytest.mark.asyncio
async def test_get_current_config_no_values(bot):
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.close = AsyncMock()
    mock_redis.keys.return_value = []

    with patch("aioredis.from_url", new_callable=AsyncMock, return_value=mock_redis):
        result = await bot._get_current_config()
        assert "No custom config set" in result


@pytest.mark.asyncio
async def test_handle_show_config(bot):
    cb = {"id": "cb_id", "message": {"message_id": 1, "chat": {"id": 12345}}}
    with patch.object(
        bot, "_get_current_config", new_callable=AsyncMock, return_value="cfg_data"
    ):
        with patch.object(bot, "edit_message", new_callable=AsyncMock) as mock_edit:
            await bot._handle_show_config(cb)
            mock_edit.assert_called_once()
            assert "cfg_data" in mock_edit.call_args[0][2]


@pytest.mark.asyncio
async def test_create_bot():
    from src.python.shared.telegram_bot import create_bot

    result = create_bot("tok", "admin", "seed")
    assert isinstance(result, TelegramBot)
    assert result.token == "tok"
    assert result.admin_chat_id == "admin"


@pytest.mark.asyncio
async def test_main_block_telegram_bot():
    import runpy
    import yaml

    with patch("builtins.open", mock_open(read_data="key: value")):
        with patch("yaml.safe_load", return_value={"key": "value"}):
            with patch(
                "os.getenv",
                side_effect=lambda k, d=None: {
                    "TELEGRAM_BOT_TOKEN": "tok",
                    "TELEGRAM_ADMIN_CHAT_ID": "admin",
                    "TELEGRAM_OTP_SEED": "seed",
                }.get(k, d),
            ):
                with patch.object(asyncio, "run"):
                    runpy.run_module(
                        "src.python.shared.telegram_bot", run_name="__main__"
                    )


@pytest.mark.asyncio
async def test_main_block_exit_missing_env():
    import runpy

    with patch("builtins.open", mock_open(read_data="key: value")):
        with patch("yaml.safe_load", return_value={"key": "value"}):
            with patch("os.getenv", return_value=None):
                with pytest.raises(SystemExit) as exc:
                    runpy.run_module(
                        "src.python.shared.telegram_bot", run_name="__main__"
                    )
                assert exc.value.code == 1


@pytest.mark.asyncio
async def test_main_block_keyboard_interrupt():
    import runpy

    with patch("builtins.open", mock_open(read_data="key: value")):
        with patch("yaml.safe_load", return_value={"key": "value"}):
            with patch(
                "os.getenv",
                side_effect=lambda k, d=None: {
                    "TELEGRAM_BOT_TOKEN": "tok",
                    "TELEGRAM_ADMIN_CHAT_ID": "admin",
                    "TELEGRAM_OTP_SEED": "seed",
                }.get(k, d),
            ):
                with patch.object(
                    asyncio, "run", side_effect=[KeyboardInterrupt, None]
                ):
                    runpy.run_module(
                        "src.python.shared.telegram_bot", run_name="__main__"
                    )
