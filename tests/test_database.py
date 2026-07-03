import pytest

from src.database import Database
from src.models import AvailabilityResult, Candidate, UsernameStatus
from src.time_utils import utc_now


@pytest.fixture
async def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    database = Database(db_path)
    await database.init_db()
    yield database
    await database.close()


@pytest.mark.asyncio
class TestDatabase:
    async def test_init_creates_tables(self, db):
        cursor = await db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row["name"] for row in await cursor.fetchall()}
        assert "candidates" in tables
        assert "checks" in tables
        assert "settings" in tables
        assert "run_history" in tables

    async def test_add_and_get_candidates(self, db):
        candidates = [
            Candidate(username="user1", created_at=utc_now()),
            Candidate(username="user2", created_at=utc_now()),
        ]
        await db.add_candidates(candidates, "run1")
        pending = await db.get_pending_candidates("run1")
        assert len(pending) == 2
        assert {c.username for c in pending} == {"user1", "user2"}

    async def test_update_candidate_status(self, db):
        candidates = [Candidate(username="testuser", created_at=utc_now())]
        await db.add_candidates(candidates, "run1")

        await db.update_candidate("testuser", UsernameStatus.AVAILABLE, None, "run1")

        pending = await db.get_pending_candidates("run1")
        assert len(pending) == 0

        available = await db.get_candidates_by_status(UsernameStatus.AVAILABLE, "run1")
        assert len(available) == 1
        assert available[0].username == "testuser"

    async def test_get_candidates_by_status(self, db):
        candidates = [
            Candidate(username="u1", created_at=utc_now()),
            Candidate(username="u2", created_at=utc_now()),
            Candidate(username="u3", created_at=utc_now()),
        ]
        await db.add_candidates(candidates, "run1")
        await db.update_candidate("u1", UsernameStatus.AVAILABLE, None, "run1")
        await db.update_candidate("u2", UsernameStatus.UNAVAILABLE, None, "run1")

        available = await db.get_candidates_by_status(UsernameStatus.AVAILABLE, "run1")
        assert len(available) == 1
        assert available[0].username == "u1"

    async def test_create_and_get_run(self, db):
        await db.create_run("run123", 50)
        run = await db.get_latest_run()
        assert run is not None
        assert run.run_id == "run123"
        assert run.total_candidates == 50

    async def test_update_run(self, db):
        await db.create_run("run1", 10)
        await db.update_run("run1", checked=5, available=2, errors=1)
        run = await db.get_latest_run()
        assert run.checked == 5
        assert run.available == 2
        assert run.errors == 1

    async def test_resume_pending(self, db):
        candidates = [
            Candidate(username=f"user{i}", created_at=utc_now())
            for i in range(5)
        ]
        await db.add_candidates(candidates, "run1")
        await db.update_candidate("user0", UsernameStatus.AVAILABLE, None, "run1")
        await db.update_candidate("user1", UsernameStatus.UNAVAILABLE, None, "run1")

        pending = await db.get_pending_candidates("run1")
        assert len(pending) == 3
        assert {c.username for c in pending} == {"user2", "user3", "user4"}

    async def test_add_check(self, db):
        result = AvailabilityResult(
            username="testuser",
            status=UsernameStatus.AVAILABLE,
            checked_at=utc_now(),
            provider_metadata={"provider": "mock"},
        )
        await db.add_check(result, "run1")
        cursor = await db._conn.execute("SELECT * FROM checks WHERE run_id = ?", ("run1",))
        rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["username"] == "testuser"

    async def test_settings(self, db):
        await db.set_setting("test_key", "test_value")
        value = await db.get_setting("test_key")
        assert value == "test_value"

        await db.set_setting("test_key", "updated")
        value = await db.get_setting("test_key")
        assert value == "updated"

    async def test_get_setting_missing(self, db):
        value = await db.get_setting("nonexistent")
        assert value is None
