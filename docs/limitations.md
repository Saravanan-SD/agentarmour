# Known Limitations

Stated plainly, not hidden in fine print.

## Single-Process Only

The breaker's state machine (`BreakerStateMachine`), the contamination guard (`CascadeGuard`), the registry (`BreakerRegistry`), and AgentBudget's registry all use `asyncio.Lock` internally. This correctly prevents race conditions *within one running Python process*, multiple async tasks failing at the same instant will never corrupt the failure counter or the spend counter.

It does **not** coordinate across multiple processes. If you run several replicas of your service (separate containers, separate pods), each one creates its own independent breaker and its own independent budget, each with its own independent state. One replica tripping OPEN does not inform the others, and a global spend limit is global only to one process, not the fleet. They each only see their own slice of traffic.

**Verified directly:** every lock in the codebase is a plain `asyncio.Lock()`. There is no Redis or other distributed coordination mechanism. This is confirmed by test: 500 concurrent budget records sum exactly, and two concurrent runs stay isolated, both within one process.

**If this matters to you:** for a single-instance deployment, this has no effect at all. For a horizontally scaled deployment, each replica protects itself, not the fleet as a whole. A proper fix would mean moving state out of process memory and into something shared, like Redis, which is a meaningfully larger piece of work than anything else in this library and has not been built.

## Budget Usage Counts Only On Success

AgentBudget records a node's tokens when the node **finishes successfully**. The `@budget.track` decorator totals the reported usage after the wrapped function returns.

It does **not** count tokens from a node that raises partway through. If a node calls the model, burns 2,000 tokens, and then throws before returning, those tokens are real money spent but they are not recorded in this version.

**If this matters to you:** the undercount is bounded by one node's worth of calls, and it only happens on the failure path. For steady-state accounting it has no effect. A fix would mean recording usage incrementally as each `report()` lands rather than in one batch at the end, which is a change to the buffer model and has not been built.

## Budget Token Capture Depends On The Provider

The LangChain callback handler reads token counts from the LLM response's `llm_output`. This works when the provider returns usage there, which most do.

It does **not** invent counts when the provider omits them. Some models, some streaming modes, and some providers return no usage metadata at all. In those cases the callback records nothing for that call, and you must fall back to `report()` with counts you supply yourself.

**Verified directly:** `_extract_usage` returns `None` when model name, prompt tokens, or completion tokens are missing, rather than guessing. A missing count is a silent zero, not an error, so if your totals look low, check that your provider actually returns usage.

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
