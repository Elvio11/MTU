import pytest
import asyncio
import os
import sys
import yaml
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

# Import all agents' main functions
from src.python.agents.anansi import main as anansi_main
from src.python.agents.cassandra import main as cassandra_main
from src.python.agents.dashboard_bridge import main as dashboard_bridge_main
from src.python.agents.heracles import main as heracles_main
from src.python.agents.hermes import main as hermes_main
from src.python.agents.hydra import main as hydra_main
from src.python.agents.ledger import main as ledger_main
from src.python.agents.nofx import main as nofx_main
from src.python.agents.oracle import main as oracle_main
from src.python.agents.portfolio_sizer import main as portfolio_sizer_main
from src.python.agents.telegram_bot_agent import main as telegram_bot_agent_main

AGENTS = [
    ("anansi", anansi_main, "AnansiAgent"),
    ("cassandra", cassandra_main, "CassandraAgent"),
    ("dashboard_bridge", dashboard_bridge_main, "DashboardBridge"),
    ("heracles", heracles_main, "HeraclesAgent"),
    ("hermes", hermes_main, "HermesAgent"),
    ("hydra", hydra_main, "HydraAgent"),
    ("ledger", ledger_main, "LedgerAgent"),
    ("nofx", nofx_main, "NofxAgent"),
    ("oracle", oracle_main, "OracleAgent"),
    ("portfolio_sizer", portfolio_sizer_main, "PortfolioSizerAgent"),
    ("telegram_bot_agent", telegram_bot_agent_main, None),
]

@pytest.mark.asyncio
@pytest.mark.parametrize("name, main_func, agent_class_name", AGENTS)
async def test_agent_main_success(name, main_func, agent_class_name):
    """Test successful main execution and keyboard interrupt."""
    config_data = "system:\n  environment: paper\n"
    m = mock_open(read_data=config_data)
    
    # Path to the specific agent module for patching
    patch_path = f"src.python.agents.{name}"
    
    with patch(f"{patch_path}.open", m), \
         patch(f"{patch_path}.validate_config", return_value=(True, None)), \
         patch("os.getenv", side_effect=lambda k, d=None: "mock_val" if "TELEGRAM" in k else d):
        
        if agent_class_name:
            with patch(f"{patch_path}.{agent_class_name}") as mock_agent_class:
                mock_agent_instance = mock_agent_class.return_value
                mock_agent_instance.run = AsyncMock(side_effect=KeyboardInterrupt())
                mock_agent_instance.stop = AsyncMock()
                await main_func()
                assert mock_agent_instance.run.called
                assert mock_agent_instance.stop.called
        else:
            # Special case for telegram_bot_agent
            with patch("src.python.shared.telegram_bot.create_bot") as mock_create_bot, \
                 patch("asyncio.Event.wait", side_effect=KeyboardInterrupt()):
                mock_bot = mock_create_bot.return_value
                mock_bot.initialize = AsyncMock()
                mock_bot.start = AsyncMock()
                mock_bot.stop = AsyncMock()
                
                await main_func()
                assert mock_bot.initialize.called
                assert mock_bot.start.called
                assert mock_bot.stop.called

@pytest.mark.asyncio
@pytest.mark.parametrize("name, main_func, _", AGENTS)
async def test_agent_main_config_not_found(name, main_func, _):
    """Test main failure when config file is missing."""
    patch_path = f"src.python.agents.{name}"
    
    with patch(f"{patch_path}.open", side_effect=FileNotFoundError("Missing config")), \
         patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        
        with pytest.raises(SystemExit) as exc:
            await main_func()
        assert exc.value.code == 1
        assert mock_exit.called

@pytest.mark.asyncio
@pytest.mark.parametrize("name, main_func, _", AGENTS)
async def test_agent_main_config_invalid(name, main_func, _):
    """Test main failure when configuration validation fails."""
    config_data = "invalid: config\n"
    m = mock_open(read_data=config_data)
    patch_path = f"src.python.agents.{name}"
    
    with patch(f"{patch_path}.open", m), \
         patch(f"{patch_path}.validate_config", return_value=(False, "Validation error")), \
         patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        
        with pytest.raises(SystemExit) as exc:
            await main_func()
        assert exc.value.code == 1
        assert mock_exit.called

@pytest.mark.asyncio
async def test_telegram_bot_agent_missing_env():
    """Test telegram_bot_agent failure when environment variables are missing."""
    patch_path = "src.python.agents.telegram_bot_agent"
    m = mock_open(read_data="{}")
    
    with patch(f"{patch_path}.open", m), \
         patch(f"{patch_path}.validate_config", return_value=(True, None)), \
         patch("os.getenv", return_value=None), \
         patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        
        with pytest.raises(SystemExit) as exc:
            await telegram_bot_agent_main()
        assert exc.value.code == 1
        assert mock_exit.called
