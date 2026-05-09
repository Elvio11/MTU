import asyncio
import aioredis
import json
import os
from typing import Set
import websockets
from src.python.shared.constants import (
    CHANNEL_POSITION_OPENED,
    CHANNEL_POSITION_CLOSED,
    CHANNEL_PRICE_UPDATED,
    CHANNEL_HEALTH_CHECK,
    CHANNEL_SYSTEM_ALERT,
    CHANNEL_KILL_SWITCH_TRIGGERED,
)


class DashboardBridge:
    """AGT-11: Bridge Redis pub/sub to WebSocket clients"""

    def __init__(self, redis_url: str = "redis://localhost:6379", ws_port: int = 3001):
        self.redis_url = redis_url
        self.ws_port = ws_port
        self.clients = set()
        self.redis = None
        self.pubsub = None
        self.running = False

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

    async def run(self):
        """Start WebSocket server and Redis listener"""
        print(f"AGT-11: Starting Dashboard Bridge on port {self.ws_port}")
        self.running = True

        # Start WebSocket server
        async with websockets.serve(self.handler, "0.0.0.0", self.ws_port):
            print(f"AGT-11: WebSocket server started on ws://0.0.0.0:{self.ws_port}")
            # Start Redis listener
            await self.forward_redis_messages()

    async def stop(self):
        """Stop the bridge"""
        self.running = False
        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
        if self.redis:
            await self.redis.close()
        print("AGT-11: Bridge stopped")


if __name__ == "__main__":
    bridge = DashboardBridge()
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        asyncio.run(bridge.stop())
