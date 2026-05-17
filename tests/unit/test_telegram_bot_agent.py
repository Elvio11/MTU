import pytest
import os
import sys
import json
import runpy
import yaml
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
import asyncio
import src.python.agents.telegram_bot_agent as telegram_agent

@pytest.mark.asyncio
async def test_telegram_bot_agent_main_success():
    """Test successful initialization and startup of the telegram bot agent."""
    with patch("os.getenv") as mock_getenv:
        def getenv_side_effect(key, default=None):
            if key == "TELEGRAM_BOT_TOKEN":
                return "fake_token_long_enough"
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
        
        mock_event_wait = AsyncMock(side_effect=KeyboardInterrupt)

        with patch("src.python.shared.telegram_bot.create_bot", return_value=mock_bot) as mock_create_bot:
            with patch("asyncio.Event.wait", mock_event_wait):
                await telegram_agent.main()

        mock_create_bot.assert_called_once_with("fake_token_long_enough", "123456", "fake_seed")
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

def test_telegram_bot_agent_main_entry_point():
    import runpy
    m = mock_open(read_data="system:\n  environment: paper\n")
    with patch("src.python.agents.telegram_bot_agent.open", m), \
         patch("src.python.agents.telegram_bot_agent.main", new_callable=AsyncMock), \
         patch("src.python.shared.config_validator.load_schema", return_value=({}, None)), \
         patch("asyncio.run"):
        try:
            runpy.run_module("src.python.agents.telegram_bot_agent", run_name="__main__")
        except SystemExit:
            pass

def test_telegram_bot_agent_main_entry_point_error_loading(capsys):
    import runpy
    import builtins
    original_open = builtins.open
    def mocked_open(file, *args, **kwargs):
        if str(file).endswith("config.yaml"):
            raise Exception("load error")
        return original_open(file, *args, **kwargs)
    
    with patch("builtins.open", side_effect=mocked_open):
        # Telegram bot agent handles config error by setting config to {} which then fails validation
        with pytest.raises(SystemExit):
            runpy.run_module("src.python.agents.telegram_bot_agent", run_name="__main__")
        captured = capsys.readouterr()
        assert "[CONFIG] Configuration validation failed" in captured.out

def test_telegram_bot_agent_main_entry_point_invalid_config(capsys):
    import runpy
    m = mock_open(read_data="invalid: yaml")
    with patch("src.python.agents.telegram_bot_agent.open", m), \
         patch("src.python.shared.config_validator.validate_config", return_value=(False, "validation error")):
        with pytest.raises(SystemExit):
            runpy.run_module("src.python.agents.telegram_bot_agent", run_name="__main__")
        captured = capsys.readouterr()
        assert "[CONFIG] Configuration validation failed: validation error" in captured.out
