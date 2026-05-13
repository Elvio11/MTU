import asyncio
import time
import random
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
import aiohttp
from src.python.shared.safe_output import safe_print as print

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class TokenBucket:
    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = 0.0
    last_refill: float = 0.0

    def __post_init__(self):
        self.tokens = self.capacity
        self.last_refill = time.time()

    def consume(self, amount: float = 1.0) -> bool:
        self.refill()
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

    def refill(self):
        now = time.time()
        delta = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + delta * self.refill_rate)
        self.last_refill = now

@dataclass
class ApiProvider:
    name: str
    url: str
    key: Optional[str] = None
    weight: int = 10
    capacity: float = 5.0
    refill_rate: float = 1.0
    failures: int = 0
    last_success: float = 0
    state: CircuitState = CircuitState.CLOSED
    state_change_time: float = 0
    bucket: Optional[TokenBucket] = None
    headers: Optional[Dict[str, str]] = None

    def __post_init__(self):
        self.bucket = TokenBucket(capacity=self.capacity, refill_rate=self.refill_rate)
        if self.headers is None:
            self.headers = {}

class ApiRouter:
    """Mathematical API router with Token Bucket rate limiting and automatic failover"""

    def __init__(self, name: str, providers: List[ApiProvider], failure_threshold: int = 3, reset_timeout: int = 60):
        self.name = name
        self.providers = {p.name: p for p in providers}
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _check_circuit_state(self):
        current_time = time.time()
        for name, p in self.providers.items():
            if p.state == CircuitState.OPEN:
                if current_time - p.state_change_time >= self.reset_timeout:
                    p.state = CircuitState.HALF_OPEN
                    print(f"[API-ROUTER] {self.name}:{name} moved to HALF_OPEN")
            elif p.state == CircuitState.HALF_OPEN:
                if current_time - p.state_change_time >= 10:
                    if p.failures >= self.failure_threshold:
                        p.state = CircuitState.OPEN
                        p.state_change_time = current_time
                    else:
                        p.state = CircuitState.CLOSED
                        p.failures = 0

    def _record_success(self, name: str):
        p = self.providers[name]
        p.failures = 0
        p.last_success = time.time()
        if p.state == CircuitState.HALF_OPEN:
            p.state = CircuitState.CLOSED

    def _record_failure(self, name: str, is_429: bool = False):
        p = self.providers[name]
        p.failures += 1
        if is_429:
            # For 429, we open the circuit immediately to force failover
            p.state = CircuitState.OPEN
            p.state_change_time = time.time()
            print(f"[API-ROUTER] {self.name}:{name} rate limited (429). Opening circuit.")
        elif p.failures >= self.failure_threshold or p.state == CircuitState.HALF_OPEN:
            p.state = CircuitState.OPEN
            p.state_change_time = time.time()
            print(f"[API-ROUTER] {self.name}:{name} opened after {p.failures} failures")

    async def call(self, method: str, path: str = "", headers: Dict = None, params: Dict = None, json_data: Dict = None, timeout: int = 10, provider: str = None) -> Optional[Any]:
        """Call API with automatic failover and rate limiting"""
        self._check_circuit_state()

        if provider:
            p = self.providers.get(provider)
            if not p or p.state == CircuitState.OPEN:
                return None
            available = [p]
        else:
            # Filter available providers (not open and has tokens)
            available = [p for p in self.providers.values() if p.state != CircuitState.OPEN]
            
            # Sort by weight and tokens available (mathematical routing)
            # We prefer providers with more tokens relative to capacity
            available.sort(key=lambda x: (x.bucket.tokens / x.capacity) * x.weight, reverse=True)

        if not available:
            return None

        for p in available:
            if not p.bucket.consume():
                continue # Skip if bucket is empty

            full_url = p.url + path
            req_headers = p.headers.copy()
            req_headers.update(headers or {})
            if p.key:
                # Common header patterns
                if "birdeye" in p.name.lower():
                    req_headers["X-API-KEY"] = p.key
                elif "rugcheck" in p.name.lower():
                    req_headers["Authorization"] = f"Bearer {p.key}"
                else:
                    req_headers["X-API-KEY"] = p.key

            try:
                session = await self.get_session()
                async with session.request(method, full_url, headers=req_headers, params=params, json=json_data, timeout=timeout) as resp:
                    if resp.status == 200:
                        self._record_success(p.name)
                        return await resp.json()
                    elif resp.status == 429:
                        self._record_failure(p.name, is_429=True)
                        continue
                    else:
                        print(f"[API-ROUTER] {p.name} returned status {resp.status}")
                        self._record_failure(p.name)
                        continue
            except Exception as e:
                print(f"[API-ROUTER] {p.name} request failed: {e}")
                self._record_failure(p.name)
                continue

        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

class GlobalApiManager:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(GlobalApiManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized: return
        self.routers: Dict[str, ApiRouter] = {}
        self.initialized = True

    def setup_router(self, name: str, providers: List[ApiProvider]):
        self.routers[name] = ApiRouter(name, providers)

    async def request(self, group: str, method: str, path: str = "", provider: str = None, **kwargs) -> Optional[Any]:
        router = self.routers.get(group)
        if not router:
            raise ValueError(f"No router found for group: {group}")
        return await router.call(method, path, provider=provider, **kwargs)

    def get_stats(self) -> Dict[str, Any]:
        stats = {}
        for name, router in self.routers.items():
            stats[name] = {
                provider_name: {
                    "failures": p.failures,
                    "last_success": p.last_success,
                    "state": p.state.value,
                    "tokens": round(p.bucket.tokens, 2)
                }
                for provider_name, p in router.providers.items()
            }
        return stats

    async def close_all(self):
        for router in self.routers.values():
            await router.close()
