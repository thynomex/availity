import asyncio
import time

import pytest

from src.config import AppConfig
from src.rate_limiter import RateLimiter, TokenPool, TokenState


class TestTokenState:
    def test_starts_ready(self):
        ts = TokenState("tok", 0)
        assert ts.is_ready is True
        assert ts.alive is True

    def test_cooldown(self):
        ts = TokenState("tok", 0)
        ts.cooldown(10.0)
        assert ts.is_ready is False

    def test_mark_dead(self):
        ts = TokenState("tok", 0)
        ts.mark_dead()
        assert ts.alive is False
        assert ts.is_ready is False

    def test_record_success_resets_failures(self):
        ts = TokenState("tok", 0)
        ts.record_failure(1.0)
        ts.record_failure(1.0)
        assert ts.consecutive_failures == 2
        ts.record_success()
        assert ts.consecutive_failures == 0


class TestTokenPool:
    @pytest.mark.asyncio
    async def test_acquire_returns_token(self):
        pool = TokenPool(["token_a", "token_b"])
        state = await pool.acquire()
        assert state is not None
        assert state.token in ("token_a", "token_b")

    @pytest.mark.asyncio
    async def test_acquire_returns_none_when_all_dead(self):
        pool = TokenPool(["token_a"])
        await pool.report_dead(pool.all_tokens[0])
        state = await pool.acquire()
        assert state is None

    @pytest.mark.asyncio
    async def test_rate_limited_token_cools_down(self):
        pool = TokenPool(["token_a", "token_b"])
        state_a = pool.all_tokens[0]
        await pool.report_rate_limited(state_a, 10.0)
        state = await pool.acquire()
        assert state.token == "token_b"

    @pytest.mark.asyncio
    async def test_alive_count(self):
        pool = TokenPool(["a", "b", "c"])
        assert pool.alive_count == 3
        await pool.report_dead(pool.all_tokens[0])
        assert pool.alive_count == 2

    @pytest.mark.asyncio
    async def test_success_resets_state(self):
        pool = TokenPool(["token_a"])
        state = pool.all_tokens[0]
        state.record_failure(0.01)
        await pool.report_success(state)
        assert state.consecutive_failures == 0


class TestRateLimiter:
    @pytest.fixture
    def config(self):
        c = AppConfig()
        c.concurrency = 2
        c.max_concurrency = 1000
        c.request_delay = 0
        c.backoff_base = 2.0
        c.backoff_max = 10.0
        return c

    def test_calculate_backoff_increases(self, config):
        rl = RateLimiter(config)
        b0 = rl.calculate_backoff(0)
        b1 = rl.calculate_backoff(1)
        b2 = rl.calculate_backoff(2)
        assert b0 < b1 < b2

    def test_backoff_capped(self, config):
        rl = RateLimiter(config)
        result = rl.calculate_backoff(100)
        assert result <= config.backoff_max

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self, config):
        config.concurrency = 2
        rl = RateLimiter(config)
        active = []
        max_active = [0]

        async def task():
            await rl.acquire()
            active.append(1)
            max_active[0] = max(max_active[0], len(active))
            await asyncio.sleep(0.05)
            active.pop()
            rl.release()

        await asyncio.gather(*[task() for _ in range(5)])
        assert max_active[0] <= 2
