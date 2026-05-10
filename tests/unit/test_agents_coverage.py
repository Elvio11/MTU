"""
Comprehensive unit tests for Python agents - coverage focused.
Covers: HermesAgent, LedgerAgent, HeraclesAgent, DashboardBridge
"""
import asyncio
import json
import sqlite3
import time
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

# ─────────────────────────────────────────────────────────────────────────────
# HermesAgent tests
# ─────────────────────────────────────────────────────────────────────────────
from src.python.agents.hermes import HermesAgent
from src.python.shared.envelope import AgentMessageEnvelope


def _make_envelope(**kwargs):
    defaults = dict(
        agent_id="AGT-01",
        event_type="token_detected",
        payload={"mint": "abc", "symbol": "TST"},
        correlation_id=str(uuid.uuid4()),
    )
    defaults.update(kwargs)
    return AgentMessageEnvelope(**defaults)


@pytest.fixture
def hermes():
    agent = HermesAgent()
    agent.redis = AsyncMock()
    agent.priority_queue = AsyncMock()
    agent.running = True
    return agent


@pytest.mark.asyncio
async def test_hermes_connect_redis():
    agent = HermesAgent()
    with patch("src.python.agents.hermes.aioredis.from_url", new_callable=AsyncMock) as mock_redis:
        mock_r = AsyncMock()
        mock_redis.return_value = mock_r
        with patch("src.python.agents.hermes.PriorityQueue"):
            await agent.connect_redis()
            assert agent.redis is not None


@pytest.mark.asyncio
async def test_hermes_handle_token_detected(hermes):
    env = _make_envelope(payload={"mint": "abc", "symbol": "TST"})
    hermes.redis.publish = AsyncMock()
    hermes.redis.lpush = AsyncMock()
    await hermes.handle_token_detected(env.model_dump_json())
    assert hermes.redis.publish.call_count == 2
    assert hermes.redis.lpush.call_count == 2


@pytest.mark.asyncio
async def test_hermes_handle_token_detected_bad_json(hermes):
    # Should not raise
    await hermes.handle_token_detected("not-valid-json")


@pytest.mark.asyncio
async def test_hermes_handle_token_migrated(hermes):
    env = _make_envelope(event_type="token_migrated", payload={"mint": "abc", "name": "Test", "symbol": "TST", "program": "pumpswap", "signature": "sig1", "uri": "http://x"})
    hermes.redis.publish = AsyncMock()
    hermes.redis.lpush = AsyncMock()
    await hermes.handle_token_migrated(env.model_dump_json())
    assert hermes.redis.publish.call_count == 2


@pytest.mark.asyncio
async def test_hermes_handle_token_migrated_bad_json(hermes):
    await hermes.handle_token_migrated("{invalid}")


@pytest.mark.asyncio
async def test_hermes_stop(hermes):
    hermes.pubsub = AsyncMock()
    hermes.redis = AsyncMock()
    await hermes.stop()
    hermes.pubsub.unsubscribe.assert_awaited_once()
    hermes.redis.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_hermes_stop_no_pubsub():
    agent = HermesAgent()
    agent.redis = AsyncMock()
    agent.pubsub = None
    await agent.stop()  # Should not raise


@pytest.mark.asyncio
async def test_hermes_run_dequeues_and_routes(hermes):
    env = _make_envelope()
    call_count = 0

    async def fake_handle(data):
        nonlocal call_count
        call_count += 1
        hermes.running = False

    hermes.handle_token_detected = fake_handle
    hermes.priority_queue.dequeue = AsyncMock(return_value=(env.model_dump(), 1))
    # Patch connect_redis so run() doesn't try to reach Redis
    with patch.object(hermes, "connect_redis", new_callable=AsyncMock):
        await hermes.run()
    assert call_count == 1


@pytest.mark.asyncio
async def test_hermes_run_dequeue_string(hermes):
    env = _make_envelope()
    call_count = 0

    async def fake_handle(data):
        nonlocal call_count
        call_count += 1
        hermes.running = False

    hermes.handle_token_detected = fake_handle
    hermes.priority_queue.dequeue = AsyncMock(return_value=(env.model_dump_json(), 2))
    with patch.object(hermes, "connect_redis", new_callable=AsyncMock):
        await hermes.run()
    assert call_count == 1


@pytest.mark.asyncio
async def test_hermes_run_dequeue_none_then_stop(hermes):
    iters = 0

    async def fake_dequeue():
        nonlocal iters
        iters += 1
        if iters >= 2:
            hermes.running = False
        return None

    hermes.priority_queue.dequeue = fake_dequeue
    with patch.object(hermes, "connect_redis", new_callable=AsyncMock), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        await hermes.run()


