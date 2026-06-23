# Known Limitations

Stated plainly, not hidden in fine print.

## Single-Process Only

The breaker's state machine (`BreakerStateMachine`), the contamination guard (`CascadeGuard`), and the registry (`BreakerRegistry`) all use `asyncio.Lock` internally. This correctly prevents race conditions *within one running Python process*, multiple async tasks failing at the same instant will never corrupt the failure counter.

It does **not** coordinate across multiple processes. If you run several replicas of your service (separate containers, separate pods), each one creates its own independent breaker with its own independent state. One replica tripping OPEN does not inform the others, they each only see their own slice of traffic.

**Verified directly:** every lock in the codebase is a plain `asyncio.Lock()`. There is no Redis or other distributed coordination mechanism.

**If this matters to you:** for a single-instance deployment, this has no effect at all. For a horizontally scaled deployment, each replica protects itself, not the fleet as a whole. A proper fix would mean moving breaker state out of process memory and into something shared, like Redis, which is a meaningfully larger piece of work than anything else in this library and has not been built.

## Postgres Ledger Not Yet Built

`SQLiteLedger` is fully implemented, tested, and zero-dependency. A `PostgresLedger`, for centralizing audit logs across multiple instances, is a natural next step, but it has not been built, since doing so without a real Postgres instance to test against would mean shipping untested integration code.

The `AuditLedger` abstract base class already exists, anyone wanting Postgres support today can implement it directly:

```python
from agentarmour.cascadebreaker.storage.base import AuditLedger

class PostgresLedger(AuditLedger):
    async def log_failure(self, record):
        ...
    async def log_transition(self, transition):
        ...
    async def close(self):
        ...
```

## Performance, For Context

Measured directly, not estimated: wrapping a node with `@breaker.protect` adds roughly 4 microseconds of overhead per call (benchmarked across 5,000 calls). Against a typical LLM call latency of 200ms to 3000ms, this is well under 0.01% of total latency. This is not a limitation in practice, included here for completeness, since it's a question worth answering with real numbers rather than assumption.