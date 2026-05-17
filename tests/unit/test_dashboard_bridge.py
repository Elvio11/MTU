import json
import asyncio
import pytest
import os
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.dashboard_bridge import DashboardBridge, main as bridge_main

CONFIG = {"system": {"environment": "paper"}}


@pytest.fixture
def bridge():
    b = DashboardBridge(CONFIG)
    b.redis = AsyncMock()
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.close = AsyncMock()
    b.redis.pubsub = MagicMock(return_value=mock_pubsub)
    b.pubsub = mock_pubsub
    return b


@pytest.mark.asyncio
async def test_bridge_handler_success(bridge):
    ws = MagicMock()
    ws.remote_address = "127.0.0.1:12345"

    # We need wait_closed to NOT complete immediately so we can check bridge.clients
    ev = asyncio.Event()

    async def mock_wait():
        await ev.wait()

    ws.wait_closed = mock_wait

    handler_task = asyncio.create_task(bridge.handler(ws))
    # Give it a moment to run up to await ws.wait_closed()
    await asyncio.sleep(0.01)

    assert ws in bridge.clients

    # Now trigger closure
    ev.set()
    await handler_task
    assert ws not in bridge.clients


@pytest.mark.asyncio
async def test_bridge_handler_exception(bridge):
    ws = AsyncMock()
    ws.wait_closed = AsyncMock(side_effect=Exception("disconnect"))
    await bridge.handler(ws)
    assert ws not in bridge.clients


@pytest.mark.asyncio
async def test_bridge_forward_redis_messages_success(bridge):
    bridge.running = True

    async def get_msg_side_effect(*args, **kwargs):
        if get_msg_side_effect.calls == 0:
            get_msg_side_effect.calls += 1
            return {
                "type": "message",
                "channel": "ch1",
                "data": json.dumps({"foo": "bar"}),
            }
        bridge.running = False
        return None

    get_msg_side_effect.calls = 0
    bridge.pubsub.get_message = AsyncMock(side_effect=get_msg_side_effect)

    client = AsyncMock()
    bridge.clients.add(client)

    with patch(
        "src.python.agents.dashboard_bridge.aioredis.from_url",
        AsyncMock(return_value=bridge.redis),
    ):
        await bridge.forward_redis_messages()

    assert client.send.called
    sent_data = json.loads(client.send.call_args[0][0])
    assert sent_data["type"] == "ch1"


@pytest.mark.asyncio
async def test_bridge_forward_redis_messages_json_error(bridge):
    bridge.running = True

    async def get_msg_side_effect(*args, **kwargs):
        if get_msg_side_effect.calls == 0:
            get_msg_side_effect.calls += 1
            return {"type": "message", "channel": "ch1", "data": "invalid-json"}
        bridge.running = False
        return None

    get_msg_side_effect.calls = 0
    bridge.pubsub.get_message = AsyncMock(side_effect=get_msg_side_effect)

    with patch(
        "src.python.agents.dashboard_bridge.aioredis.from_url",
        AsyncMock(return_value=bridge.redis),
    ):
        await bridge.forward_redis_messages()


@pytest.mark.asyncio
async def test_bridge_forward_redis_messages_send_error(bridge):
    bridge.running = True

    async def get_msg_side_effect(*args, **kwargs):
        if get_msg_side_effect.calls == 0:
            get_msg_side_effect.calls += 1
            return {"type": "message", "channel": "ch1", "data": "{}"}
        bridge.running = False
        return None

    get_msg_side_effect.calls = 0
    bridge.pubsub.get_message = AsyncMock(side_effect=get_msg_side_effect)

    client = AsyncMock()
    client.send = AsyncMock(side_effect=Exception("send fail"))
    bridge.clients.add(client)

    with patch(
        "src.python.agents.dashboard_bridge.aioredis.from_url",
        AsyncMock(return_value=bridge.redis),
    ):
        await bridge.forward_redis_messages()

    assert client not in bridge.clients

    assert client not in bridge.clients


