"""
SQLite-backed audit ledger for CascadeBreaker.

Requires the optional `aiosqlite` dependency:
    uv add --optional storage aiosqlite
"""

from __future__ import annotations

import asyncio
import json

try:
    import aiosqlite
except ImportError as exc:
    raise ImportError(
        "SQLiteLedger requires the 'aiosqlite' package. "
        "Install it with: uv add --optional storage aiosqlite"
    ) from exc

from agentarmour.cascadebreaker.states import FailureRecord, StateTransition
from agentarmour.cascadebreaker.storage.base import AuditLedger


class SQLiteLedger(AuditLedger):
    """Persists circuit breaker failures and state transitions to SQLite.

    Tables are created lazily on first write, so no separate async setup
    step is required. Safe to share across multiple CircuitBreaker
    instances in the same process.

    Args:
        db_path: Path to the SQLite database file. Created if it does not exist.
        table_prefix: Prefix applied to all table names. Default "cb_".
    """

    def __init__(
        self, db_path: str = "cascadebreaker.db", table_prefix: str = "cb_"
    ) -> None:
        self._db_path = db_path
        self._prefix = table_prefix
        self._initialised = False
        self._init_lock = asyncio.Lock()

    async def _ensure_initialised(self) -> None:
        if self._initialised:
            return
        async with self._init_lock:
            if self._initialised:
                return
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._prefix}failures (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        breaker_name TEXT NOT NULL,
                        category TEXT NOT NULL,
                        error_type TEXT NOT NULL,
                        error_message TEXT NOT NULL,
                        traceback_str TEXT,
                        latency_ms REAL,
                        timestamp REAL NOT NULL,
                        metadata TEXT
                    )
                    """
                )
                await db.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._prefix}transitions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        breaker_name TEXT NOT NULL,
                        from_state TEXT NOT NULL,
                        to_state TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        failure_count INTEGER,
                        timestamp REAL NOT NULL
                    )
                    """
                )
                await db.commit()
            self._initialised = True

    async def log_failure(self, record: FailureRecord) -> None:
        await self._ensure_initialised()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                f"""
                INSERT INTO {self._prefix}failures
                (breaker_name, category, error_type, error_message,
                 traceback_str, latency_ms, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.breaker_name,
                    record.category.value,
                    record.error_type,
                    record.error_message,
                    record.traceback_str,
                    record.latency_ms,
                    record.timestamp,
                    json.dumps(record.metadata),
                ),
            )
            await db.commit()

    async def log_transition(self, transition: StateTransition) -> None:
        await self._ensure_initialised()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                f"""
                INSERT INTO {self._prefix}transitions
                (breaker_name, from_state, to_state, reason, failure_count, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    transition.breaker_name,
                    transition.from_state.value,
                    transition.to_state.value,
                    transition.reason,
                    transition.failure_count,
                    transition.timestamp,
                ),
            )
            await db.commit()

    async def close(self) -> None:
        # Connections are opened per-operation and closed automatically,
        # so there's nothing persistent to release here.
        return None