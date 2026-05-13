import pytest
import os
from unittest.mock import patch
from src.python.shared.notification_templates import NotificationTemplates, add_environment_tag

def test_add_environment_tag():
    with patch("src.python.shared.notification_templates.MTUS_ENVIRONMENT", "paper"):
        assert add_environment_tag("test") == "[PAPER] test"
    with patch("src.python.shared.notification_templates.MTUS_ENVIRONMENT", "prod"):
        assert add_environment_tag("test") == "test"

def test_token_qualified():
    token = {"name": "TestToken", "symbol": "TT", "mint": "1234567890", "market_cap": 1000.50, "rugcheck_score": "Good"}
    result = NotificationTemplates.token_qualified(token)
    assert "✅ <b>Token Qualified</b>" in result
    assert "TestToken" in result
    assert "TT" in result
    assert "12345678" in result # truncated mint
    assert "$1000.50" in result
    assert "Good" in result

def test_trade_opened():
    result = NotificationTemplates.trade_opened("id1", "token1", 0.5, 1.23)
    assert "📈 <b>Position Opened</b>" in result
    assert "id1" in result
    assert "0.500 SOL" in result
    assert "1.230000" in result

def test_tp1_hit():
    result = NotificationTemplates.tp1_hit("id1", "token1", 0.1)
    assert "🎯 <b>TP1 Hit!</b>" in result
    assert "+0.100 SOL" in result

def test_tp2_hit():
    result = NotificationTemplates.tp2_hit("id1", "token1", 0.2)
    assert "🎯 <b>TP2 Hit!</b>" in result
    assert "+0.200 SOL" in result

def test_stop_loss():
    result = NotificationTemplates.stop_loss("id1", "token1", -0.1)
    assert "🛑 <b>Stop Loss</b>" in result
    assert "-0.100 SOL" in result

def test_daily_summary():
    result = NotificationTemplates.daily_summary(10, 6, 0.5, "PROD")
    assert "📊 <b>Daily Summary [PROD]</b>" in result
    assert "6 (60.0%)" in result
    assert "+0.5000 SOL" in result

def test_system_alert():
    result = NotificationTemplates.system_alert("CRITICAL", "Danger!")
    assert "🚨 <b>System Alert: CRITICAL</b>" in result
    assert "Danger!" in result

def test_agent_status():
    result = NotificationTemplates.agent_status("agent1", "healthy", "Working fine")
    assert "🤖 <b>Agent Status</b>" in result
    assert "✅ agent1: healthy" in result
    assert "Working fine" in result

def test_price_alert():
    result = NotificationTemplates.price_alert("token1", 10.5, 15.0)
    assert "🚀 <b>Price Alert</b>" in result
    assert "+15.0%" in result

def test_position_closed():
    result = NotificationTemplates.position_closed("id1", "token1", 0.1, "TP2", "PAPER")
    assert "✅ <b>Position Closed [PAPER]</b>" in result
    assert "id1" in result
    assert "+0.1000 SOL" in result
    assert "TP2" in result
