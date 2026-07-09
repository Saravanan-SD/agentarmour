"""Command-line interface for AgentBudget.

Usage:
    agentarmour budget summary
    agentarmour budget nodes
    agentarmour budget events --node research_agent --limit 10
"""

from __future__ import annotations

import argparse
import sqlite3


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def cmd_budget_summary(args: argparse.Namespace) -> int:
    conn = _connect(args.db)
    table = f"{args.table_prefix}events"

    if not _table_exists(conn, table):
        print(f"No budget data found in '{args.db}'. Has a tracked node run yet?")
        return 1

    row = conn.execute(
        f"""
        SELECT COUNT(*) AS events,
               COUNT(DISTINCT node) AS nodes,
               COUNT(DISTINCT run_id) AS runs,
               SUM(input_tokens) AS input_tokens,
               SUM(output_tokens) AS output_tokens,
               SUM(cost_usd) AS cost_usd
        FROM {table}
        """
    ).fetchone()

    print(f"Budget ledger: {args.db}")
    print(f"Events recorded:  {row['events']}")
    print(f"Nodes seen:       {row['nodes']}")
    print(f"Runs seen:        {row['runs']}")
    print(f"Input tokens:     {row['input_tokens'] or 0:,}")
    print(f"Output tokens:    {row['output_tokens'] or 0:,}")
    print(f"Total cost:       ${row['cost_usd'] or 0:.4f}")

    states = conn.execute(
        f"SELECT state, COUNT(*) AS n FROM {table} GROUP BY state"
    ).fetchall()
    for s in states:
        print(f"  {s['state']}: {s['n']} event(s)")

    conn.close()
    return 0


def cmd_budget_nodes(args: argparse.Namespace) -> int:
    conn = _connect(args.db)
    table = f"{args.table_prefix}events"

    if not _table_exists(conn, table):
        print(f"No budget data found in '{args.db}'.")
        return 1

    rows = conn.execute(
        f"""
        SELECT node,
               COUNT(*) AS calls,
               SUM(input_tokens) AS input_tokens,
               SUM(output_tokens) AS output_tokens,
               SUM(cost_usd) AS cost_usd
        FROM {table}
        GROUP BY node
        ORDER BY cost_usd DESC
        """
    ).fetchall()

    if not rows:
        print("No budget events recorded yet.")
        return 0

    for row in rows:
        print(
            f"{row['node']}: ${row['cost_usd']:.4f} "
            f"over {row['calls']} call(s), "
            f"{row['input_tokens']:,} in / {row['output_tokens']:,} out"
        )

    conn.close()
    return 0


def cmd_budget_events(args: argparse.Namespace) -> int:
    conn = _connect(args.db)
    table = f"{args.table_prefix}events"

    if not _table_exists(conn, table):
        print(f"No budget data found in '{args.db}'.")
        return 1

    query = f"SELECT node, run_id, cost_usd, state, timestamp FROM {table}"
    params: list[str] = []
    if args.node:
        query += " WHERE node = ?"
        params.append(args.node)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(str(args.limit))

    rows = conn.execute(query, params).fetchall()

    if not rows:
        print("No events found matching that filter.")
        return 0

    for row in rows:
        run = row["run_id"] or "(no run)"
        print(
            f"[{row['node']}] {row['state']}: "
            f"${row['cost_usd']:.4f} (run {run})"
        )

    conn.close()
    return 0


def add_budget_commands(subparsers) -> None:
    """Attach the `budget` command group to a parent subparser."""
    budget_parser = subparsers.add_parser("budget", help="Inspect the budget ledger")
    budget_sub = budget_parser.add_subparsers(dest="budget_command")

    summary_parser = budget_sub.add_parser("summary", help="Show a high-level summary")
    summary_parser.add_argument("--db", default="agentarmour.db")
    summary_parser.add_argument("--table-prefix", default="ab_")
    summary_parser.set_defaults(func=cmd_budget_summary)

    nodes_parser = budget_sub.add_parser("nodes", help="Cost breakdown per node")
    nodes_parser.add_argument("--db", default="agentarmour.db")
    nodes_parser.add_argument("--table-prefix", default="ab_")
    nodes_parser.set_defaults(func=cmd_budget_nodes)

    events_parser = budget_sub.add_parser("events", help="List recorded budget events")
    events_parser.add_argument("--db", default="agentarmour.db")
    events_parser.add_argument("--table-prefix", default="ab_")
    events_parser.add_argument("--node", default=None, help="Filter by node name")
    events_parser.add_argument("--limit", type=int, default=20)
    events_parser.set_defaults(func=cmd_budget_events)