"""
SQLite-backed audit ledger for CascadeBreaker.

Uses Python's built-in `sqlite3` module, so no extra dependency is
required to use this feature. Database operations run in a background
thread via asyncio.to_thread, so they never block the event loop.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3

from agentarmour.cascadebreaker.states import FailureRecord, StateTransition
from agentarmour.cascadebreaker.storage.base import AuditLedger


class SQLiteLedger(AuditLedger):
    """Persists circuit breaker failures and state transitions to a local
    SQLite file, using only Python's standard library.

    Tables are created lazily on first write, so no separate async setup
    step is required. Safe to share across multiple CircuitBreaker
    instances in the same process.

    Args:
        db_path: Path to the SQLite database file. Created if it does not exist.
        table_prefix: Prefix applied to all table names. Default "cb_".
    """

    def __init__(
        self, db_path: str = "agentarmour.db", table_prefix: str = "cb_"
    ) -> None:
        self._db_path = db_path
        self._prefix = table_prefix
        self._initialised = False
        self._init_lock = asyncio.Lock()

    def _connect(self) -> sqlite3.Connection:
        # Each call opens its own connection. sqlite3 connections are not
        # safe to share across threads, and to_thread may use a different
        # thread on each call.
        return sqlite3.connect(self._db_path)

    def _create_tables_sync(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
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
            conn.execute(
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
            conn.commit()
        finally:
            conn.close()

    async def _ensure_initialised(self) -> None:
        if self._initialised:
            return
        async with self._init_lock:
            if self._initialised:
                return
            await asyncio.to_thread(self._create_tables_sync)
            self._initialised = True

    def _insert_failure_sync(self, record: FailureRecord) -> None:
        conn = self._connect()
        try:
            conn.execute(
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
            conn.commit()
        finally:
            conn.close()

    async def log_failure(self, record: FailureRecord) -> None:
        await self._ensure_initialised()
        await asyncio.to_thread(self._insert_failure_sync, record)

    def _insert_transition_sync(self, transition: StateTransition) -> None:
        conn = self._connect()
        try:
            conn.execute(
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
            conn.commit()
        finally:
            conn.close()

    async def log_transition(self, transition: StateTransition) -> None:
        await self._ensure_initialised()
        await asyncio.to_thread(self._insert_transition_sync, transition)

    async def close(self) -> None:
        # Connections are opened and closed per-operation, so there's
        # nothing persistent to release here.
        return None