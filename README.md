# CascadeBreaker

**Circuit breaker and self-healing layer for LangGraph multi-agent systems.**

Part of the [AgentArmour](https://github.com/Saravanan-SD/agentarmour) reliability suite.

![CI](https://github.com/Saravanan-SD/agentarmour/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![PyPI](https://img.shields.io/pypi/v/agentarmour)

## Why This Exists

Existing circuit breaker tools for LLMs (`llm-circuit`, `aeneassoft`, `llm-cascade`) only protect against **LLM API provider outages**. OpenAI down, Anthropic rate-limited.

They do nothing about what actually breaks production multi-agent systems: an agent stuck in a reasoning loop, a hallucinated value silently poisoning shared state, one agent's failure cascading through every downstream node.

A March 2025 paper, *["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657)* (Cemri, Pan, Yang, Agrawal, Chopra, Tiwari, Keutzer, Parameswaran, Klein, Ramchandran, Zaharia, Gonzalez, and Stoica), analysed over 1,600 execution traces across seven multi-agent frameworks and identified 14 distinct failure modes. None of them involve an API going down.

CascadeBreaker operates one level below the API, at the individual LangGraph node.

## Install

```bash
pip install agentarmour
```

Core install pulls in only two dependencies: `pydantic` and `structlog`. Everything else is optional, installed only when you need it:

```bash
pip install agentarmour[langgraph]    # LangGraph/LangChain integration
pip install agentarmour[dashboard]    # Streamlit dashboard
pip install agentarmour[dev]          # pytest, ruff, dev tools
pip install agentarmour[all]          # everything
```

Verified: a clean install of the base package brings in exactly 7 packages total (the library, `pydantic`, `structlog`, and their own small dependencies), nothing else.

## Quick Start

```python
from agentarmour.cascadebreaker import CircuitBreaker, BreakerConfig
from agentarmour.cascadebreaker.strategies import CacheStrategy

breaker = CircuitBreaker(
    name="research_agent",
    config=BreakerConfig(failure_threshold=3, recovery_timeout=30),
    fallback_strategy=CacheStrategy(max_age_seconds=300),
)

@breaker.protect
async def research_node(state: dict) -> dict:
    result = await llm_chain.ainvoke(state["query"])
    return {**state, "research": result}
```

One decorator. The breaker cycles through CLOSED → OPEN → HALF_OPEN automatically based on real failures, no manual intervention needed.

## The Four Fallback Strategies

When the breaker is OPEN, something still has to respond. Pick the strategy that fits each node.

### CacheStrategy — return the last good response

```python
from agentarmour.cascadebreaker.strategies import CacheStrategy

breaker = CircuitBreaker(
    name="summary_agent",
    config=BreakerConfig(failure_threshold=3),
    fallback_strategy=CacheStrategy(max_age_seconds=300),
)
```

Good when output doesn't shift drastically minute to minute, and "slightly stale but correct" beats nothing. The cache is populated automatically every time the real agent succeeds.

### DegradeStrategy — fall back to a simpler agent

```python
from agentarmour.cascadebreaker.strategies import DegradeStrategy

async def cheap_backup_agent(state: dict) -> dict:
    result = await gpt35_chain.ainvoke(state["query"])
    return {**state, "research": result}

breaker = CircuitBreaker(
    name="research_agent",
    config=BreakerConfig(failure_threshold=2),
    fallback_strategy=DegradeStrategy(backup_fn=cheap_backup_agent, confidence_override=0.6),
)
```

Good when you have a cheaper, more reliable backup model available.

### EscalateStrategy — alert a human

```python
from agentarmour.cascadebreaker.strategies import EscalateStrategy

async def notify_oncall(breaker_name: str, state: dict, context: dict) -> dict | None:
    await slack_client.post(channel="#incidents", text=f"Circuit '{breaker_name}' OPEN")
    return None  # don't block the pipeline waiting for a human

breaker = CircuitBreaker(
    name="payment_validation_agent",
    config=BreakerConfig(failure_threshold=1),
    fallback_strategy=EscalateStrategy(escalation_fn=notify_oncall, notification_only=True),
)
```

Good for anything where a wrong answer is worse than a delayed one.

### DecomposeStrategy — break the task into smaller pieces

```python
from agentarmour.cascadebreaker.strategies import DecomposeStrategy

async def split_into_chunks(state: dict) -> list[dict]:
    return [{**state, "chunk": c} for c in state["documents"]]

async def process_chunk(sub_state: dict) -> dict:
    return {"result": await llm.ainvoke(sub_state["chunk"])}

breaker = CircuitBreaker(
    name="batch_summary_agent",
    config=BreakerConfig(failure_threshold=2),
    fallback_strategy=DecomposeStrategy(decompose_fn=split_into_chunks, execute_fn=process_chunk),
)
```

Good when the failure mode is the task being too large or complex for one agent call.

## Cross-Agent Contamination Guard

A circuit breaker catches loud failures. It does not catch an agent that "succeeds" while quietly writing corrupted data into shared state, which the next agent then trusts and builds on. `CascadeGuard` closes that gap.

```python
from agentarmour.cascadebreaker import CascadeGuard

guard = CascadeGuard(quarantine_ttl_seconds=300)

@guard.protect_node(
    "extract_agent",
    quarantine_on_failure=["extracted_entities"],
    reads_from=["raw_document"],
)
async def extract_node(state: dict) -> dict:
    state["extracted_entities"] = await extract_llm.ainvoke(state["raw_document"])
    return state

@guard.protect_node(
    "analyse_agent",
    reads_from=["extracted_entities"],
)
async def analyse_node(state: dict) -> dict:
    entities = state.get("extracted_entities")
    if entities is None:
        return {**state, "analysis": "Entities unavailable, upstream agent degraded."}
    return {**state, "analysis": await analyse_llm.ainvoke(entities)}
```

If `extract_agent` fails, `extracted_entities` gets quarantined for 5 minutes. `analyse_node` receives `None` for that field instead of inheriting garbage, and handles it explicitly.

## Debugging Without Crashing the Pipeline

When an agent fails, the breaker swallows the exception so your pipeline keeps running, but the full original stack trace is preserved and attached to the returned state:

```python
result = await protected_node(state)

if "__cascadebreaker_traceback__" in result:
    print("Something failed upstream:")
    print(result["__cascadebreaker_traceback__"])
```

The trace includes the exact file, line, and function where the original exception occurred, even though nothing was ever raised to the caller.

## Audit Ledger

Every failure and state transition is logged to a local SQLite file, zero extra dependencies (built on Python's standard `sqlite3` + `asyncio.to_thread`, so it works even in the base install).

```python
from agentarmour.cascadebreaker.storage.sqlite_ledger import SQLiteLedger

breaker = CircuitBreaker(
    name="research_agent",
    config=BreakerConfig(),
    fallback_strategy=CacheStrategy(),
    ledger=SQLiteLedger(),  # writes to cascadebreaker.db by default
)
```

Inspect it from the terminal:

```bash
agentarmour ledger summary
agentarmour ledger failures --breaker research_agent --limit 10
agentarmour ledger transitions
```

Or visually, with the dashboard (requires `pip install agentarmour[dashboard]`):

```bash
streamlit run agentarmour/cascadebreaker/dashboard/app.py
```

Shows live metrics, current state per breaker, a failure timeline chart, and recent failure/transition tables, all reading from the same SQLite file.

## Performance

Benchmarked across 5,000 calls: wrapping a node with `@breaker.protect` adds roughly **4 microseconds** of overhead per call. Against a typical LLM call (200ms to 3000ms), that's well under 0.01% of total latency. The wrapper will never be the bottleneck in a real pipeline.

## Known Limitations

Stated plainly, not hidden:

- **Single-process only.** The breaker's state machine uses `asyncio.Lock`, which coordinates concurrent tasks within one Python process. Running multiple replicas (separate containers, separate pods) means each one tracks its own independent circuit state. They do not share state across processes.
- **Postgres ledger not yet built.** `SQLiteLedger` is fully implemented and tested. A `PostgresLedger` for centralized, multi-instance audit logging is planned but not built, since it has not yet been tested against a real Postgres instance.

## Architecture
agentarmour/cascadebreaker/

├── config.py        # Pydantic configuration (BreakerConfig, StorageConfig)

├── states.py        # BreakerStateMachine — CLOSED/OPEN/HALF_OPEN logic

├── breaker.py        # CircuitBreaker — decorator + core execution

├── strategies.py      # CACHE / DEGRADE / ESCALATE / DECOMPOSE

├── guard.py         # CascadeGuard — cross-agent contamination protection

├── registry.py       # BreakerRegistry — process-wide discovery

├── cli.py          # Terminal inspection of the audit ledger

├── storage/         # SQLite audit ledger (stdlib only, zero dependencies)

└── dashboard/        # Streamlit live dashboard

## Running the Examples

```bash
# Zero dependencies needed
python examples/basic_usage.py

# Requires pip install agentarmour[langgraph]
python examples/langgraph_example.py
```

## Running Tests

```bash
pip install agentarmour[dev]
pytest tests/ -v
```

24 tests, covering the state machine, fallback paths, timeout handling, traceback capture, and the audit ledger. CI runs this automatically across Python 3.10, 3.11, and 3.12 on every push.

## Roadmap

CascadeBreaker is the first module in the AgentArmour suite. Planned next, in order:

- **AgentBudget** — cost and rate-limit control
- **ToolGuard** — protection against hallucinated tool calls
- **AgentMock** — reliable testing for non-deterministic agents

Each module ships completely before the next one starts.

## Credit

The failure taxonomy this project is built around comes from Mert Cemri, Melissa Z. Pan, Shuyi Yang, Lakshya A. Agrawal, Bhavya Chopra, Rishabh Tiwari, Kurt Keutzer, Aditya Parameswaran, Dan Klein, Kannan Ramchandran, Matei Zaharia, Joseph E. Gonzalez, and Ion Stoica. *["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657)*, March 2025.

## License

MIT