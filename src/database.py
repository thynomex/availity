import json
from datetime import datetime
from typing import Optional

import aiosqlite

from src.models import AvailabilityResult, Candidate, RunRecord, UsernameStatus
from src.time_utils import utc_now


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def init_db(self):
        if not self._conn:
            await self.connect()
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                checked_at TEXT,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                run_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                status TEXT NOT NULL,
                checked_at TEXT,
                error_message TEXT,
                provider_metadata TEXT,
                run_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS run_history (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                total_candidates INTEGER DEFAULT 0,
                checked INTEGER DEFAULT 0,
                available INTEGER DEFAULT 0,
                errors INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_candidates_run_status
                ON candidates(run_id, status);
            CREATE INDEX IF NOT EXISTS idx_checks_run
                ON checks(run_id);
        """)
        await self._conn.commit()

    async def add_candidates(self, candidates: list[Candidate], run_id: str):
        rows = [
            (c.username, c.status.value, c.created_at.isoformat(), run_id)
            for c in candidates
        ]
        await self._conn.executemany(
            "INSERT INTO candidates (username, status, created_at, run_id) VALUES (?, ?, ?, ?)",
            rows,
        )
        await self._conn.commit()

    async def update_candidate(
        self, username: str, status: UsernameStatus, error_message: Optional[str], run_id: str
    ):
        await self._conn.execute(
            """UPDATE candidates
               SET status = ?, checked_at = ?, error_message = ?, retry_count = retry_count + 1
               WHERE username = ? AND run_id = ?""",
            (status.value, utc_now().isoformat(), error_message, username, run_id),
        )
        await self._conn.commit()

    async def get_pending_candidates(self, run_id: str) -> list[Candidate]:
        cursor = await self._conn.execute(
            "SELECT username, status, created_at, checked_at, error_message, retry_count "
            "FROM candidates WHERE run_id = ? AND status IN (?, ?)",
            (run_id, UsernameStatus.PENDING.value, UsernameStatus.RATE_LIMITED.value),
        )
        rows = await cursor.fetchall()
        return [
            Candidate(
                username=r["username"],
                status=UsernameStatus(r["status"]),
                created_at=datetime.fromisoformat(r["created_at"]),
                checked_at=datetime.fromisoformat(r["checked_at"]) if r["checked_at"] else None,
                error_message=r["error_message"],
                retry_count=r["retry_count"],
            )
            for r in rows
        ]

    async def get_candidates_by_status(self, status: UsernameStatus, run_id: str) -> list[Candidate]:
        cursor = await self._conn.execute(
            "SELECT username, status, created_at, checked_at, error_message, retry_count "
            "FROM candidates WHERE run_id = ? AND status = ?",
            (run_id, status.value),
        )
        rows = await cursor.fetchall()
        return [
            Candidate(
                username=r["username"],
                status=UsernameStatus(r["status"]),
                created_at=datetime.fromisoformat(r["created_at"]),
                checked_at=datetime.fromisoformat(r["checked_at"]) if r["checked_at"] else None,
                error_message=r["error_message"],
                retry_count=r["retry_count"],
            )
            for r in rows
        ]

    async def get_all_candidates(self, run_id: str) -> list[Candidate]:
        cursor = await self._conn.execute(
            "SELECT username, status, created_at, checked_at, error_message, retry_count "
            "FROM candidates WHERE run_id = ?",
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [
            Candidate(
                username=r["username"],
                status=UsernameStatus(r["status"]),
                created_at=datetime.fromisoformat(r["created_at"]),
                checked_at=datetime.fromisoformat(r["checked_at"]) if r["checked_at"] else None,
                error_message=r["error_message"],
                retry_count=r["retry_count"],
            )
            for r in rows
        ]

    async def add_check(self, result: AvailabilityResult, run_id: str):
        metadata = json.dumps(result.provider_metadata) if result.provider_metadata else None
        await self._conn.execute(
            "INSERT INTO checks (username, status, checked_at, error_message, provider_metadata, run_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                result.username,
                result.status.value,
                result.checked_at.isoformat() if result.checked_at else None,
                result.error_message,
                metadata,
                run_id,
            ),
        )
        await self._conn.commit()

    async def create_run(self, run_id: str, total: int):
        await self._conn.execute(
            "INSERT INTO run_history (run_id, started_at, total_candidates) VALUES (?, ?, ?)",
            (run_id, utc_now().isoformat(), total),
        )
        await self._conn.commit()

    async def update_run(self, run_id: str, **kwargs):
        sets = []
        vals = []
        for k, v in kwargs.items():
            sets.append(f"{k} = ?")
            vals.append(v.isoformat() if isinstance(v, datetime) else v)
        vals.append(run_id)
        await self._conn.execute(
            f"UPDATE run_history SET {', '.join(sets)} WHERE run_id = ?", vals
        )
        await self._conn.commit()

    async def get_latest_run(self) -> Optional[RunRecord]:
        cursor = await self._conn.execute(
            "SELECT * FROM run_history ORDER BY started_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return RunRecord(
            run_id=row["run_id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            total_candidates=row["total_candidates"],
            checked=row["checked"],
            available=row["available"],
            errors=row["errors"],
        )

    async def get_setting(self, key: str) -> Optional[str]:
        cursor = await self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str):
        await self._conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        await self._conn.commit()
