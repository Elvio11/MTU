import asyncio
import aioredis
import json
import os
import sys
import websockets
import yaml
import sqlite3
from typing import Dict, Any, Set
from src.python.shared.envelope import AgentMessageEnvelope, EventType
from src.python.shared.config_validator import validate_config
from src.python.shared.safe_output import safe_print as print
from src.python.shared.api_manager import GlobalApiManager
from src.python.shared.constants import (
    CHANNEL_POSITION_OPENED,
    CHANNEL_POSITION_CLOSED,
    CHANNEL_PRICE_UPDATED,
    CHANNEL_HEALTH_CHECK,
    CHANNEL_SYSTEM_ALERT,
    CHANNEL_KILL_SWITCH_TRIGGERED,
    KEY_POSITION_SIZE_SOL,
)


class DashboardBridge:
    """AGT-11: Bridge Redis pub/sub to WebSocket clients"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.ws_port = 4001
        self.clients = set()
        self.redis = None
        self.pubsub = None
        self.running = False
        self.api_manager = GlobalApiManager()
        
        # Determine database path
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.db_path = os.path.join(project_root, "data", "positions.db")

    async def handler(self, ws, path=None):
        """Handle WebSocket client connections"""
        self.clients.add(ws)
        print(f"AGT-11: Client connected from {ws.remote_address}, path: {path}")
        try:
            await ws.wait_closed()
        except Exception as e:
            print(f"AGT-11: Client disconnected: {e}")
        finally:
            self.clients.discard(ws)
            print(f"AGT-11: Client removed, active: {len(self.clients)}")

    async def forward_redis_messages(self):
        """Subscribe to Redis channels and forward to WebSocket clients"""
        self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)
        self.pubsub = self.redis.pubsub()

        channels = [
            CHANNEL_POSITION_OPENED,
            CHANNEL_POSITION_CLOSED,
            CHANNEL_PRICE_UPDATED,
            CHANNEL_HEALTH_CHECK,
            CHANNEL_SYSTEM_ALERT,
            CHANNEL_KILL_SWITCH_TRIGGERED,
        ]
        await self.pubsub.subscribe(*channels)
        print(f"AGT-11: Subscribed to {channels}")

        while self.running:
            try:
                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message["type"] == "message":
                    try:
                        channel = message["channel"]
                        data = json.loads(message["data"])
                        # Broadcast to all WebSocket clients
                        disconnected = set()
                        for client in self.clients:
                            try:
                                await client.send(
                                    json.dumps({"type": channel, "payload": data})
                                )
                            except Exception as e:
                                print(f"AGT-11: Error sending to client: {e}")
                                disconnected.add(client)
                        for client in disconnected:
                            self.clients.discard(client)
                    except json.JSONDecodeError as e:
                        print(f"AGT-11: JSON decode error: {e}")
                    except Exception as e:
                        print(f"AGT-11: Error forwarding: {e}")
            except Exception as e:
                if self.running:
                    print(f"AGT-11: Redis poll error: {e}")
            await asyncio.sleep(0.1)

    async def broadcast_system_stats(self):
        """Periodically broadcast API stats and DB metrics"""
        while self.running:
            try:
                if not self.clients:
                    await asyncio.sleep(5)
                    continue

                # Get API stats
                api_stats = self.api_manager.get_stats()

                # Get DB metrics
                db_metrics = {}
                if os.path.exists(self.db_path):
                    try:
                        conn = sqlite3.connect(self.db_path)
                        cursor = conn.cursor()
                        
                        cursor.execute("SELECT SUM(realised_pnl_sol) FROM positions")
                        total_pnl = cursor.fetchone()[0] or 0.0
                        
                        cursor.execute("SELECT COUNT(*) FROM positions WHERE state = 'OPEN'")
                        open_count = cursor.fetchone()[0] or 0
                        
                        cursor.execute("SELECT COUNT(*) FROM positions WHERE realised_pnl_sol > 0")
                        wins = cursor.fetchone()[0] or 0
                        cursor.execute("SELECT COUNT(*) FROM positions WHERE state = 'CLOSED'")
                        closed = cursor.fetchone()[0] or 1
                        win_rate = (wins / max(1, closed)) * 100
                        
                        db_metrics = {
                            "total_pnl": round(total_pnl, 4),
                            "open_positions": open_count,
                            "win_rate": round(win_rate, 2)
                        }
                        conn.close()
                    except Exception as e:
                        print(f"AGT-11: DB metrics error: {e}")

                # Get dynamic position size
                current_size = 0.0
                try:
                    size_val = await self.redis.get(KEY_POSITION_SIZE_SOL)
                    if size_val:
                        current_size = float(size_val)
                except Exception:
                    pass

                stats_payload = {
                    "type": "system_stats",
                    "payload": {
                        "api": api_stats,
                        "metrics": {
                            **db_metrics,
                            "current_position_size": current_size
                        },
                        "timestamp": os.getpid() # Just a marker
                    }
                }

                # Broadcast
                disconnected = set()
                for client in self.clients:
                    try:
                        await client.send(json.dumps(stats_payload))
                    except Exception:
                        disconnected.add(client)
                for client in disconnected:
                    self.clients.discard(client)

            except Exception as e:
                print(f"AGT-11: Stats broadcast error: {e}")
            
            await asyncio.sleep(5)

    async def run(self):
        """Start WebSocket server and Redis listener"""
        print(f"AGT-11: Starting Dashboard Bridge on port {self.ws_port}")
        self.running = True

        # Start WebSocket server
        async with websockets.serve(self.handler, "0.0.0.0", self.ws_port):
            print(f"AGT-11: WebSocket server started on ws://0.0.0.0:{self.ws_port}")
            # Start Redis listener and stats broadcaster
            await asyncio.gather(
                self.forward_redis_messages(),
                self.broadcast_system_stats()
            )

    async def stop(self):
        """Stop the bridge"""
        self.running = False
        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
        if self.redis:
            await self.redis.close()
        print("AGT-11: Bridge stopped")


async def main():
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    config_path = os.path.join(project_root, "config", "config.yaml")

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"[CONFIG] Error loading config: {e}")
        sys.exit(1)

    is_valid, error = validate_config(config)
    if not is_valid:
        print(f"[CONFIG] Configuration validation failed: {error}")
        sys.exit(1)

    bridge = DashboardBridge(config)
    try:
        await bridge.run()
    except KeyboardInterrupt:
        await bridge.stop()

if __name__ == "__main__":
    asyncio.run(main())
