# tests/unit/test_agentbudget_registry.py
import asyncio
import pytest

from agentarmour.agentbudget.config import BudgetConfig
from agentarmour.agentbudget.breaker import BudgetState
from agentarmour.agentbudget.registry import (
    BudgetRegistry,
    run_context,
    current_run_id,
)


# ---------- contextvar / run id ----------

def test_no_run_id_by_default():
    assert current_run_id() is None


def test_run_context_sets_and_resets():
    assert current_run_id() is None
    with run_context() as rid:
        assert rid is not None
        assert current_run_id() == rid
    # reset after the block
    assert current_run_id() is None


def test_run_context_accepts_explicit_id():
    with run_context("my-run") as rid:
        assert rid == "my-run"
        assert current_run_id() == "my-run"


# ---------- record accumulates ----------

@pytest.mark.asyncio
async def test_record_accumulates_global_and_node():
    reg = BudgetRegistry(BudgetConfig())
    await reg.record("node_a", 100, 50, 0.01)
    await reg.record("node_a", 100, 50, 0.01)

    assert reg._global.cost_usd == pytest.approx(0.02)
    assert reg._global.calls == 2
    assert reg._nodes["node_a"].cost_usd == pytest.approx(0.02)


@pytest.mark.asyncio
async def test_record_tracks_run_scope_inside_context():
    reg = BudgetRegistry(BudgetConfig())
    with run_context("run-1"):
        await reg.record("node_a", 100, 50, 0.03)
    assert reg._runs["run-1"].cost_usd == pytest.approx(0.03)


@pytest.mark.asyncio
async def test_record_without_context_has_no_run_entry():
    reg = BudgetRegistry(BudgetConfig())
    await reg.record("node_a", 100, 50, 0.03)
    assert reg._runs == {}


# ---------- state verdicts ----------

@pytest.mark.asyncio
async def test_within_when_no_limits():
    reg = BudgetRegistry(BudgetConfig())
    state = await reg.record("node_a", 100, 50, 5.0)
    assert state is BudgetState.WITHIN


@pytest.mark.asyncio
async def test_warning_on_run_scope():
    cfg = BudgetConfig(run_limit_usd=10.0, warn_threshold=0.8)
    reg = BudgetRegistry(cfg)
    with run_context("run-1"):
        state = await reg.record("node_a", 0, 0, 8.0)
    assert state is BudgetState.WARNING


@pytest.mark.asyncio
async def test_exceeded_returns_worst_state():
    # node is within, global is exceeded, worst wins
    cfg = BudgetConfig(node_limit_usd=100.0, global_limit_usd=1.0)
    reg = BudgetRegistry(cfg)
    state = await reg.record("node_a", 0, 0, 2.0)
    assert state is BudgetState.EXCEEDED


# ---------- concurrency: the Part 2 lock ----------

@pytest.mark.asyncio
async def test_concurrent_records_do_not_lose_updates():
    reg = BudgetRegistry(BudgetConfig())

    async def one():
        await reg.record("node_a", 1, 1, 0.01)

    # 500 tasks hitting the same counters at once
    await asyncio.gather(*(one() for _ in range(500)))

    assert reg._global.calls == 500
    assert reg._global.cost_usd == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_concurrent_runs_stay_isolated():
    reg = BudgetRegistry(BudgetConfig())

    async def do_run(run_id: str, amount: float):
        with run_context(run_id):
            await reg.record("node_a", 0, 0, amount)

    await asyncio.gather(
        do_run("run-1", 1.0),
        do_run("run-2", 2.0),
    )

    assert reg._runs["run-1"].cost_usd == pytest.approx(1.0)
    assert reg._runs["run-2"].cost_usd == pytest.approx(2.0)