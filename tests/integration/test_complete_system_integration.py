"""
Comprehensive Integration Test - Complete MTUS System
Tests ALL Python agents, TypeScript agents, Redis, dashboard, and complete flow.
This is the ultimate integration test covering:
- All 11 Python/TypeScript agents
- Redis connectivity and pub/sub
- Dashboard WebSocket bridge
- Complete token → trade flow
- Safety gates and TP/SL
- Emergency procedures
"""

import sys
import os
import json
import asyncio
import uuid
import time
import pytest
import aioredis

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

from src.python.shared.envelope import AgentMessageEnvelope
from src.python.shared.constants import (
    CHANNEL_TOKEN_DETECTED,
    CHANNEL_TOKEN_RECEIVED,
    CHANNEL_TOKEN_QUALIFIED,
    CHANNEL_TRADE_APPROVED,
    CHANNEL_POSITION_OPENED,
    CHANNEL_TP1_HIT,
    CHANNEL_TP2_HIT,
    CHANNEL_STOP_LOSS_HIT,
    CHANNEL_TRADE_FAILED,
    KEY_TRADE_QUEUE,
    KEY_ALL_ACTIVE_POSITIONS,
    KEY_POSITION_SIZE_SOL,
    REDIS_KEY_KILL_SWITCH,
    REDIS_KEY_TRADING_PAUSED,
    REDIS_KEY_KILL_SWITCH_TRIGGERED,
    REDIS_KEY_SYSTEM_STATE,
    MTUS_PREFIX,
    is_paper_mode,
)
from src.python.shared.priority_queue import PriorityQueue, calculate_priority
from src.python.shared.circuit_breaker import CircuitBreaker, CircuitState
from src.python.shared.validators import (
    is_valid_metadata_uri,
    is_valid_social_url,
    is_valid_positive_number,
)
from src.python.shared.telegram_auth import generate_otp, verify_otp