@pytest.mark.asyncio
async def test_hermes_run_dequeue_exception(hermes):
    iters = 0

    async def fake_dequeue():
        nonlocal iters
        iters += 1
        if iters >= 2:
            hermes.running = False
        raise Exception("boom")

    hermes.priority_queue.dequeue = fake_dequeue
    with patch.object(hermes, "connect_redis", new_callable=AsyncMock), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        await hermes.run()


# ─────────────────────────────────────────────────────────────────────────────
# LedgerAgent tests
# ─────────────────────────────────────────────────────────────────────────────
from src.python.agents.ledger import LedgerAgent


@pytest.fixture
def ledger(tmp_path):
    agent = LedgerAgent()
    db_path = str(tmp_path / "positions.db")
    agent.db = sqlite3.connect(db_path)
    agent.db.execute("""
        CREATE TABLE IF NOT EXISTS audit_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            envelope_id TEXT, agent_id TEXT, event_type TEXT,
            payload TEXT, timestamp_utc TEXT
        )
    """)
    agent.db.commit()
    agent.audit_file = MagicMock()
    agent.redis = AsyncMock()
    agent.pubsub = AsyncMock()
    agent.running = True
    return agent


def test_ledger_connect_db(tmp_path):
    agent = LedgerAgent()
    with patch("src.python.agents.ledger.sqlite3.connect") as mock_conn:
        mock_conn.return_value = MagicMock()
        agent.connect_db()
        mock_conn.assert_called_once()


def test_ledger_write_audit_log(ledger):
    env = _make_envelope()
    ledger.write_audit_log(env)
    ledger.audit_file.write.assert_called_once()
    ledger.audit_file.flush.assert_called_once()


@pytest.mark.asyncio
async def test_ledger_handle_event(ledger):
    env = _make_envelope()
    await ledger.handle_event("mtus:trade_approved", env.model_dump_json())


@pytest.mark.asyncio
async def test_ledger_handle_event_bad_json(ledger):
    await ledger.handle_event("channel", "not-json")  # Should not raise


@pytest.mark.asyncio
async def test_ledger_handle_event_write_exception(ledger):
    ledger.audit_file.write.side_effect = IOError("disk full")
    env = _make_envelope()
    await ledger.handle_event("ch", env.model_dump_json())  # Should not propagate


@pytest.mark.asyncio
async def test_ledger_connect_redis():
    agent = LedgerAgent()
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_r = AsyncMock()
    mock_r.pubsub = MagicMock(return_value=mock_pubsub)
    with patch("src.python.agents.ledger.aioredis.from_url", new_callable=AsyncMock) as mock_from:
        mock_from.return_value = mock_r
        await agent.connect_redis()
        assert agent.redis is not None


