import pytest
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from src.python.shared.telegram_bot import TelegramBot, ButtonType, InlineButton, InlineKeyboard

@pytest.fixture
def bot():
    return TelegramBot(
        token="test_token",
        admin_chat_id="12345",
        otp_seed="test_seed",
        redis_url="redis://localhost:6379"
    )

def mock_aiohttp_cm(mock_response):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_response)
    cm.__aexit__ = AsyncMock()
    return cm

@pytest.mark.asyncio
async def test_initialize(bot):
    with patch("aioredis.from_url", new_callable=AsyncMock) as mock_from_url:
        await bot.initialize()
        mock_from_url.assert_called_once()
        assert bot.redis is not None
        assert bot.session is not None
        assert bot.running is True

@pytest.mark.asyncio
async def test_handle_message_unauthorized(bot):
    bot.session = MagicMock()
    message = {
        "text": "/status",
        "chat": {"id": 67890} # Different chat ID
    }
    
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.handle_message(message)
        mock_send.assert_called_once_with("67890", "[BLOCKED] Unauthorized. This bot is for admin only.")

@pytest.mark.asyncio
async def test_handle_message_authorized_command(bot):
    bot.session = MagicMock()
    message = {
        "text": "/help",
        "chat": {"id": 12345}
    }
    
    with patch.object(bot, "handle_help", new_callable=AsyncMock) as mock_help:
        await bot.handle_message(message)
        mock_help.assert_called_once()

@pytest.mark.asyncio
async def test_handle_callback_query_unauthorized(bot):
    bot.session = MagicMock()
    callback_query = {
        "id": "cb1",
        "message": {"chat": {"id": 67890}},
        "data": "confirm_pause"
    }
    
    with patch.object(bot, "answer_callback", new_callable=AsyncMock) as mock_answer:
        await bot.handle_callback_query(callback_query)
        mock_answer.assert_called_once_with("cb1", "Unauthorized")

@pytest.mark.asyncio
async def test_handle_callback_query_authorized(bot):
    bot.session = MagicMock()
    
    with patch.object(bot, "_handle_confirm_pause", new_callable=AsyncMock) as mock_handler:
        bot._register_callback_handlers()
        callback_query = {
            "id": "cb1",
            "message": {
                "chat": {"id": 12345},
                "message_id": 100
            },
            "data": "confirm_pause"
        }
        await bot.handle_callback_query(callback_query)
        mock_handler.assert_called_once()

@pytest.mark.asyncio
async def test_send_message(bot):
    bot.session = MagicMock()
    mock_response = MagicMock()
    mock_response.json = AsyncMock(return_value={"ok": True})
    bot.session.post.return_value = mock_aiohttp_cm(mock_response)
    
    keyboard = InlineKeyboard().add_button("Test", "cb_test")
    await bot.send_message("12345", "Hello", keyboard)
    
    bot.session.post.assert_called_once()
    args, kwargs = bot.session.post.call_args
    assert "sendMessage" in args[0]
    assert kwargs["json"]["chat_id"] == "12345"
    assert "cb_test" in kwargs["json"]["reply_markup"]

@pytest.mark.asyncio
async def test_poll_updates(bot):
    bot.session = MagicMock()
    mock_response = MagicMock()
    mock_response.json = AsyncMock(return_value={
        "ok": True,
        "result": [
            {
                "update_id": 1,
                "message": {"text": "/status", "chat": {"id": 12345}}
            }
        ]
    })
    
    def get_with_stop(*args, **kwargs):
        bot.running = False
        return mock_aiohttp_cm(mock_response)
        
    bot.session.get.side_effect = get_with_stop
    bot.running = True
    
    with patch.object(bot, "handle_message", new_callable=AsyncMock) as mock_handle:
        await bot.poll_updates()
        mock_handle.assert_called_once()

@pytest.mark.asyncio
async def test_get_system_status(bot):
    mock_redis = AsyncMock()
    mock_redis.keys.return_value = ["position:1"]
    mock_redis.hgetall.return_value = {"symbol": "TEST", "state": "OPEN", "unrealized_pnl": "0.1"}
    mock_redis.get.side_effect = ["running", "true"]
    mock_redis.close = AsyncMock()
    
    with patch("aioredis.from_url", new_callable=AsyncMock, return_value=mock_redis):
        status = await bot._get_system_status()
        assert "TEST" in status
        assert "*Active Positions:* 1/1" in status

