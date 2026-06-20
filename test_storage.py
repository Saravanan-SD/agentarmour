import logging
import structlog
logging.basicConfig(level=logging.WARNING)
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

import asyncio
import os
import sqlite3

from agentarmour.cascadebreaker import CircuitBreaker, BreakerConfig
from agentarmour.cascadebreaker.strategies import CacheStrategy
from agentarmour.cascadebreaker.storage.sqlite_ledger import SQLiteLedger

DB_PATH = "test_audit.db"

# Start fresh each run
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

ledger = SQLiteLedger(db_path=DB_PATH)

breaker = CircuitBreaker(
    name="storage_test_agent",
    config=BreakerConfig(failure_threshold=2, recovery_timeout=1.0, call_timeout=None),
    fallback_strategy=CacheStrategy(),
    ledger=ledger,
)


@breaker.protect
async def flaky_node(state: dict) -> dict:
    raise RuntimeError("intentional failure for storage test")


async def main():
    print("Triggering 2 failures to populate the audit ledger...")
    await flaky_node({"x": 1})
    await flaky_node({"x": 2})

    print(f"Breaker state: {breaker.state.value}")
    print()
    print("Reading back what was written to SQLite...")
    print()

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT breaker_name, category, error_message FROM cb_failures") as cursor:
            rows = await cursor.fetchall()
            print(f"cb_failures table — {len(rows)} row(s):")
            for row in rows:
                print(f"  {row}")

        print()
        async with db.execute("SELECT breaker_name, from_state, to_state, reason FROM cb_transitions") as cursor:
            rows = await cursor.fetchall()
            print(f"cb_transitions table — {len(rows)} row(s):")
            for row in rows:
                print(f"  {row}")


asyncio.run(main())