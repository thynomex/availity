import asyncio
import uuid
from datetime import datetime
from typing import Callable, Optional

from src.config import AppConfig
from src.database import Database
from src.models import AvailabilityResult, Candidate, UsernameStatus
from src.providers import DiscordProvider
from src.rate_limiter import RateLimiter, TokenPool
from src.validator import validate_username


class UsernameChecker:
    def __init__(
        self,
        config: AppConfig,
        provider: DiscordProvider,
        db: Database,
        rate_limiter: RateLimiter,
        token_pool: TokenPool,
    ):
        self.config = config
        self.provider = provider
        self.db = db
        self.rate_limiter = rate_limiter
        self.token_pool = token_pool
        self._stats = {"checked": 0, "available": 0, "errors": 0, "rate_limited": 0}
        self._cancelled = False
        self._on_rate_limit: Optional[Callable] = None
        self._lock = asyncio.Lock()

    def cancel(self):
        self._cancelled = True

    def reset(self):
        self._cancelled = False
        self._stats = {"checked": 0, "available": 0, "errors": 0, "rate_limited": 0}

    @property
    def stats(self) -> dict:
        return self._stats.copy()

    async def check_single(self, username: str) -> AvailabilityResult:
        validation = validate_username(username, self.config)
        if not validation.valid:
            return AvailabilityResult(
                username=username,
                status=UsernameStatus.INVALID,
                checked_at=datetime.utcnow(),
                error_message=validation.reason,
            )
        return await self._check_with_retry(username)

# --- PLACEHOLDER_CHECKER_BATCH ---

    async def check_batch(
        self,
        usernames: list[str],
        run_id: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        on_found: Optional[Callable] = None,
        on_check: Optional[Callable] = None,
        on_rate_limit: Optional[Callable] = None,
    ) -> list[AvailabilityResult]:
        if not run_id:
            run_id = str(uuid.uuid4())

        candidates = [
            Candidate(username=u, created_at=datetime.utcnow()) for u in usernames
        ]
        await self.db.create_run(run_id, len(candidates))
        await self.db.add_candidates(candidates, run_id)

        return await self._process_pending(run_id, progress_callback, on_found, on_check, on_rate_limit)

    async def resume_run(
        self, run_id: str, progress_callback: Optional[Callable] = None,
        on_found: Optional[Callable] = None,
        on_check: Optional[Callable] = None,
        on_rate_limit: Optional[Callable] = None,
    ) -> list[AvailabilityResult]:
        return await self._process_pending(run_id, progress_callback, on_found, on_check, on_rate_limit)

    async def _process_pending(
        self, run_id: str, progress_callback: Optional[Callable] = None,
        on_found: Optional[Callable] = None,
        on_check: Optional[Callable] = None,
        on_rate_limit: Optional[Callable] = None,
    ) -> list[AvailabilityResult]:
        self._cancelled = False
        self._stats = {"checked": 0, "available": 0, "errors": 0, "rate_limited": 0}
        self._on_rate_limit = on_rate_limit
        results: list[AvailabilityResult] = []
        pending = await self.db.get_pending_candidates(run_id)

        if not pending:
            return results

        queue: asyncio.Queue = asyncio.Queue()
        for candidate in pending:
            queue.put_nowait(candidate)

        worker_count = min(self.config.concurrency, len(pending))

        async def worker():
            while not self._cancelled:
                try:
                    candidate = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                try:
                    if on_check:
                        on_check(candidate.username)

                    result = await self._check_with_retry(candidate.username)

                    await self.db.update_candidate(
                        candidate.username, result.status, result.error_message, run_id
                    )
                    await self.db.add_check(result, run_id)

                    async with self._lock:
                        results.append(result)
                        self._stats["checked"] += 1
                        if result.status == UsernameStatus.AVAILABLE:
                            self._stats["available"] += 1
                            if on_found:
                                await on_found(result)
                        elif result.status == UsernameStatus.ERROR:
                            self._stats["errors"] += 1
                        elif result.status == UsernameStatus.RATE_LIMITED:
                            self._stats["rate_limited"] += 1

                        if progress_callback:
                            progress_callback(self._stats, len(pending))
                except (KeyboardInterrupt, asyncio.CancelledError):
                    self._cancelled = True
                    break

                queue.task_done()

        try:
            workers = [asyncio.create_task(worker()) for _ in range(worker_count)]
            await asyncio.gather(*workers)
        except (KeyboardInterrupt, asyncio.CancelledError):
            self._cancelled = True

        await self.db.update_run(
            run_id,
            checked=self._stats["checked"],
            available=self._stats["available"],
            errors=self._stats["errors"],
        )

        if not self._cancelled:
            await self.db.update_run(run_id, finished_at=datetime.utcnow())

        return results

    async def _check_with_retry(self, username: str) -> AvailabilityResult:
        for attempt in range(self.config.max_retries + 1):
            await self.rate_limiter.acquire()
            try:
                token_state = await self.token_pool.acquire()
                if token_state is None:
                    return AvailabilityResult(
                        username=username,
                        status=UsernameStatus.ERROR,
                        checked_at=datetime.utcnow(),
                        error_message="All tokens are dead",
                    )

                result = await self.provider.check_with_token(username, token_state.token)
            finally:
                self.rate_limiter.release()

            if result.status in (UsernameStatus.AVAILABLE, UsernameStatus.UNAVAILABLE):
                await self.token_pool.report_success(token_state)
                return result

            if result.status == UsernameStatus.RATE_LIMITED:
                retry_after = 5.0
                if result.provider_metadata and "retry_after" in result.provider_metadata:
                    retry_after = float(result.provider_metadata["retry_after"])
                await self.token_pool.report_rate_limited(token_state, retry_after)
                if self._on_rate_limit:
                    self._on_rate_limit(token_state.index, retry_after)
                continue

            if result.status == UsernameStatus.ERROR:
                meta = result.provider_metadata or {}
                if meta.get("token_dead"):
                    await self.token_pool.report_dead(token_state)
                    if self.token_pool.alive_count == 0:
                        return result
                    continue

                if attempt < self.config.max_retries:
                    backoff = self.rate_limiter.calculate_backoff(attempt)
                    await asyncio.sleep(backoff)
                    continue

            return result

        return AvailabilityResult(
            username=username,
            status=UsernameStatus.ERROR,
            checked_at=datetime.utcnow(),
            error_message="Max retries exceeded",
        )
