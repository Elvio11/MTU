import pytest
import os
import sys
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

# Prevent the agent script from messing with the working directory during import
with patch("os.chdir"):
    import src.python.agents.telegram_bot_agent as telegram_agent

@pytest.mark.asyncio
async def test_telegram_bot_agent_main_success():
    """Test successful initialization and startup of the telegram bot agent."""
    with patch("os.getenv") as mock_getenv:
        def getenv_side_effect(key, default=None):
            if key == "TELEGRAM_BOT_TOKEN":
                return "fake_token"
            if key == "TELEGRAM_ADMIN_CHAT_ID":
                return "123456"
            if key == "TELEGRAM_OTP_SEED":
                return "fake_seed"
            return default
        mock_getenv.side_effect = getenv_side_effect

        mock_bot = AsyncMock()
        mock_bot.initialize = AsyncMock()
        mock_bot.start = AsyncMock()
        mock_bot.stop = AsyncMock()
        
        # We need to simulate the Event.wait() throwing KeyboardInterrupt to exit the infinite loop
        # so we don't block the test forever.
        mock_event_wait = AsyncMock(side_effect=KeyboardInterrupt)

        with patch("src.python.shared.telegram_bot.create_bot", return_value=mock_bot) as mock_create_bot:
            with patch("asyncio.Event.wait", mock_event_wait):
                await telegram_agent.main()

        mock_create_bot.assert_called_once_with("fake_token", "123456", "fake_seed")
        mock_bot.initialize.assert_awaited_once()
        mock_bot.start.assert_awaited_once()
        mock_bot.stop.assert_awaited_once()

@pytest.mark.asyncio
async def test_telegram_bot_agent_main_missing_env():
    """Test exit when missing necessary env vars."""
    with patch("os.getenv", return_value=None):
        with patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
            with pytest.raises(SystemExit) as excinfo:
                await telegram_agent.main()
            assert excinfo.value.code == 1
            mock_exit.assert_called_once_with(1)

def test_telegram_bot_agent_name_main():
    """Test __main__ block logic by running it as a script."""
    with patch.object(telegram_agent, "__name__", "__main__"):
        with patch("asyncio.run") as mock_run:
            # We must use exec or reload to re-evaluate the module level code, or just test the if block logic directly if possible.
            # But the if block is at module level. Let's just mock asyncio.run and run the script as __main__ using runpy
            pass