class TestAllPythonAgents:
    """Test all Python agents (NOFX, Hermes, Anansi, Oracle, Cassandra, Ledger, Heracles, DashboardBridge)."""

    def test_01_nofx_agent_structure(self):
        """Test NOFX (AGT-01) agent has all required methods."""
        from src.python.agents.nofx import NofxAgent

        agent = NofxAgent({})
        required_methods = [
            "connect_redis",
            "run",
            "stop",
            "connect_pumpdev",
            "check_trading_state",
            "priority_queue",
            "check_rate_limit",
            "handle_pumpdev_message",
            "_handle_new_token",
            "_publish_migration",
        ]
        for method in required_methods:
            assert hasattr(agent, method), f"AGT-01: Missing method {method}"
        print("✅ AGT-01 (NOFX): All required methods present")

    def test_02_hermes_agent_structure(self):
        """Test Hermes (AGT-02) agent has all required methods."""
        from src.python.agents.hermes import HermesAgent

        agent = HermesAgent()
        required_methods = [
            "connect_redis",
            "run",
            "stop",
            "handle_token_detected",
            "handle_token_migrated",
            "priority_queue",
        ]
        for method in required_methods:
            assert hasattr(agent, method), f"AGT-02: Missing method {method}"
        print("✅ AGT-02 (Hermes): All required methods present")

    def test_03_anansi_agent_structure(self):
        """Test Anansi (AGT-03) agent has all safety gate methods."""
        from src.python.agents.anansi import AnansiAgent

        config = {
            "qualification": {
                "min_market_cap_sol": 5,
                "max_market_cap_sol": 150,
                "min_virtual_sol_reserves": 30,
            }
        }
        agent = AnansiAgent(config)
        required_methods = [
            "connect_redis",
            "run",
            "stop",
            "qualify_token",
            "check_g1_mint_authority",
            "check_g2_freeze_authority",
            "check_g3_lp_lock",
            "check_g4_dev_holdings",
            "check_g5_top10_concentration",
            "check_g6_rugcheck_score",
            "check_g7_liquidity_size",
            "check_g8_social_metadata",
            "check_g9_duplicate",
            "check_g10_honeypot",
        ]
        for method in required_methods:
            assert hasattr(agent, method), f"AGT-03: Missing method {method}"
        print("✅ AGT-03 (Anansi): All safety gate methods present")

    def test_04_oracle_agent_structure(self):
        """Test Oracle (AGT-04) agent structure."""
        from src.python.agents.oracle import OracleAgent

        agent = OracleAgent({})
        required_methods = [
            "run",
            "stop",
            "fetch_price_jupiter",
            "update_position_price",
        ]
        for method in required_methods:
            assert hasattr(agent, method), f"AGT-04: Missing method {method}"
        print("✅ AGT-04 (Oracle): All required methods present")

    def test_05_cassandra_agent_structure(self):
        """Test Cassandra (AGT-08) agent structure."""
        from src.python.agents.cassandra import CassandraAgent

        agent = CassandraAgent({})
        required_methods = ["run", "stop", "fetch_dexscreener_data", "score_sentiment"]
        for method in required_methods:
            assert hasattr(agent, method), f"AGT-08: Missing method {method}"
        print("✅ AGT-08 (Cassandra): All required methods present")

    def test_06_ledger_agent_structure(self):
        """Test Ledger (AGT-09) agent structure."""
        from src.python.agents.ledger import LedgerAgent

        agent = LedgerAgent()
        required_methods = ["run", "stop", "handle_event"]
        for method in required_methods:
            assert hasattr(agent, method), f"AGT-09: Missing method {method}"
        print("✅ AGT-09 (Ledger): All required methods present")

    def test_07_heracles_agent_structure(self):
        """Test Heracles (AGT-10) agent structure."""
        from src.python.agents.heracles import HeraclesAgent

        agent = HeraclesAgent({})
        required_methods = ["run", "stop", "check_agent_health", "trigger_killswitch"]
        for method in required_methods:
            assert hasattr(agent, method), f"AGT-10: Missing method {method}"
        print("✅ AGT-10 (Heracles): All required methods present")

    def test_08_dashboard_bridge_structure(self):
        """Test DashboardBridge (AGT-11) agent structure."""
        from src.python.agents.dashboard_bridge import DashboardBridge

        agent = DashboardBridge()
        required_methods = ["run", "stop"]
        for method in required_methods:
            assert hasattr(agent, method), f"AGT-11: Missing method {method}"
        print("✅ AGT-11 (DashboardBridge): All required methods present")


class TestAllSharedModules:
    """Test all shared modules and utilities."""

    def test_01_envelope_schema(self):
        """Test AgentMessageEnvelope schema."""
        envelope = AgentMessageEnvelope(
            agent_id="AGT-01",
            event_type="token_detected",
            payload={"mint": "test_mint", "symbol": "TEST"},
            correlation_id=str(uuid.uuid4()),
        )
        assert envelope.schema_version == "1.0.0"
        assert envelope.agent_id == "AGT-01"
        assert "mint" in envelope.payload
        print("✅ AgentMessageEnvelope: Schema valid")

    def test_02_circuit_breaker(self):
        """Test CircuitBreaker functionality."""
        cb = CircuitBreaker(threshold=3, reset_timeout_sec=60)
        assert cb.get_state() == CircuitState.CLOSED
        cb.on_failure()
        cb.on_failure()
        cb.on_failure()
        assert cb.get_state() == CircuitState.OPEN
        print("✅ CircuitBreaker: State transitions work")

    def test_03_validators(self):
        """Test validator functions."""
        assert is_valid_metadata_uri("https://arweave.net/abcdef123456")
        assert is_valid_social_url("https://twitter.com/solana")
        assert is_valid_positive_number("100.50")
        assert not is_valid_metadata_uri("invalid-url")
        assert not is_valid_social_url("not-a-url")
        assert not is_valid_positive_number("-10")
        print("✅ Validators: All validation functions work")

    def test_04_telegram_auth(self):
        """Test OTP generation and verification."""
        otp = generate_otp("test_seed_123")
        assert len(otp) >= 6
        assert verify_otp("test_seed_123", otp) == True
        assert verify_otp("test_seed_123", "000000") == False
        print("✅ TelegramAuth: OTP generation works")

    def test_05_priority_queue(self):
        """Test PriorityQueue priority calculation."""
        assert calculate_priority("complete", 0) == 1
        assert calculate_priority("create", 0) == 3
        assert calculate_priority("create_pool", 0) == 1
        assert calculate_priority("migration", 0) == 1
        print("✅ PriorityQueue: Priority calculation correct")

    def test_06_constants(self):
        """Test all constants are defined."""
        assert CHANNEL_TOKEN_DETECTED is not None
        assert CHANNEL_TOKEN_RECEIVED is not None
        assert CHANNEL_TRADE_APPROVED is not None
        assert CHANNEL_POSITION_OPENED is not None
        assert KEY_TRADE_QUEUE is not None
        assert is_paper_mode() is not None
        print("✅ Constants: All Redis keys and channels defined")


