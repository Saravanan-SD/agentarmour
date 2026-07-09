# AgentBudget

A circuit breaker catches failures that raise. AgentBudget catches a quieter one: token and cost blowups that never raise anything at all. The pipeline runs clean, the output looks fine, and the only signal is the bill at the end of the month.

`AgentBudget` puts a ceiling on spend while the run is still happening.

## The Problem It Solves

Agent A enters a retry loop → each pass is a fresh LLM call → tokens climb

Agent B fans out to five sub-agents → each one calls the model → cost multiplies per branch

Nobody set a ceiling → the run finishes → the spend is only visible after the fact

No exception is ever raised. The graph looks healthy. The cost is not.

## Basic Usage

```python
from agentarmour.agentbudget import (
    Budget,
    BudgetConfig,
    ModelPrice,
    report,
    run_context,
)

config = BudgetConfig(
    prices={
        "my-model": ModelPrice(input_per_million=3.0, output_per_million=15.0),
    },
    run_limit_usd=5.0,
)
budget = Budget(config)

@budget.track
async def research_node(state: dict) -> dict:
    answer = await research_llm.ainvoke(state["question"])
    report("my-model", input_tokens=1200, output_tokens=400)
    return {**state, "answer": answer}
```

Each time `research_node` runs, its reported tokens are priced, added to the node, run, and global totals, and checked against your limits. If the run total crosses `run_limit_usd`, the configured action fires.

Wrap a whole pipeline run in `run_context()` so per-run limits have something to count against:

```python
with run_context():
    await research_node(state)
    await analyse_node(state)
```

Without it, node and global limits still work, but run-scoped limits have no run to track.

## Reporting Token Usage

AgentBudget needs to know how many tokens each call used. Two ways to tell it.

**Manual** — call `report()` inside the node with the counts your provider returned:

```python
report("my-model", input_tokens=1200, output_tokens=400)
```

**LangChain callback** — if you use LangChain, attach the handler and it reports for you:

```python
handler = budget.callback_handler()
answer = await research_llm.ainvoke(state["question"], config={"callbacks": [handler]})
```

The callback reads token counts off the LLM response automatically. It requires the optional dependency: `pip install agentarmour-toolkit[agentbudget]`.

## Scopes

Three limits, checked on every recorded call. Any of them can be left unset.

**`node_limit_usd`** — cap on a single node's total spend, summed across every time it runs.

**`run_limit_usd`** — cap on one pipeline run, tracked through `run_context()`.

**`global_limit_usd`** — cap on everything the `Budget` has ever seen, across all runs and nodes.

The verdict returned is always the worst of the three. If the node is fine but the run has exceeded, the state is exceeded.

## Actions

What happens when a limit is crossed, set by `action` in `BudgetConfig`:

**`WARN`** (default) — logs loudly and lets the node finish. Nothing is interrupted.

**`BLOCK`** — raises `BudgetExceeded` and stops the node before it returns.

```python
from agentarmour.agentbudget import OverBudgetAction

config = BudgetConfig(
    prices={...},
    run_limit_usd=5.0,
    action=OverBudgetAction.BLOCK,
)
```

A `warn_threshold` (default `0.8`) sets when a limit enters the warning state, at 80% of the cap by default, so you get a heads-up before the ceiling, not just at it.

## Audit Ledger

Pass a ledger and every recorded call is written to SQLite, in its own `ab_events` table, in the same database file CascadeBreaker uses:

```python
from agentarmour.agentbudget import SQLiteBudgetLedger

ledger = SQLiteBudgetLedger(db_path="agentarmour.db")
budget = Budget(config, ledger=ledger)
```

The two modules share the file but never the tables. Inspect it with `agentarmour budget summary`, or open the dashboard.