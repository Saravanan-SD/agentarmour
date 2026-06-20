"""Unit tests for the SQLite audit ledger."""

from __future__ import annotations

import os
import pytest
import aiosqlite

from agentarmour.cascadebreaker import CircuitBreaker, BreakerConfig
from agentarmour.cascadebreaker.strategies import CacheStrategy
from agentarmour.cascadebreaker.storage.sqlite_ledger import SQLiteLedger

TEST_DB = "test_storage_pytest.db"


@pytest.fixture
def ledger():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    yield SQLiteLedger(db_path=TEST_DB)
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


class TestSQLiteLedger:
    @pytest.mark.asyncio
    async def test_failure_is_persisted(self, ledger: SQLiteLedger) -> None:
        breaker = CircuitBreaker(
            name="ledger_test",
            config=BreakerConfig(failure_threshold=1, call_timeout=None),
            fallback_strategy=CacheStrategy(),
            ledger=ledger,
        )

        @breaker.protect
        async def failing_node(state: dict) -> dict:
            raise RuntimeError("boom")

        await failing_node({})

        async with aiosqlite.connect(TEST_DB) as db:
            async with db.execute("SELECT breaker_name, error_message FROM cb_failures") as cursor:
                rows = await cursor.fetchall()

        assert len(rows) == 1
        assert rows[0][0] == "ledger_test"
        assert rows[0][1] == "boom"

    @pytest.mark.asyncio
    async def test_transition_is_persisted(self, ledger: SQLiteLedger) -> None:
        breaker = CircuitBreaker(
            name="ledger_transition_test",
            config=BreakerConfig(failure_threshold=1, call_timeout=None),
            fallback_strategy=CacheStrategy(),
            ledger=ledger,
        )

        @breaker.protect
        async def failing_node(state: dict) -> dict:
            raise RuntimeError("boom")

        await failing_node({})

        async with aiosqlite.connect(TEST_DB) as db:
            async with db.execute(
                "SELECT breaker_name, from_state, to_state FROM cb_transitions"
            ) as cursor:
                rows = await cursor.fetchall()

        assert len(rows) == 1
        assert rows[0] == ("ledger_transition_test", "CLOSED", "OPEN")