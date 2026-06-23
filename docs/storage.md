# Audit Ledger

Every failure and state transition a breaker records can be persisted to a local SQLite file, so they survive process restarts and can be inspected later.

## Zero Extra Dependencies

The ledger is built on Python's standard `sqlite3` module plus `asyncio.to_thread`, no extra package required, even though `sqlite3` is normally synchronous. Database writes run in a background thread so they never block your event loop.

## Basic Usage

```python
from agentarmour.cascadebreaker import CircuitBreaker, BreakerConfig
from agentarmour.cascadebreaker.strategies import CacheStrategy
from agentarmour.cascadebreaker.storage.sqlite_ledger import SQLiteLedger

breaker = CircuitBreaker(
    name="research_agent",
    config=BreakerConfig(),
    fallback_strategy=CacheStrategy(),
    ledger=SQLiteLedger(),  # writes to cascadebreaker.db by default
)
```

Pass a custom path if you'd rather control where the file lives:

```python
SQLiteLedger(db_path="logs/my_app_audit.db")
```

## What Gets Stored

Two tables are created automatically on first write.

**`cb_failures`** — one row per failure: breaker name, category, error type, error message, full traceback, latency, timestamp, and any custom metadata.

**`cb_transitions`** — one row per state change: breaker name, from-state, to-state, reason, failure count at time of transition, timestamp.

The `cb_` prefix can be customized:

```python
SQLiteLedger(table_prefix="myapp_")
```

## Reading the Data Directly

```python
import sqlite3

conn = sqlite3.connect("cascadebreaker.db")
rows = conn.execute("SELECT * FROM cb_failures ORDER BY timestamp DESC LIMIT 10").fetchall()
```

Or use the [CLI](cli.md) or [Dashboard](dashboard.md) instead of writing SQL by hand.

## A Custom Ledger Backend

`SQLiteLedger` implements an abstract base, `AuditLedger`. Anyone can write their own backend (Postgres, a remote API, anything) by implementing three methods:

```python
from agentarmour.cascadebreaker.storage.base import AuditLedger

class MyCustomLedger(AuditLedger):
    async def log_failure(self, record):
        ...

    async def log_transition(self, transition):
        ...

    async def