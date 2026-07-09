# tests/unit/test_agentbudget_tracker.py
import pytest

from agentarmour.agentbudget.config import (
    BudgetConfig,
    ModelPrice,
    OverBudgetAction,
)
from agentarmour.agentbudget.storage.sqlite_ledger import SQLiteBudgetLedger
from agentarmour.agentbudget.tracker import Budget, BudgetExceeded, report


PRICES = {"m": ModelPrice(input_per_million=3.0, output_per_million=15.0)}


# ---------- decorator basics ----------

@pytest.mark.asyncio
async def test_tracked_node_returns_its_value():
    budget = Budget(BudgetConfig(prices=PRICES))

    @budget.track
    async def node(x):
        return x + 1

    result = await node(41)
    assert result == 42


@pytest.mark.asyncio
async def test_wraps_keeps_node_name():
    budget = Budget(BudgetConfig(prices=PRICES))

    @budget.track
    async def my_node():
        return None

    # functools.wraps keeps the real name, not "wrapper"
    assert my_node.__name__ == "my_node"


# ---------- usage capture via report() ----------

@pytest.mark.asyncio
async def test_report_tokens_are_recorded():
    budget = Budget(BudgetConfig(prices=PRICES))

    @budget.track
    async def node():
        report("m", 1000, 500)

    await node()

    usage = budget.registry._nodes["node"]
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 500
    assert usage.cost_usd == pytest.approx(0.0105)
    assert usage.calls == 1


@pytest.mark.asyncio
async def test_multiple_reports_sum_in_one_node():
    budget = Budget(BudgetConfig(prices=PRICES))

    @budget.track
    async def node():
        report("m", 1000, 0)
        report("m", 1000, 0)

    await node()

    usage = budget.registry._nodes["node"]
    assert usage.input_tokens == 2000


@pytest.mark.asyncio
async def test_report_outside_node_is_safe():
    # calling report with no active node must not error
    report("m", 100, 100)  # should silently do nothing


# ---------- buffer isolation ----------

@pytest.mark.asyncio
async def test_buffer_resets_between_runs():
    budget = Budget(BudgetConfig(prices=PRICES))

    @budget.track
    async def node():
        report("m", 100, 0)

    await node()
    await node()

    # two separate runs, each buffered on its own, node total is both
    usage = budget.registry._nodes["node"]
    assert usage.calls == 2
    assert usage.input_tokens == 200


# ---------- action: WARN ----------

@pytest.mark.asyncio
async def test_warn_action_does_not_raise():
    cfg = BudgetConfig(
        prices=PRICES,
        global_limit_usd=0.001,   # tiny, so any call exceeds
        action=OverBudgetAction.WARN,
    )
    budget = Budget(cfg)

    @budget.track
    async def node():
        report("m", 1000, 1000)

    # WARN means it logs and keeps going, no exception
    await node()


# ---------- action: BLOCK ----------

@pytest.mark.asyncio
async def test_block_action_raises_when_exceeded():
    cfg = BudgetConfig(
        prices=PRICES,
        global_limit_usd=0.001,
        action=OverBudgetAction.BLOCK,
    )
    budget = Budget(cfg)

    @budget.track
    async def node():
        report("m", 1000, 1000)

    with pytest.raises(BudgetExceeded):
        await node()


@pytest.mark.asyncio
async def test_block_does_not_raise_when_within():
    cfg = BudgetConfig(
        prices=PRICES,
        global_limit_usd=100.0,   # generous
        action=OverBudgetAction.BLOCK,
    )
    budget = Budget(cfg)

    @budget.track
    async def node():
        report("m", 100, 100)

    # within budget, BLOCK stays quiet
    await node()


# ---------- ledger integration through the decorator ----------

@pytest.mark.asyncio
async def test_decorator_writes_to_ledger(tmp_path):
    import sqlite3

    db = str(tmp_path / "test.db")
    ledger = SQLiteBudgetLedger(db_path=db)
    budget = Budget(BudgetConfig(prices=PRICES), ledger=ledger)

    @budget.track
    async def node():
        report("m", 1000, 500)

    await node()

    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT node, input_tokens, output_tokens FROM ab_events"
        ).fetchone()
    finally:
        conn.close()

    assert row == ("node", 1000, 500)