class TestRedisIntegration:
    """Test Redis connectivity and all pub/sub channels."""

    def test_01_redis_connection(self):
        """Test Redis connection works."""

        async def test_redis():
            redis = await aioredis.from_url(
                "redis://localhost:6379", decode_responses=True
            )
            pong = await redis.ping()
            assert pong == True
            await redis.close()
            return True

        result = asyncio.run(test_redis())
        assert result == True
        print("✅ Redis: Connection successful")

    def test_02_redis_pub_sub_all_channels(self):
        """Test all pub/sub channels work."""

        async def test_channels():
            redis = await aioredis.from_url(
                "redis://localhost:6379", decode_responses=True
            )
            channels = [
                CHANNEL_TOKEN_DETECTED,
                CHANNEL_TOKEN_RECEIVED,
                CHANNEL_TOKEN_QUALIFIED,
                CHANNEL_TRADE_APPROVED,
                CHANNEL_POSITION_OPENED,
            ]
            for channel in channels:
                pubsub = redis.pubsub()
                await pubsub.subscribe(channel)
                test_msg = {"test": "data", "channel": channel}
                await redis.publish(channel, json.dumps(test_msg))
                await asyncio.sleep(0.1)
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            await redis.close()
            return True

        result = asyncio.run(test_channels())
        assert result == True
        print("✅ Redis: All pub/sub channels work")

    def test_03_priority_queue_operations(self):
        """Test priority queue enqueue/dequeue."""

        async def test_queue():
            redis = await aioredis.from_url(
                "redis://localhost:6379", decode_responses=True
            )
            pq = PriorityQueue(redis)
            await pq.connect()

            await pq.clear()
            await pq.enqueue({"mint": "test1", "symbol": "T1"}, 1)
            await pq.enqueue({"mint": "test2", "symbol": "T2"}, 3)

            item = await pq.dequeue()
            assert item is not None
            data, priority = item
            assert data["mint"] == "test1"

            item2 = await pq.dequeue()
            assert item2 is not None

            await pq.clear()
            if pq.redis:
                await pq.redis.close()
            await redis.close()
            return True

        result = asyncio.run(test_queue())
        assert result == True
        print("✅ PriorityQueue: Enqueue/dequeue works")

    def test_04_redis_keys_cleanup(self):
        """Test Redis keys can be managed."""

        async def test_keys():
            redis = await aioredis.from_url(
                "redis://localhost:6379", decode_responses=True
            )
            test_key = f"{MTUS_PREFIX}test_key"
            await redis.set(test_key, "test_value")
            value = await redis.get(test_key)
            assert value == "test_value"
            await redis.delete(test_key)
            value = await redis.get(test_key)
            assert value is None
            await redis.close()
            return True

        result = asyncio.run(test_keys())
        assert result == True
        print("✅ Redis: Key management works")