@pytest.mark.asyncio
async def test_calculate_pnl(bot):
    mock_redis = AsyncMock()
    mock_redis.keys.return_value = ["position_closed:1"]
    mock_redis.hgetall.return_value = {"realized_pnl": "0.5"}
    mock_redis.close = AsyncMock()
    
    with patch("aioredis.from_url", new_callable=AsyncMock, return_value=mock_redis):
        pnl = await bot._calculate_pnl()
        assert "0.5000 SOL" in pnl
        assert "*Win Rate:* 100.0%" in pnl

@pytest.mark.asyncio
async def test_execute_pause(bot):
    bot.redis = AsyncMock()
    bot.session = MagicMock()
    
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot._execute_pause("12345")
        bot.redis.set.assert_called_with("mtus:trading_active", "false")
        bot.redis.publish.assert_called()
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_execute_resume(bot):
    bot.redis = AsyncMock()
    bot.session = MagicMock()
    
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot._execute_resume("12345")
        bot.redis.set.assert_called_with("mtus:trading_active", "true")
        bot.redis.publish.assert_called()
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_handle_status(bot):
    with patch.object(bot, "_get_system_status", new_callable=AsyncMock, return_value="status"):
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            await bot.handle_status("12345", "/status", [])
            mock_send.assert_called_once()
            assert "status" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_pnl(bot):
    with patch.object(bot, "_calculate_pnl", new_callable=AsyncMock, return_value="pnl"):
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            await bot.handle_pnl("12345", "/pnl", [])
            mock_send.assert_called_once()
            assert "pnl" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_help(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.handle_help("12345", "/help", [])
        mock_send.assert_called_once()
        assert "HELP" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_sweep_no_otp(bot):
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        await bot.handle_sweep("12345", "/sweep", [])
        mock_send.assert_called_once()
        assert "Sweep Funds" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_golive_not_ready(bot):
    import os
    os.environ["MTUS_ENVIRONMENT"] = "paper"
    mock_agent = MagicMock()
    mock_agent.check_mainnet_readiness.return_value = False
    mock_agent.paper_trades = []
    mock_agent.connect_redis = AsyncMock()
    mock_agent.stop = AsyncMock()
    
    with patch("src.python.agents.heracles.HeraclesAgent", return_value=mock_agent):
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            await bot.handle_golive("12345", "/golive", [])
            assert "NOT READY" in mock_send.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_golive_ready(bot):
    import os
    os.environ["MTUS_ENVIRONMENT"] = "paper"
    mock_agent = MagicMock()
    mock_trade = MagicMock()
    mock_trade.payload = {"realised_pnl_sol": 1.0}
    mock_agent.paper_trades = [mock_trade] * 50
    mock_agent.check_mainnet_readiness.return_value = True
    mock_agent.connect_redis = AsyncMock()
    mock_agent.stop = AsyncMock()
    
    with patch("src.python.agents.heracles.HeraclesAgent", return_value=mock_agent):
        with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
            await bot.handle_golive("12345", "/golive", [])
            assert "MAINNET READY" in mock_send.call_args[0][1]
            assert "production" in bot.send_message.call_args[0][1].lower()

@pytest.mark.asyncio
async def test_handle_pause_with_otp(bot):
    with patch("src.python.shared.telegram_bot.verify_otp", return_value=True):
        with patch.object(bot, "_execute_pause", new_callable=AsyncMock) as mock_exec:
            await bot.handle_pause("12345", "/pause 123456", ["123456"])
            mock_exec.assert_called_once()

@pytest.mark.asyncio
async def test_handle_resume_with_otp(bot):
    with patch("src.python.shared.telegram_bot.verify_otp", return_value=True):
        with patch.object(bot, "_execute_resume", new_callable=AsyncMock) as mock_exec:
            await bot.handle_resume("12345", "/resume 123456", ["123456"])
            mock_exec.assert_called_once()

@pytest.mark.asyncio
async def test_handle_exit_with_otp(bot):
    with patch("src.python.shared.telegram_bot.verify_otp", return_value=True):
        with patch.object(bot, "_execute_exit", new_callable=AsyncMock) as mock_exec:
            await bot.handle_exit("12345", "/exit pos1 123456", ["pos1", "123456"])
            mock_exec.assert_called_once_with("12345", "pos1")

@pytest.mark.asyncio
async def test_handle_sweep_with_otp(bot):
    with patch("src.python.shared.telegram_bot.verify_otp", return_value=True):
        with patch.object(bot, "_execute_sweep", new_callable=AsyncMock) as mock_exec:
            await bot.handle_sweep("12345", "/sweep 123456", ["123456"])
            mock_exec.assert_called_once()
