import asyncio
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import aiohttp


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class RPCEndpoint:
    name: str
    url: str
    weight: int
    failures: int = 0
    last_success: float = 0
    state: CircuitState = CircuitState.CLOSED
    state_change_time: float = 0


class RPCHelper:
    """RPC load balancer with round-robin and circuit breaker"""

    def __init__(
        self,
        helius_url: str,
        quicknode_url: str,
        alchemy_url: str,
        helius_key: str = "",
        failure_threshold: int = 3,
        reset_timeout: int = 60,
    ):
        self.endpoints: Dict[str, RPCEndpoint] = {
            "helius": RPCEndpoint(
                "helius",
                f"{helius_url}?api-key={helius_key}" if helius_key else helius_url,
                50,
            ),
            "quicknode": RPCEndpoint("quicknode", quicknode_url, 35),
            "alchemy": RPCEndpoint("alchemy", alchemy_url, 15),
        }
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.current_index = 0
        self.last_failure_check = 0
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _check_circuit_state(self):
        """Check and update circuit breaker states"""
        current_time = time.time()

        for name, endpoint in self.endpoints.items():
            if endpoint.state == CircuitState.OPEN:
                if current_time - endpoint.state_change_time >= self.reset_timeout:
                    endpoint.state = CircuitState.HALF_OPEN
                    print(f"Circuit: {name} moved to HALF_OPEN")
            elif endpoint.state == CircuitState.HALF_OPEN:
                if current_time - endpoint.state_change_time >= 10:
                    if endpoint.failures >= self.failure_threshold:
                        endpoint.state = CircuitState.OPEN
                        endpoint.state_change_time = current_time
                    else:
                        endpoint.state = CircuitState.CLOSED
                        endpoint.failures = 0

    async def _record_success(self, name: str):
        """Record successful call"""
        endpoint = self.endpoints[name]
        endpoint.failures = 0
        endpoint.last_success = time.time()
        if endpoint.state == CircuitState.HALF_OPEN:
            endpoint.state = CircuitState.CLOSED

    async def _record_failure(self, name: str):
        """Record failed call"""
        endpoint = self.endpoints[name]
        endpoint.failures += 1

        if (
            endpoint.state == CircuitState.HALF_OPEN
            or endpoint.failures >= self.failure_threshold
        ):
            endpoint.state = CircuitState.OPEN
            endpoint.state_change_time = time.time()
            print(f"Circuit: {name} opened after {endpoint.failures} failures")

    async def _get_weighted_endpoints(self) -> List[RPCEndpoint]:
        """Get unique endpoints sorted by last success and weight"""
        await self._check_circuit_state()

        available = [
            ep for ep in self.endpoints.values() if ep.state != CircuitState.OPEN
        ]

        if not available:
            half_open = [
                ep
                for ep in self.endpoints.values()
                if ep.state == CircuitState.HALF_OPEN
            ]
            if half_open:
                return half_open
            return list(self.endpoints.values())

        # Sort by last_success (ascending) and weight (descending)
        # Endpoints with older last_success or higher weight come first
        sorted_endpoints = sorted(
            available,
            key=lambda x: (x.last_success, -x.weight)
        )

        return sorted_endpoints

    async def make_request(
        self, method: str, payload: Dict[str, Any], timeout: int = 30
    ) -> Optional[Dict]:
        """Make RPC request with round-robin and circuit breaker"""
        endpoints = await self._get_weighted_endpoints()

        for endpoint in endpoints:
            try:
                session = await self.get_session()
                async with session.post(
                    endpoint.url, json=payload, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        await self._record_success(endpoint.name)
                        return await resp.json()
                    elif resp.status == 429:
                        await self._record_failure(endpoint.name)
                        continue
                    else:
                        await self._record_failure(endpoint.name)
                        continue
            except Exception as e:
                print(f"RPC {endpoint.name} error: {e}")
                await self._record_failure(endpoint.name)
                continue

        return None

    async def broadcast_transaction(self, signed_tx: str) -> Dict[str, Any]:
        """Broadcast to all 3 RPCs simultaneously"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [signed_tx],
        }

        results = {}

        async def try_broadcast(name: str, endpoint: RPCEndpoint):
            try:
                session = await self.get_session()
                async with session.post(endpoint.url, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        results[name] = {"success": True, "data": await resp.json()}
                        await self._record_success(name)
                    else:
                        results[name] = {
                            "success": False,
                            "error": f"Status {resp.status}",
                        }
                        await self._record_failure(name)
            except Exception as e:
                results[name] = {"success": False, "error": str(e)}
                await self._record_failure(name)

        tasks = [try_broadcast(name, ep) for name, ep in self.endpoints.items()]
        await asyncio.gather(*tasks, return_exceptions=True)

        return results

    def get_status(self) -> Dict[str, Any]:
        """Get status of all endpoints"""
        return {
            name: {
                "state": ep.state.value,
                "failures": ep.failures,
                "weight": ep.weight,
                "last_success": ep.last_success,
            }
            for name, ep in self.endpoints.items()
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