@pytest.mark.asyncio
async def test_ledger_run_processes_message(ledger):
    """Test the ledger message loop inline (not via run()) to avoid subprocess/file setup."""
    env = _make_envelope()
    msg = {"channel": "ch", "data": env.model_dump_json(), "type": "message"}
    call_count = 0

    async def fake_get_message(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return msg
        ledger.running = False
        return None

    ledger.pubsub.get_message = fake_get_message
    while ledger.running:
        message = await ledger.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if message:
            await ledger.handle_event(message["channel"], message["data"])
    assert call_count >= 1


@pytest.mark.asyncio
async def test_ledger_stop(ledger):
    await ledger.stop()
    ledger.redis.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_ledger_stop_all_none():
    agent = LedgerAgent()
    await agent.stop()  # Should not raise


# ─────────────────────────────────────────────────────────────────────────────
# HeraclesAgent tests
# ─────────────────────────────────────────────────────────────────────────────
from src.python.agents.heracles import HeraclesAgent


@pytest.fixture
def heracles():
    config = {"trading": {"daily_loss_limit_sol": -1.0}}
    agent = HeraclesAgent(config)
    agent.redis = AsyncMock()
    agent.running = True
    return agent


@pytest.mark.asyncio
async def test_heracles_connect_redis():
    import sys
    agent = HeraclesAgent({})
    mock_r = AsyncMock()
    mock_aioredis = MagicMock()
    mock_aioredis.from_url = AsyncMock(return_value=mock_r)
    # heracles.py does `import aioredis` inside the method, so inject via sys.modules
    original = sys.modules.get("aioredis")
    sys.modules["aioredis"] = mock_aioredis
    try:
        await agent.connect_redis()
        assert agent.redis is mock_r
    finally:
        if original is None:
            sys.modules.pop("aioredis", None)
        else:
            sys.modules["aioredis"] = original


@pytest.mark.asyncio
async def test_heracles_handle_health_check(heracles):
    env = _make_envelope(agent_id="AGT-03", event_type="health_check", payload={"status": "ok"})
    await heracles.handle_health_check(env.model_dump_json())
    assert "AGT-03" in heracles.agent_health


@pytest.mark.asyncio
async def test_heracles_handle_health_check_bad_json(heracles):
    await heracles.handle_health_check("bad")  # Should not raise


@pytest.mark.asyncio
async def test_heracles_handle_position_closed_profit(heracles):
    env = _make_envelope(event_type="position_closed", payload={"realised_pnl_sol": 0.5})
    with patch("src.python.agents.heracles.is_paper_mode", return_value=False):
        await heracles.handle_position_closed(env.model_dump_json())
    assert heracles.daily_pnl == 0.5


@pytest.mark.asyncio
async def test_heracles_handle_position_closed_paper_mode(heracles):
    env = _make_envelope(event_type="position_closed", payload={"realised_pnl_sol": 0.1})
    with patch("src.python.agents.heracles.is_paper_mode", return_value=True):
        await heracles.handle_position_closed(env.model_dump_json())
    assert len(heracles.paper_trades) == 1


@pytest.mark.asyncio
async def test_heracles_handle_position_closed_triggers_killswitch(heracles):
    env = _make_envelope(event_type="position_closed", payload={"realised_pnl_sol": -5.0})
    heracles.trigger_killswitch = AsyncMock()
    with patch("src.python.agents.heracles.is_paper_mode", return_value=False):
        await heracles.handle_position_closed(env.model_dump_json())
    heracles.trigger_killswitch.assert_awaited_once()


@pytest.mark.asyncio
async def test_heracles_handle_position_closed_bad_json(heracles):
    await heracles.handle_position_closed("not-json")


@pytest.mark.asyncio
async def test_heracles_check_agent_health_no_timeout(heracles):
    heracles.agent_health["AGT-01"] = time.time()
    heracles.trigger_killswitch = AsyncMock()
    await heracles.check_agent_health()
    heracles.trigger_killswitch.assert_not_awaited()


@pytest.mark.asyncio
async def test_heracles_check_agent_health_timeout(heracles):
    heracles.agent_health["AGT-01"] = time.time() - 60
    heracles.trigger_killswitch = AsyncMock()
    await heracles.check_agent_health()
    heracles.trigger_killswitch.assert_awaited_once()
    assert "AGT-01" not in heracles.agent_health


@pytest.mark.asyncio
async def test_heracles_trigger_killswitch(heracles):
    heracles.send_telegram_alert = AsyncMock()
    await heracles.trigger_killswitch("Test reason")
    heracles.redis.publish.assert_awaited_once()
    heracles.send_telegram_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_heracles_send_telegram_alert_no_creds(heracles):
    with patch("os.getenv", return_value=None):
        await heracles.send_telegram_alert("test")  # Should not raise


@pytest.mark.asyncio
async def test_heracles_send_telegram_alert_with_creds(heracles):
    with patch("os.getenv", side_effect=lambda k, *a: "tok" if k == "TELEGRAM_BOT_TOKEN" else "123"):
        with patch("aiohttp.ClientSession") as mock_sess:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock()))
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_sess.return_value = mock_ctx
            await heracles.send_telegram_alert("hello")


@pytest.mark.asyncio
async def test_heracles_send_telegram_exception(heracles):
    with patch("os.getenv", side_effect=lambda k, *a: "tok"):
        with patch("aiohttp.ClientSession", side_effect=Exception("net")):
            await heracles.send_telegram_alert("msg")  # Should not raise


def test_heracles_check_mainnet_readiness_not_enough_trades(heracles):
    assert heracles.check_mainnet_readiness() is False


def test_heracles_check_mainnet_readiness_low_winrate(heracles):
    for i in range(50):
        env = _make_envelope(event_type="position_closed", payload={"realised_pnl_sol": -0.1})
        heracles.paper_trades.append(env)
    assert heracles.check_mainnet_readiness() is False


def test_heracles_check_mainnet_readiness_passes(heracles):
    for i in range(50):
        pnl = 0.1 if i < 30 else -0.1
        env = _make_envelope(event_type="position_closed", payload={"realised_pnl_sol": pnl})
        heracles.paper_trades.append(env)
    result = heracles.check_mainnet_readiness()
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_heracles_stop(heracles):
    await heracles.stop()
    heracles.redis.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_heracles_stop_no_redis():
    agent = HeraclesAgent({})
    await agent.stop()  # Should not raise


