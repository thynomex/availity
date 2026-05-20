import asyncio
import random
import time
from typing import Optional

from src.config import AppConfig


class TokenState:
    """Tracks rate-limit state for a single Discord token."""

    def __init__(self, token: str, index: int):
        self.token = token
        self.index = index
        self.available_at: float = 0
        self.consecutive_failures: int = 0
        self.alive: bool = True

    @property
    def is_ready(self) -> bool:
        return self.alive and time.time() >= self.available_at

    def cooldown(self, seconds: float):
        self.available_at = time.time() + seconds

    def mark_dead(self):
        self.alive = False

    def record_success(self):
        self.consecutive_failures = 0

    def record_failure(self, cooldown: float = 5.0):
        self.consecutive_failures += 1
        self.cooldown(cooldown)


class TokenPool:
    """Thread-safe pool that distributes requests across tokens."""

    def __init__(self, tokens: list[str]):
        self._states = [TokenState(t, i) for i, t in enumerate(tokens)]
        self._lock = asyncio.Lock()
        self._index = 0

    @property
    def alive_count(self) -> int:
        return sum(1 for s in self._states if s.alive)

    @property
    def all_tokens(self) -> list[TokenState]:
        return self._states

    async def acquire(self) -> Optional[TokenState]:
        """Get the next available token, waiting if all are cooling down."""
        while True:
            async with self._lock:
                alive = [s for s in self._states if s.alive]
                if not alive:
                    return None

                ready = [s for s in alive if s.is_ready]
                if ready:
                    best = min(ready, key=lambda s: s.available_at)
                    best.available_at = time.time()
                    return best

            shortest_wait = min(
                (s.available_at - time.time() for s in self._states if s.alive),
                default=0.1,
            )
            await asyncio.sleep(max(shortest_wait, 0.05))

    async def report_rate_limited(self, state: TokenState, retry_after: float):
        async with self._lock:
            state.record_failure(retry_after)

    async def report_dead(self, state: TokenState):
        async with self._lock:
            state.mark_dead()

    async def report_success(self, state: TokenState):
        async with self._lock:
            state.record_success()


class RateLimiter:
    """Controls concurrency via semaphore. Token-level rate limiting is handled by TokenPool."""

    def __init__(self, config: AppConfig):
        self.config = config
        effective_concurrency = min(config.concurrency, config.max_concurrency)
        self.semaphore = asyncio.Semaphore(effective_concurrency)

    async def acquire(self):
        await self.semaphore.acquire()

    def release(self):
        self.semaphore.release()

    def calculate_backoff(self, retry_count: int) -> float:
        base = self.config.backoff_base ** retry_count
        jitter = random.uniform(0, base * 0.5)
        return min(base + jitter, self.config.backoff_max)
