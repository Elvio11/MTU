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
    assert "🟢 <b>TOKEN QUALIFIED</b>" in result
    assert "TestToken" in result
    assert "TT" in result
    assert "1234567890" in result
    assert "$1,000.50" in result
    assert "Good" in result

def test_trade_opened():
    result = NotificationTemplates.trade_opened("id1", "token1", 0.5, 1.23)
    assert "🚀 <b>POSITION OPENED</b>" in result
    assert "id1" in result
    assert "0.5000 SOL" in result
    assert "1.230000" in result

def test_tp1_hit():
    result = NotificationTemplates.tp1_hit("id1", "token1", 0.1)
    assert "🎯 <b>TAKE PROFIT 1 HIT</b>" in result
    assert "+0.1000 SOL" in result

def test_tp2_hit():
    result = NotificationTemplates.tp2_hit("id1", "token1", 0.2)
    assert "🏆 <b>TAKE PROFIT 2 HIT (EXIT)</b>" in result
    assert "+0.2000 SOL" in result

def test_stop_loss():
    result = NotificationTemplates.stop_loss("id1", "token1", -0.1)
    assert "🛑 <b>STOP LOSS TRIGGERED</b>" in result
    assert "-0.1000 SOL" in result

def test_daily_summary():
    result = NotificationTemplates.daily_summary(10, 6, 0.5, "PROD")
    assert "📊 <b>DAILY TRADING SUMMARY</b>" in result
    assert "Win Rate:" in result
    assert "60.0%" in result
    assert "+0.5000 SOL" in result

def test_system_alert():
    result = NotificationTemplates.system_alert("CRITICAL", "Danger!")
    assert "🚨 <b>SYSTEM ALERT: CRITICAL</b>" in result
    assert "Danger!" in result

def test_agent_status():
    result = NotificationTemplates.agent_status("agent1", "healthy", "Working fine")
    assert "🤖 <b>AGENT STATUS SUMMARY</b>" in result
    assert "HEALTHY" in result
    assert "Working fine" in result

def test_price_alert():
    result = NotificationTemplates.price_alert("token1", 10.5, 15.0)
    assert "PRICE MOVEMENT ALERT" in result
    assert "+15.0%" in result

def test_position_closed():
    result = NotificationTemplates.position_closed("id1", "token1", 0.1, "TP2", "PAPER")
    assert "POSITION CLOSED [PAPER]" in result
    assert "id1" in result
    assert "+0.1000 SOL" in result
    assert "TP2" in result

def test_trade_failed():
    # Without token details
    result = NotificationTemplates.trade_failed("mint123", "Insufficient balance")
    assert "❌ <b>TRADE SKIPPED/FAILED</b>" in result
    assert "mint123" in result
    assert "Insufficient balance" in result
    assert "Waiting for the next setup" in result

    # With token details
    token_details = {
        "name": "SuperCoin",
        "symbol": "SUP",
        "market_cap": 150000.50,
        "volume_24h": 5000.00
    }
    result_with_details = NotificationTemplates.trade_failed("mint123", "Failed gates", token_details)
    assert "❌ <b>TRADE SKIPPED/FAILED</b>" in result_with_details
    assert "SuperCoin" in result_with_details
    assert "SUP" in result_with_details
    assert "$150,000.50" in result_with_details
    assert "$5,000.00" in result_with_details
    assert "Failed gates" in result_with_details
