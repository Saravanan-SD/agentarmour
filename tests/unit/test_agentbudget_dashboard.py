# tests/unit/test_agentbudget_dashboard.py
import sqlite3

import pandas as pd
import pytest

from agentarmour.agentbudget.dashboard.app import (
    cost_per_node,
    cumulative_cost,
    load_events,
)


def _seed(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE ab_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node TEXT NOT NULL,
            run_id TEXT,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cost_usd REAL NOT NULL,
            state TEXT NOT NULL,
            timestamp REAL NOT NULL
        )
        """
    )
    conn.executemany(
        "INSERT INTO ab_events "
        "(node, run_id, input_tokens, output_tokens, cost_usd, state, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("cheap_node", "run-1", 100, 50, 0.01, "within", 1.0),
            ("pricey_node", "run-1", 900, 400, 0.50, "warning", 2.0),
            ("pricey_node", "run-2", 900, 400, 0.40, "exceeded", 3.0),
        ],
    )
    conn.commit()
    conn.close()


# ---------- load_events ----------

def test_load_events_missing_file_returns_empty(tmp_path):
    df = load_events(str(tmp_path / "nope.db"))
    assert df.empty


def test_load_events_missing_table_returns_empty(tmp_path):
    # file exists but has no ab_events table
    db = tmp_path / "bare.db"
    sqlite3.connect(str(db)).close()

    df = load_events(str(db))
    assert df.empty


def test_load_events_reads_rows(tmp_path):
    db = tmp_path / "seeded.db"
    _seed(str(db))

    df = load_events(str(db))
    assert len(df) == 3
    assert set(df["node"]) == {"cheap_node", "pricey_node"}


def test_load_events_converts_timestamp(tmp_path):
    db = tmp_path / "seeded.db"
    _seed(str(db))

    df = load_events(str(db))
    # raw float seconds become real datetimes
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])


# ---------- cost_per_node ----------

def test_cost_per_node_empty_input():
    assert cost_per_node(pd.DataFrame()).empty


def test_cost_per_node_aggregates_and_sorts(tmp_path):
    db = tmp_path / "seeded.db"
    _seed(str(db))
    events = load_events(str(db))

    per_node = cost_per_node(events)

    # most expensive first
    assert per_node.iloc[0]["node"] == "pricey_node"
    assert per_node.iloc[0]["cost_usd"] == pytest.approx(0.90)
    assert per_node.iloc[0]["calls"] == 2

    assert per_node.iloc[1]["node"] == "cheap_node"
    assert per_node.iloc[1]["calls"] == 1


def test_cost_per_node_sums_tokens(tmp_path):
    db = tmp_path / "seeded.db"
    _seed(str(db))
    events = load_events(str(db))

    pricey = cost_per_node(events).iloc[0]
    assert pricey["input_tokens"] == 1800
    assert pricey["output_tokens"] == 800


# ---------- cumulative_cost ----------

def test_cumulative_cost_empty_input():
    assert cumulative_cost(pd.DataFrame()).empty


def test_cumulative_cost_runs_a_total(tmp_path):
    db = tmp_path / "seeded.db"
    _seed(str(db))
    events = load_events(str(db))

    cum = cumulative_cost(events)
    totals = list(cum["cumulative_usd"])

    assert totals == pytest.approx([0.01, 0.51, 0.91])


def test_cumulative_cost_sorts_by_time_first(tmp_path):
    # rows inserted out of order must still accumulate chronologically
    db = tmp_path / "unordered.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE ab_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node TEXT NOT NULL,
            run_id TEXT,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cost_usd REAL NOT NULL,
            state TEXT NOT NULL,
            timestamp REAL NOT NULL
        )
        """
    )
    conn.executemany(
        "INSERT INTO ab_events "
        "(node, run_id, input_tokens, output_tokens, cost_usd, state, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("b", None, 1, 1, 0.20, "within", 9.0),   # later, inserted first
            ("a", None, 1, 1, 0.10, "within", 1.0),   # earlier
        ],
    )
    conn.commit()
    conn.close()

    cum = cumulative_cost(load_events(str(db)))
    assert list(cum["node"]) == ["a", "b"]
    assert list(cum["cumulative_usd"]) == pytest.approx([0.10, 0.30])


def test_cumulative_cost_does_not_mutate_input(tmp_path):
    db = tmp_path / "seeded.db"
    _seed(str(db))
    events = load_events(str(db))

    cumulative_cost(events)
    # the .copy() inside means the caller's frame is untouched
    assert "cumulative_usd" not in events.columns