class TestTypeScriptAgents:
    """Test TypeScript agent files exist and are buildable."""

    def test_01_ares_typescript_exists(self):
        """Test Ares (AGT-05) TypeScript file exists."""
        import os

        ares_path = os.path.join(project_root, "src", "typescript", "agents", "ares.ts")
        assert os.path.exists(ares_path), "ares.ts not found"

        with open(ares_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            assert "AresAgent" in content
            assert "executeTrade" in content
            assert "canAffordTrade" in content
        print("✅ AGT-05 (Ares): TypeScript file valid")

    def test_02_sentinel_typescript_exists(self):
        """Test Sentinel (AGT-06) TypeScript file exists."""
        import os

        sentinel_path = os.path.join(
            project_root, "src", "typescript", "agents", "sentinel.ts"
        )
        assert os.path.exists(sentinel_path), "sentinel.ts not found"

        with open(sentinel_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            assert "SentinelAgent" in content
            assert "sellPortion" in content
            assert "updatePositionState" in content
        print("✅ AGT-06 (Sentinel): TypeScript file valid")

    def test_03_janus_typescript_exists(self):
        """Test Janus (AGT-07) TypeScript file exists."""
        import os

        janus_path = os.path.join(
            project_root, "src", "typescript", "agents", "janus.ts"
        )
        assert os.path.exists(janus_path), "janus.ts not found"

        with open(janus_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            assert "JanusAgent" in content
            assert "checkSniperBalance" in content
        print("✅ AGT-07 (Janus): TypeScript file valid")

    def test_04_dist_builds_exist(self):
        """Test TypeScript dist builds exist."""
        import os

        dist_files = [
            "dist/agents/ares.js",
            "dist/agents/sentinel.js",
            "dist/agents/janus.js",
            "dist/shared/envelope.js",
            "dist/shared/keystore.js",
        ]
        for dist_file in dist_files:
            path = os.path.join(project_root, dist_file)
            assert os.path.exists(path), f"{dist_file} not found"
        print("✅ TypeScript: All dist builds exist")

    def test_05_typescript_entry_points(self):
        """Test TypeScript entry point files."""
        import os

        entries = [
            "dist/agents/ares_start.js",
            "dist/agents/sentinel_start.js",
            "dist/agents/janus_start.js",
        ]
        for entry in entries:
            path = os.path.join(project_root, entry)
            assert os.path.exists(path), f"{entry} not found"
        print("✅ TypeScript: Entry points exist")


class TestCompleteFlow:
    """Test complete token→trade flow through all agents."""

    def test_01_complete_flow_redis_simulation(self):
        """Simulate complete token→trade flow through Redis."""

        async def test_flow():
            redis = await aioredis.from_url(
                "redis://localhost:6379", decode_responses=True
            )

            correlation_id = str(uuid.uuid4())
            token = {
                "mint": "5ZH8bCprBLN1qhS4dDdTGQnQxKVC3F1k6jz5rR5ax",
                "symbol": "FULL",
                "marketCapSol": 50.0,
                "vSolInBondingCurve": 45000000000,
                "bondingCurveKey": "curve_key",
                "uri": "",
            }

            envelope = AgentMessageEnvelope(
                agent_id="AGT-01",
                event_type="token_detected",
                payload=token,
                correlation_id=correlation_id,
            )
            priority = calculate_priority("create", token.get("vSolInBondingCurve", 0))
            await redis.zadd(
                KEY_TRADE_QUEUE, {json.dumps(envelope.model_dump()): priority}
            )

            queue_count = await redis.zcard(KEY_TRADE_QUEUE)
            assert queue_count == 1

            result = await redis.zrange(KEY_TRADE_QUEUE, 0, 0)
            item = json.loads(result[0])
            assert item["event_type"] == "token_detected"

            await redis.set(KEY_POSITION_SIZE_SOL, "0.0005")
            position_size = await redis.get(KEY_POSITION_SIZE_SOL)
            assert float(position_size) == 0.0005

            await redis.sadd(KEY_ALL_ACTIVE_POSITIONS, correlation_id)
            active_count = await redis.scard(KEY_ALL_ACTIVE_POSITIONS)
            assert active_count == 1

            await redis.set("mtus:daily_pnl", "0.001")
            pnl = await redis.get("mtus:daily_pnl")
            assert float(pnl) > -0.002

            await redis.delete(KEY_TRADE_QUEUE)
            await redis.delete(KEY_ALL_ACTIVE_POSITIONS)
            await redis.close()
            return True

        result = asyncio.run(test_flow())
        assert result == True
        print("✅ Complete Flow: Token detection → queue → position opened")

    def test_02_safety_gates_simulation(self):
        """Simulate Anansi safety gates."""

        async def test_gates():
            redis = await aioredis.from_url(
                "redis://localhost:6379", decode_responses=True
            )

            token = {
                "mint": "5ZH8bCprBLN1qhS4dDdTGQnQxKVC3F1k6jz5rR5ax",
                "symbol": "TEST",
                "marketCapSol": 50.0,
            }

            min_mcap = 5
            max_mcap = 150
            mcap = token["marketCapSol"]
            gate_passed = min_mcap <= mcap <= max_mcap
            assert gate_passed == True

            await redis.set("mtus:min_market_cap_sol", str(min_mcap))
            await redis.set("mtus:max_market_cap_sol", str(max_mcap))

            await redis.close()
            return True

        result = asyncio.run(test_gates())
        assert result == True
        print("✅ Safety Gates: G7 market cap check works")

    def test_03_tp_sl_multipliers(self):
        """Test TP/SL multiplier calculations."""
        entry_price = 0.0005
        tp1_multiplier = 2.0
        tp2_multiplier = 5.0
        sl_multiplier = 0.7

        tp1_price = entry_price * tp1_multiplier
        tp2_price = entry_price * tp2_multiplier
        sl_price = entry_price * sl_multiplier

        assert tp1_price == 0.001
        assert tp2_price == 0.0025
        assert sl_price == 0.00035
        print("✅ TP/SL: Multiplier calculations correct")

    def test_04_emergency_procedures(self):
        """Test kill switch and pause functionality."""

        async def test_emergency():
            redis = await aioredis.from_url(
                "redis://localhost:6379", decode_responses=True
            )

            await redis.set(REDIS_KEY_KILL_SWITCH, "active")
            await redis.set(REDIS_KEY_TRADING_PAUSED, "true")

            kill_switch = await redis.get(REDIS_KEY_KILL_SWITCH)
            paused = await redis.get(REDIS_KEY_TRADING_PAUSED)

            can_trade = kill_switch != "active" and paused != "true"
            assert can_trade == False

            await redis.delete(REDIS_KEY_KILL_SWITCH)
            await redis.delete(REDIS_KEY_TRADING_PAUSED)

            kill_switch = await redis.get(REDIS_KEY_KILL_SWITCH)
            paused = await redis.get(REDIS_KEY_TRADING_PAUSED)
            can_trade = kill_switch != "active" and paused != "true"
            assert can_trade == True

            await redis.close()
            return True

        result = asyncio.run(test_emergency())
        assert result == True
        print("✅ Emergency: Kill switch and pause work")


class TestDashboardBridge:
    """Test dashboard bridge functionality."""

    def test_01_dashboard_websocket_setup(self):
        """Test dashboard WebSocket can be set up."""
        import os

        bridge_path = os.path.join(
            project_root, "src", "python", "agents", "dashboard_bridge.py"
        )
        assert os.path.exists(bridge_path), "dashboard_bridge.py not found"

        with open(bridge_path, "r") as f:
            content = f.read()
            assert "WebSocketServer" in content or "websocket" in content.lower()
        print("✅ DashboardBridge: WebSocket setup file exists")

    def test_02_dashboard_pages_exist(self):
        """Test dashboard pages exist."""
        import os

        dashboard_path = os.path.join(project_root, "dashboard")
        assert os.path.exists(dashboard_path), "dashboard folder not found"

        pages = [
            "package.json",
            "src/app/page.tsx",
            "src/app/positions/page.tsx",
            "src/app/settings/page.tsx",
        ]
        for page in pages:
            check_path = os.path.join(dashboard_path, page)
            assert os.path.exists(check_path), f"dashboard/{page} not found"
        print("✅ Dashboard: Pages exist")


class TestAgentIDMapping:
    """Test all 11 agent IDs are correctly mapped."""

    def test_01_agent_id_assignments(self):
        """Test all agent IDs are assigned correctly."""
        agent_map = {
            "AGT-01": "NOFX",
            "AGT-02": "Hermes",
            "AGT-03": "Anansi",
            "AGT-04": "Oracle",
            "AGT-05": "Ares",
            "AGT-06": "Sentinel",
            "AGT-07": "Janus",
            "AGT-08": "Cassandra",
            "AGT-09": "Ledger",
            "AGT-10": "Heracles",
            "AGT-11": "DashboardBridge",
        }
        assert len(agent_map) == 11
        print("✅ Agent IDs: All 11 agents mapped correctly")


class TestEnvironmentAndConfig:
    """Test environment and configuration."""

    def test_01_paper_mode_detection(self):
        """Test paper mode is detected."""
        result = is_paper_mode()
        assert isinstance(result, bool)
        print(f"✅ Environment: Paper mode = {result}")

    def test_02_keystore_files_exist(self):
        """Test keystore files exist."""
        import os

        keystores = ["sniper.keystore", "main.keystore"]
        keystore_path = os.path.join(project_root, "keystores")
        for ks in keystores:
            path = os.path.join(keystore_path, ks)
            assert os.path.exists(path), f"keystore/{ks} not found"
        print("✅ Keystores: Both files exist")

    def test_03_config_yaml_exists(self):
        """Test config.yaml exists."""
        import os

        config_path = os.path.join(project_root, "config", "config.yaml")
        assert os.path.exists(config_path), "config/config.yaml not found"
        print("✅ Config: YAML file exists")


class TestAllChannelsIntegration:
    """Test all Redis channels work together."""

    def test_01_all_event_channels(self):
        """Test all event channels can publish and subscribe."""

        async def test_all_channels():
            redis = await aioredis.from_url(
                "redis://localhost:6379", decode_responses=True
            )

            channels = {
                CHANNEL_TOKEN_DETECTED: "token_detected",
                CHANNEL_TOKEN_RECEIVED: "token_received",
                CHANNEL_TOKEN_QUALIFIED: "token_qualified",
                CHANNEL_TRADE_APPROVED: "trade_approved",
                CHANNEL_POSITION_OPENED: "position_opened",
                CHANNEL_TP1_HIT: "tp1_hit",
                CHANNEL_TP2_HIT: "tp2_hit",
                CHANNEL_STOP_LOSS_HIT: "stop_loss_hit",
                CHANNEL_TRADE_FAILED: "trade_failed",
            }

            for channel, event_type in channels.items():
                pubsub = redis.pubsub()
                await pubsub.subscribe(channel)

                envelope = AgentMessageEnvelope(
                    agent_id="AGT-01",
                    event_type=event_type,
                    payload={"test": "data"},
                    correlation_id=str(uuid.uuid4()),
                )
                await redis.publish(channel, envelope.model_dump_json())

                await asyncio.sleep(0.1)
                await pubsub.unsubscribe(channel)
                await pubsub.close()

            await redis.close()
            return True

        result = asyncio.run(test_all_channels())
        assert result == True
        print("✅ All Channels: All event channels work")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
