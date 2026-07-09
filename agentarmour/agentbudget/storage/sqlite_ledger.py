# agentarmour/agentbudget/storage/sqlite_ledger.py
from __future__ import annotations

import asyncio
import sqlite3

from agentarmour.agentbudget.usage import BudgetEvent


class SQLiteBudgetLedger:
    def __init__(
        self, db_path: str = "agentarmour.db", table_prefix: str = "ab_"
    ) -> None:
        self._db_path = db_path
        self._prefix = table_prefix
        self._initialised = False
        self._init_lock = asyncio.Lock()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _create_tables_sync(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._prefix}events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node TEXT NOT NULL,
                    run_id TEXT,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    state TEXT NOT NULL,
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

    def _insert_event_sync(self, event: BudgetEvent) -> None:
        conn = self._connect()
        try:
            conn.execute(
                f"""
                INSERT INTO {self._prefix}events
                (node, run_id, input_tokens, output_tokens,
                 cost_usd, state, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.node,
                    event.run_id,
                    event.input_tokens,
                    event.output_tokens,
                    event.cost_usd,
                    event.state,
                    event.timestamp,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    async def log_event(self, event: BudgetEvent) -> None:
        await self._ensure_initialised()
        await asyncio.to_thread(self._insert_event_sync, event)

    async def close(self) -> None:
        return None