@pytest.mark.asyncio
async def test_bridge_broadcast_system_stats_success(bridge):
    bridge.running = True
    bridge._get_db_metrics = MagicMock(return_value={
        "total_pnl": 1.0,
        "open_positions": 2,
        "win_rate": 75.0
    })
    
    bridge.redis.get = AsyncMock(return_value="0.1")
    client = AsyncMock()
    bridge.clients.add(client)

    call_count = 0

    async def sleep_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            bridge.running = False
        return None

    with patch("src.python.agents.dashboard_bridge.asyncio.sleep", side_effect=sleep_side_effect):
        await bridge.broadcast_system_stats()

    assert client.send.called
    sent_payload = json.loads(client.send.call_args[0][0])
    assert sent_payload["payload"]["metrics"]["total_pnl"] == 1.0
    assert sent_payload["payload"]["metrics"]["open_positions"] == 2


@pytest.mark.asyncio
async def test_bridge_broadcast_system_stats_no_clients(bridge):
    bridge.running = True
    bridge.clients = set()

    call_count = 0

    async def sleep_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        bridge.running = False
        return None

    with patch(
        "src.python.agents.dashboard_bridge.asyncio.sleep",
        side_effect=sleep_side_effect,
    ):
        await bridge.broadcast_system_stats()


@pytest.mark.asyncio
async def test_bridge_run(bridge):
    bridge.forward_redis_messages = AsyncMock()
    bridge.broadcast_system_stats = AsyncMock()

    with patch(
        "src.python.agents.dashboard_bridge.websockets.serve", return_value=AsyncMock()
    ) as mock_ws:
        # websockets.serve is an async context manager
        mock_ws.return_value.__aenter__.return_value = AsyncMock()
        await bridge.run()
        assert bridge.running is True


@pytest.mark.asyncio
async def test_bridge_stop(bridge):
    await bridge.stop()
    assert bridge.redis.close.called


@pytest.mark.asyncio
async def test_bridge_main_config_error():
    m = mock_open()
    with (
        patch("src.python.agents.dashboard_bridge.open", m),
        patch(
            "src.python.agents.dashboard_bridge.yaml.safe_load",
            side_effect=Exception("load error"),
        ),
        patch("sys.exit", side_effect=SystemExit(1)) as mock_exit,
    ):
        with pytest.raises(SystemExit):
            await bridge_main()


@pytest.mark.asyncio
async def test_bridge_main_keyboard_interrupt():
    m = mock_open(read_data="system: {environment: paper}")
    with (
        patch("src.python.agents.dashboard_bridge.open", m),
        patch(
            "src.python.agents.dashboard_bridge.validate_config",
            return_value=(True, ""),
        ),
        patch(
            "src.python.agents.dashboard_bridge.DashboardBridge.run",
            side_effect=KeyboardInterrupt,
        ),
        patch(
            "src.python.agents.dashboard_bridge.DashboardBridge.stop", return_value=None
        ) as mock_stop,
    ):
        await bridge_main()
        assert mock_stop.called


@pytest.mark.asyncio
async def test_bridge_main_validation_error():
    m = mock_open(read_data="system: {environment: paper}")
    with (
        patch("src.python.agents.dashboard_bridge.open", m),
        patch(
            "src.python.agents.dashboard_bridge.yaml.safe_load",
            return_value={"system": {}},
        ),
        patch(
            "src.python.agents.dashboard_bridge.validate_config",
            return_value=(False, "invalid"),
        ),
        patch("sys.exit", side_effect=SystemExit(1)) as mock_exit,
    ):
        from src.python.agents.dashboard_bridge import main as bridge_main

        with pytest.raises(SystemExit):
            await bridge_main()


