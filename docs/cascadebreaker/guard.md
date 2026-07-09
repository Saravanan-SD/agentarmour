# Cross-Agent Contamination Guard

A circuit breaker catches loud failures, the kind that raise exceptions. It does not catch an agent that *appears* to succeed while quietly writing corrupted data into shared state, which the next agent then trusts and builds on without question.

`CascadeGuard` closes that gap.

## The Problem It Solves

Agent A fails partway through → writes a malformed value to "extracted_entities"

Agent B reads "extracted_entities" → trusts it → produces wrong output

Agent C inherits Agent B's wrong output → compounds the error

No exception is ever raised. The pipeline looks healthy. The output is wrong.

## Basic Usage

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

If `extract_node` raises an exception, `extracted_entities` is quarantined for 300 seconds. Any node that declares `reads_from=["extracted_entities"]` during that window receives `None` for that field instead of whatever `extract_node` may have partially written.

## Parameters

**`quarantine_on_failure`** — list of state keys to quarantine if this node raises an exception. These are fields this node is responsible for producing.

**`reads_from`** — list of state keys this node depends on. Before the node runs, each of these is checked. If quarantined, it's replaced with `None` (or a value from `field_defaults`, if provided).

**`field_defaults`** — optional dict mapping field names to a replacement value other than `None`.

```python
@guard.protect_node(
    "analyse_agent",
    reads_from=["extracted_entities"],
    field_defaults={"extracted_entities": []},
)
```

## Strict Mode

By default, a quarantined field is silently replaced with `None`. If you'd rather fail loudly during development:

```python
guard = CascadeGuard(strict_mode=True)
```

In strict mode, reading a quarantined field raises `ContaminatedStateError` instead of substituting a default.

## Manually Managing Quarantine

```python
await guard.quarantine_field("extracted_entities", source_node="extract_agent", reason="manual flag")
await guard.lift_quarantine("extracted_entities")

guard.is_quarantined("extracted_entities")  # bool
guard.quarantined_fields                    # list of currently quarantined fields
guard.metrics                               # dict for dashboard/monitoring
```