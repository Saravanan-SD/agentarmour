# tests/unit/test_agentbudget_cli.py
import argparse
import sqlite3

import pytest

from agentarmour.agentbudget.cli import (
    add_budget_commands,
    cmd_budget_events,
    cmd_budget_nodes,
    cmd_budget_summary,
)
from agentarmour.cli import build_parser


def _seed(db_path: str) -> None:
    """Write a few ab_events rows straight into a fresh db."""
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
            ("pricey_node", "run-1", 900, 400, 0.90, "warning", 2.0),
            ("pricey_node", "run-2", 900, 400, 0.90, "exceeded", 3.0),
        ],
    )
    conn.commit()
    conn.close()


def _args(db, **kwargs) -> argparse.Namespace:
    base = {"db": str(db), "table_prefix": "ab_"}
    base.update(kwargs)
    return argparse.Namespace(**base)


# ---------- parser wiring ----------

def test_parser_has_both_command_groups():
    parser = build_parser()
    help_text = parser.format_help()
    assert "ledger" in help_text
    assert "budget" in help_text


def test_budget_subcommands_resolve_to_functions():
    parser = build_parser()
    args = parser.parse_args(["budget", "nodes"])
    assert args.func is cmd_budget_nodes


# ---------- empty state ----------

def test_summary_missing_table_returns_1(tmp_path, capsys):
    db = tmp_path / "empty.db"
    code = cmd_budget_summary(_args(db))
    out = capsys.readouterr().out

    assert code == 1
    assert "No budget data found" in out


def test_nodes_missing_table_returns_1(tmp_path, capsys):
    db = tmp_path / "empty.db"
    assert cmd_budget_nodes(_args(db)) == 1


# ---------- summary ----------

def test_summary_reports_totals(tmp_path, capsys):
    db = tmp_path / "seeded.db"
    _seed(str(db))

    code = cmd_budget_summary(_args(db))
    out = capsys.readouterr().out

    assert code == 0
    assert "Events recorded:  3" in out
    assert "Nodes seen:       2" in out
    assert "Runs seen:        2" in out
    assert "$1.8100" in out          # 0.01 + 0.90 + 0.90
    assert "exceeded: 1 event(s)" in out


# ---------- nodes ----------

def test_nodes_sorted_by_cost_descending(tmp_path, capsys):
    db = tmp_path / "seeded.db"
    _seed(str(db))

    code = cmd_budget_nodes(_args(db))
    out = capsys.readouterr().out

    assert code == 0
    # the expensive node must be listed first
    assert out.index("pricey_node") < out.index("cheap_node")
    assert "$1.8000" in out          # pricey_node total


# ---------- events ----------

def test_events_lists_all_by_default(tmp_path, capsys):
    db = tmp_path / "seeded.db"
    _seed(str(db))

    code = cmd_budget_events(_args(db, node=None, limit=20))
    out = capsys.readouterr().out

    assert code == 0
    assert out.count("\n") == 3


def test_events_filters_by_node(tmp_path, capsys):
    db = tmp_path / "seeded.db"
    _seed(str(db))

    cmd_budget_events(_args(db, node="cheap_node", limit=20))
    out = capsys.readouterr().out

    assert "cheap_node" in out
    assert "pricey_node" not in out


def test_events_respects_limit(tmp_path, capsys):
    db = tmp_path / "seeded.db"
    _seed(str(db))

    cmd_budget_events(_args(db, node=None, limit=1))
    out = capsys.readouterr().out

    assert out.count("\n") == 1