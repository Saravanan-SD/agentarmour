# Getting Started

## Install

```bash
pip install agentarmour-toolkit
```

This installs only two dependencies: `pydantic` and `structlog`. Verified with a clean install: 7 packages total, nothing else.

For LangGraph integration:

```bash
pip install agentarmour-toolkit[langgraph]
```

For the Streamlit dashboard:

```bash
pip install agentarmour-toolkit[dashboard]
```

## Your First Protected Node

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

That's the entire integration. One decorator.

## What Happens Underneath

The breaker tracks every call to `research_node`. If it fails 3 times within the configured window, the breaker trips OPEN. While OPEN, the real `research_node` is skipped entirely, the `CacheStrategy` serves the last good response instead.

CLOSED ──(3 failures)──► OPEN

▲   │

│ (30s elapses)

│   │

└──(probe succeeds)── HALF_OPEN ◄┘

After the cooldown, exactly one test call is allowed through. Succeed, and the breaker closes again. Fail, and it stays open with the timer reset.

## Checking Breaker State

```python
print(breaker.state)        # BreakerState.CLOSED / OPEN / HALF_OPEN
print(breaker.metrics)      # dict of counts, success rate, etc.
```

## Next Steps

- See [Fallback Strategies](strategies.md) for the four ways to respond when a breaker trips
- See [Cross-Agent Guard](guard.md) for protecting downstream nodes from corrupted state