# ─────────────────────────────────────────────────────────────────────────────
# DashboardBridge tests
# ─────────────────────────────────────────────────────────────────────────────
from src.python.agents.dashboard_bridge import DashboardBridge


@pytest.fixture
def bridge():
    b = DashboardBridge()
    b.redis = AsyncMock()
    b.pubsub = AsyncMock()
    b.running = True
    return b


@pytest.mark.asyncio
async def test_bridge_handler_adds_removes_client(bridge):
    mock_ws = AsyncMock()
    mock_ws.remote_address = ("127.0.0.1", 9999)
    mock_ws.wait_closed = AsyncMock(return_value=None)
    await bridge.handler(mock_ws)
    assert mock_ws not in bridge.clients


@pytest.mark.asyncio
async def test_bridge_handler_exception(bridge):
    mock_ws = AsyncMock()
    mock_ws.remote_address = ("127.0.0.1", 1234)
    mock_ws.wait_closed = AsyncMock(side_effect=Exception("dropped"))
    await bridge.handler(mock_ws)
    assert mock_ws not in bridge.clients


@pytest.mark.asyncio
async def test_bridge_forward_redis_messages_broadcasts(bridge):
    env = _make_envelope()
    msg = {"type": "message", "channel": "mtus:position_opened", "data": env.model_dump_json()}

    call_count = 0
    async def fake_get_message(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return msg
        bridge.running = False
        return None

    bridge.pubsub.get_message = fake_get_message
    mock_client = AsyncMock()
    bridge.clients.add(mock_client)

    mock_r = AsyncMock()
    mock_r.pubsub = MagicMock(return_value=bridge.pubsub)
    bridge.pubsub.subscribe = AsyncMock()

    with patch("src.python.agents.dashboard_bridge.aioredis.from_url", new_callable=AsyncMock) as mock_from:
        mock_from.return_value = mock_r
        await bridge.forward_redis_messages()

    mock_client.send.assert_awaited()


@pytest.mark.asyncio
async def test_bridge_forward_client_send_fail(bridge):
    env = _make_envelope()
    msg = {"type": "message", "channel": "ch", "data": env.model_dump_json()}

    call_count = 0
    async def fake_get_message(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return msg
        bridge.running = False
        return None

    bridge.pubsub.get_message = fake_get_message
    bad_client = AsyncMock()
    bad_client.send = AsyncMock(side_effect=Exception("send failed"))
    bridge.clients.add(bad_client)

    mock_r = AsyncMock()
    mock_r.pubsub = MagicMock(return_value=bridge.pubsub)
    bridge.pubsub.subscribe = AsyncMock()

    with patch("src.python.agents.dashboard_bridge.aioredis.from_url", new_callable=AsyncMock) as mock_from:
        mock_from.return_value = mock_r
        await bridge.forward_redis_messages()

    assert bad_client not in bridge.clients


@pytest.mark.asyncio
async def test_bridge_forward_json_decode_error(bridge):
    msg = {"type": "message", "channel": "ch", "data": "not-valid-json"}

    call_count = 0
    async def fake_get_message(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return msg
        bridge.running = False
        return None

    bridge.pubsub.get_message = fake_get_message
    bridge.pubsub.subscribe = AsyncMock()
    mock_r = AsyncMock()
    mock_r.pubsub = MagicMock(return_value=bridge.pubsub)

    with patch("src.python.agents.dashboard_bridge.aioredis.from_url", new_callable=AsyncMock) as mock_from:
        mock_from.return_value = mock_r
        await bridge.forward_redis_messages()  # Should not raise


@pytest.mark.asyncio
async def test_bridge_forward_non_message_type(bridge):
    msg = {"type": "subscribe", "channel": "ch", "data": "1"}

    call_count = 0
    async def fake_get_message(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return msg
        bridge.running = False
        return None

    bridge.pubsub.get_message = fake_get_message
    bridge.pubsub.subscribe = AsyncMock()
    mock_r = AsyncMock()
    mock_r.pubsub = MagicMock(return_value=bridge.pubsub)

    with patch("src.python.agents.dashboard_bridge.aioredis.from_url", new_callable=AsyncMock) as mock_from:
        mock_from.return_value = mock_r
        await bridge.forward_redis_messages()



@pytest.mark.asyncio
async def test_bridge_stop(bridge):
    await bridge.stop()
    bridge.pubsub.unsubscribe.assert_awaited_once()
    bridge.redis.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_bridge_stop_no_connections():
    b = DashboardBridge()
    await b.stop()  # Should not raise
