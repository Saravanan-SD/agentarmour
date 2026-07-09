# tests/unit/test_agentbudget_ledger.py
import sqlite3

import pytest

from agentarmour.agentbudget.config import BudgetConfig
from agentarmour.agentbudget.usage import BudgetEvent
from agentarmour.agentbudget.registry import BudgetRegistry, run_context
from agentarmour.agentbudget.storage.sqlite_ledger import SQLiteBudgetLedger


# ---------- ledger writes on its own ----------

@pytest.mark.asyncio
async def test_ledger_creates_table_and_row(tmp_path):
    db = str(tmp_path / "test.db")
    ledger = SQLiteBudgetLedger(db_path=db)

    event = BudgetEvent(
        node="node_a",
        run_id="run-1",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        state="within",
        timestamp=123.0,
    )
    await ledger.log_event(event)

    # open the real file and check the row landed
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT node, run_id, cost_usd, state FROM ab_events"
        ).fetchall()
    finally:
        conn.close()

    assert rows == [("node_a", "run-1", 0.01, "within")]


@pytest.mark.asyncio
async def test_ledger_appends_multiple_rows(tmp_path):
    db = str(tmp_path / "test.db")
    ledger = SQLiteBudgetLedger(db_path=db)

    for i in range(3):
        await ledger.log_event(
            BudgetEvent(
                node=f"node_{i}",
                run_id=None,
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.01,
                state="within",
                timestamp=float(i),
            )
        )

    conn = sqlite3.connect(db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM ab_events").fetchone()[0]
    finally:
        conn.close()

    assert count == 3


@pytest.mark.asyncio
async def test_ledger_stores_null_run_id(tmp_path):
    # a call with no run context should store run_id as NULL
    db = str(tmp_path / "test.db")
    ledger = SQLiteBudgetLedger(db_path=db)

    await ledger.log_event(
        BudgetEvent(
            node="node_a",
            run_id=None,
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.01,
            state="within",
            timestamp=0.0,
        )
    )

    conn = sqlite3.connect(db)
    try:
        run_id = conn.execute("SELECT run_id FROM ab_events").fetchone()[0]
    finally:
        conn.close()

    assert run_id is None


# ---------- registry writes through to the ledger ----------

@pytest.mark.asyncio
async def test_registry_writes_event_when_ledger_present(tmp_path):
    db = str(tmp_path / "test.db")
    ledger = SQLiteBudgetLedger(db_path=db)
    reg = BudgetRegistry(BudgetConfig(), ledger=ledger)

    with run_context("run-1"):
        await reg.record("node_a", 100, 50, 0.02)

    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT node, run_id, cost_usd FROM ab_events"
        ).fetchone()
    finally:
        conn.close()

    assert row == ("node_a", "run-1", 0.02)


@pytest.mark.asyncio
async def test_registry_without_ledger_does_not_break(tmp_path):
    # no ledger passed, record still works and returns a state
    reg = BudgetRegistry(BudgetConfig())
    state = await reg.record("node_a", 100, 50, 0.02)
    assert state.value == "within"


@pytest.mark.asyncio
async def test_registry_logs_state_it_returned(tmp_path):
    # the state written to the ledger matches the verdict returned
    db = str(tmp_path / "test.db")
    ledger = SQLiteBudgetLedger(db_path=db)
    cfg = BudgetConfig(global_limit_usd=1.0)
    reg = BudgetRegistry(cfg, ledger=ledger)

    state = await reg.record("node_a", 0, 0, 2.0)  # over the 1.0 global cap

    conn = sqlite3.connect(db)
    try:
        logged = conn.execute("SELECT state FROM ab_events").fetchone()[0]
    finally:
        conn.close()

    assert state.value == "exceeded"
    assert logged == "exceeded"