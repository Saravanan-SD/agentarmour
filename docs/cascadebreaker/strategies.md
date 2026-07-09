# Fallback Strategies

When a breaker trips OPEN, something still has to respond. CascadeBreaker ships four strategies, each suited to a different situation.

## CacheStrategy

Returns the last successful response.

```python
from agentarmour.cascadebreaker.strategies import CacheStrategy

breaker = CircuitBreaker(
    name="summary_agent",
    config=BreakerConfig(failure_threshold=3),
    fallback_strategy=CacheStrategy(max_age_seconds=300),
)
```

The cache is populated automatically every time the real agent succeeds, no manual wiring needed. Good when output is reasonably stable minute to minute, and "slightly stale but correct" beats nothing.

If no cached entry exists yet, or the cache is empty, the returned state includes `__cascadebreaker_cache_miss__: True` so you can detect this case.

## DegradeStrategy

Delegates to a simpler, cheaper backup agent.

```python
from agentarmour.cascadebreaker.strategies import DegradeStrategy

async def cheap_backup_agent(state: dict) -> dict:
    result = await gpt35_chain.ainvoke(state["query"])
    return {**state, "research": result}

breaker = CircuitBreaker(
    name="research_agent",
    config=BreakerConfig(failure_threshold=2),
    fallback_strategy=DegradeStrategy(
        backup_fn=cheap_backup_agent,
        confidence_override=0.6,
    ),
)
```

`confidence_override` is attached to the result metadata, useful if downstream logic wants to treat degraded responses differently from full-confidence ones.

## EscalateStrategy

Alerts a human and either waits briefly for a response or passes the state through flagged for review.

```python
from agentarmour.cascadebreaker.strategies import EscalateStrategy

async def notify_oncall(breaker_name: str, state: dict, context: dict) -> dict | None:
    await slack_client.post(channel="#incidents", text=f"Circuit '{breaker_name}' OPEN")
    return None  # don't block the pipeline waiting for a human

breaker = CircuitBreaker(
    name="payment_validation_agent",
    config=BreakerConfig(failure_threshold=1),
    fallback_strategy=EscalateStrategy(
        escalation_fn=notify_oncall,
        notification_only=True,
    ),
)
```

Set `notification_only=False` if you want the breaker to actually wait for `escalation_fn` to return a value, with `human_timeout_seconds` controlling how long it waits before giving up.

## DecomposeStrategy

Breaks a task into smaller sub-tasks and runs each independently.

```python
from agentarmour.cascadebreaker.strategies import DecomposeStrategy

async def split_into_chunks(state: dict) -> list[dict]:
    return [{**state, "chunk": c} for c in state["documents"]]

async def process_chunk(sub_state: dict) -> dict:
    return {"result": await llm.ainvoke(sub_state["chunk"])}

breaker = CircuitBreaker(
    name="batch_summary_agent",
    config=BreakerConfig(failure_threshold=2),
    fallback_strategy=DecomposeStrategy(
        decompose_fn=split_into_chunks,
        execute_fn=process_chunk,
    ),
)
```

Sub-tasks run concurrently via `asyncio.gather`. If a `merge_fn` isn't provided, results are merged with a simple dict update onto the original state.

## Choosing a Strategy

| Situation | Strategy |
|---|---|
| Output doesn't change quickly | `CacheStrategy` |
| You have a cheaper backup model | `DegradeStrategy` |
| Wrong answer is worse than a delayed one | `EscalateStrategy` |
| Task may be too complex for one call | `DecomposeStrategy` |