@pytest.mark.asyncio
async def test_bridge_forward_redis_messages_error(bridge):
    bridge.running = True

    # Initial success then failure then stop
    async def get_msg_side_effect(*args, **kwargs):
        if get_msg_side_effect.calls == 0:
            get_msg_side_effect.calls += 1
            return {
                "type": "message",
                "channel": "ch1",
                "data": json.dumps({"foo": "bar"}),
            }
        if get_msg_side_effect.calls == 1:
            get_msg_side_effect.calls += 1
            return {
                "type": "message",
                "channel": "ch1",
                "data": json.dumps({"error": "trigger"}),
            }
        bridge.running = False
        return None

    get_msg_side_effect.calls = 0
    bridge.pubsub.get_message = AsyncMock(side_effect=get_msg_side_effect)

    # To trigger line 94, we need an exception inside the loop
    def mock_loads(s):
        if "trigger" in s:
            raise Exception("generic fail")
        return json.loads(s)

    with (
        patch("json.loads", side_effect=mock_loads),
        patch(
            "src.python.agents.dashboard_bridge.aioredis.from_url",
            AsyncMock(return_value=bridge.redis),
        ),
    ):
        await bridge.forward_redis_messages()


@pytest.mark.asyncio
async def test_bridge_broadcast_system_stats_errors(bridge):
    bridge.running = True
    bridge.redis.get = AsyncMock(side_effect=Exception("redis fail"))
    client = MagicMock()
    client.send = AsyncMock(side_effect=Exception("send fail"))
    bridge.clients.add(client)

    call_count = 0

    async def sleep_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        bridge.running = False
        return None

    with (
        patch(
            "src.python.agents.dashboard_bridge.get_connection",
            side_effect=Exception("db fail"),
        ),
        patch(
            "src.python.agents.dashboard_bridge.asyncio.sleep",
            side_effect=sleep_side_effect,
        ),
    ):
        await bridge.broadcast_system_stats()

    assert client not in bridge.clients


@pytest.mark.asyncio
async def test_bridge_forward_redis_messages_poll_error(bridge):
    bridge.running = True
    bridge.pubsub.get_message = AsyncMock(side_effect=[Exception("poll error"), None])

    async def stop_loop(*args, **kwargs):
        bridge.running = False
        return None

    with (
        patch(
            "src.python.agents.dashboard_bridge.aioredis.from_url",
            AsyncMock(return_value=bridge.redis),
        ),
        patch(
            "src.python.agents.dashboard_bridge.asyncio.sleep", side_effect=stop_loop
        ),
    ):
        await bridge.forward_redis_messages()


@pytest.mark.asyncio
async def test_bridge_broadcast_system_stats_loop_error(bridge):
    bridge.running = True
    bridge.clients.add(AsyncMock())
    with patch.object(
        bridge.api_manager, "get_stats", side_effect=Exception("broadcast fail")
    ):

        async def stop_loop(*args, **kwargs):
            bridge.running = False
            return None

        with patch(
            "src.python.agents.dashboard_bridge.asyncio.sleep", side_effect=stop_loop
        ):
            await bridge.broadcast_system_stats()


@pytest.mark.asyncio
async def test_bridge_main_full():
    m = mock_open(read_data="system: {environment: paper}")
    with (
        patch("src.python.agents.dashboard_bridge.open", m),
        patch(
            "src.python.agents.dashboard_bridge.validate_config",
            return_value=(True, ""),
        ),
        patch("src.python.agents.dashboard_bridge.DashboardBridge.run", AsyncMock()),
        patch("src.python.agents.dashboard_bridge.asyncio.run") as mock_run,
    ):
        from src.python.agents.dashboard_bridge import main as bridge_main

        # Test script execution path
        import src.python.agents.dashboard_bridge as db_mod

        with patch.object(db_mod, "__name__", "__main__"):
            # This triggers the if __name__ == "__main__": block
            # We can't easily re-import to trigger it, so we just call main()
            await bridge_main()
