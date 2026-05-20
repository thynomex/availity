import pytest
import asyncio
import random
from unittest.mock import AsyncMock, MagicMock

from src.checker import UsernameChecker
from src.config import AppConfig
from src.models import AvailabilityResult, Candidate, UsernameStatus, ValidationResult
from src.providers import AvailabilityProvider
from src.rate_limiter import RateLimiter, TokenPool
from src.validator import validate_username
from datetime import datetime


class MockProvider(AvailabilityProvider):
    """Test-only mock provider."""

    def validate_username(self, username: str) -> ValidationResult:
        return validate_username(username)

    async def check_with_token(self, username: str, token: str) -> AvailabilityResult:
        await asyncio.sleep(0.01)
        if username.startswith("avail"):
            status = UsernameStatus.AVAILABLE
        elif username.startswith("taken"):
            status = UsernameStatus.UNAVAILABLE
        elif username.startswith("error"):
            return AvailabilityResult(
                username=username, status=UsernameStatus.ERROR,
                checked_at=datetime.utcnow(), error_message="Simulated error",
            )
        else:
            status = UsernameStatus.AVAILABLE if random.random() < 0.3 else UsernameStatus.UNAVAILABLE
        return AvailabilityResult(
            username=username, status=status, checked_at=datetime.utcnow(),
            provider_metadata={"provider": "mock"},
        )

    async def check_username(self, username: str) -> AvailabilityResult:
        return await self.check_with_token(username, "fake_token")


@pytest.fixture
def config():
    c = AppConfig()
    c.concurrency = 1
    c.request_delay = 0
    c.max_retries = 2
    c.max_concurrency = 10
    c.backoff_base = 2.0
    c.backoff_max = 60.0
    return c


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.create_run = AsyncMock()
    db.add_candidates = AsyncMock()
    db.update_candidate = AsyncMock()
    db.add_check = AsyncMock()
    db.update_run = AsyncMock()
    db.get_pending_candidates = AsyncMock(return_value=[
        Candidate(username="avail.one", created_at=datetime.utcnow()),
        Candidate(username="taken.two", created_at=datetime.utcnow()),
    ])
    return db


@pytest.fixture
def token_pool():
    return TokenPool(["fake_token_1"])


@pytest.mark.asyncio
class TestUsernameChecker:
    async def test_check_single_available(self, config, mock_db, token_pool):
        provider = MockProvider()
        rl = RateLimiter(config)
        checker = UsernameChecker(config, provider, mock_db, rl, token_pool)

        result = await checker.check_single("avail.test")
        assert result.status == UsernameStatus.AVAILABLE

    async def test_check_single_taken(self, config, mock_db, token_pool):
        provider = MockProvider()
        rl = RateLimiter(config)
        checker = UsernameChecker(config, provider, mock_db, rl, token_pool)

        result = await checker.check_single("taken.test")
        assert result.status == UsernameStatus.UNAVAILABLE

    async def test_check_single_invalid(self, config, mock_db, token_pool):
        provider = MockProvider()
        rl = RateLimiter(config)
        checker = UsernameChecker(config, provider, mock_db, rl, token_pool)

        result = await checker.check_single("")
        assert result.status == UsernameStatus.INVALID

    async def test_check_batch(self, config, mock_db, token_pool):
        provider = MockProvider()
        rl = RateLimiter(config)
        checker = UsernameChecker(config, provider, mock_db, rl, token_pool)

        usernames = ["avail.one", "taken.two", "avail.three"]
        mock_db.get_pending_candidates = AsyncMock(return_value=[
            Candidate(username=u, created_at=datetime.utcnow()) for u in usernames
        ])

        results = await checker.check_batch(usernames, "test_run")
        assert len(results) == 3
        assert mock_db.create_run.called
        assert mock_db.add_candidates.called
        assert mock_db.update_candidate.call_count == 3
        assert mock_db.add_check.call_count == 3

    async def test_check_batch_updates_stats(self, config, mock_db, token_pool):
        provider = MockProvider()
        rl = RateLimiter(config)
        checker = UsernameChecker(config, provider, mock_db, rl, token_pool)

        usernames = ["avail.x1", "avail.x2"]
        mock_db.get_pending_candidates = AsyncMock(return_value=[
            Candidate(username=u, created_at=datetime.utcnow()) for u in usernames
        ])

        await checker.check_batch(usernames, "run1")
        assert checker.stats["checked"] == 2
        assert checker.stats["available"] == 2

    async def test_check_single_with_error_retries(self, config, mock_db, token_pool):
        provider = MockProvider()
        rl = RateLimiter(config)
        checker = UsernameChecker(config, provider, mock_db, rl, token_pool)

        result = await checker.check_single("error.test")
        assert result.status == UsernameStatus.ERROR
