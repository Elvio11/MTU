import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.python.shared.incident_response import IncidentResponse

@pytest.fixture
def ir():
    return IncidentResponse(telegram_token="test_token", admin_chat_id="test_chat")

@pytest.mark.asyncio
async def test_send_telegram_alert(ir):
    mock_resp = MagicMock()
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    
    with patch("aiohttp.ClientSession.get", return_value=mock_context) as mock_get:
        await ir.send_telegram_alert("test message")
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert kwargs["params"]["text"] == "[HIGH] test message"

@pytest.mark.asyncio
async def test_handle_p0_sniper_compromise(ir):
    with patch.object(ir, "send_telegram_alert", new_callable=AsyncMock) as mock_alert:
        incident = await ir.handle_p0_sniper_compromise("reason1", "wallet1")
        assert incident["type"] == "P0_SNIFFER_COMPROMISE"
        assert ir.emergency_mode is True
        mock_alert.assert_called_once()

@pytest.mark.asyncio
async def test_handle_p1_position_stuck(ir):
    with patch.object(ir, "send_telegram_alert", new_callable=AsyncMock) as mock_alert:
        incident = await ir.handle_p1_position_stuck("pos1", "reason1", "state1")
        assert incident["type"] == "P1_POSITION_STUCK"
        mock_alert.assert_called_once()

@pytest.mark.asyncio
async def test_handle_circuit_breaker_open(ir):
    with patch.object(ir, "send_telegram_alert", new_callable=AsyncMock) as mock_alert:
        await ir.handle_circuit_breaker_open("rpc1")
        mock_alert.assert_called_once()

@pytest.mark.asyncio
async def test_handle_high_slippage(ir):
    with patch.object(ir, "send_telegram_alert", new_callable=AsyncMock) as mock_alert:
        await ir.handle_high_slippage("pos1", 500, "token1")
        mock_alert.assert_called_once()

def test_incident_report(ir):
    ir.incident_log = [
        {"type": "P0_X"},
        {"type": "P1_Y"}
    ]
    ir.emergency_mode = True
    report = ir.get_incident_report()
    assert report["total_incidents"] == 2
    assert report["p0_count"] == 1
    assert report["p1_count"] == 1
    assert report["emergency_mode"] is True

def test_clear_emergency(ir):
    ir.emergency_mode = True
    ir.clear_emergency()
    assert ir.emergency_mode is False
