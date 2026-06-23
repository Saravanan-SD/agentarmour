"""
Command-line interface for CascadeBreaker.

Lets you inspect a SQLite audit ledger from the terminal without writing
a throwaway script every time. Uses only the standard library.

Usage:
    agentarmour --version
    agentarmour ledger summary
    agentarmour ledger failures --limit 10
    agentarmour ledger transitions --breaker research_agent
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

from agentarmour import __version__


def _connect(db_path: str, table_prefix: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def cmd_summary(args: argparse.Namespace) -> int:
    prefix = args.table_prefix
    conn = _connect(args.db, prefix)

    failures_table = f"{prefix}failures"
    transitions_table = f"{prefix}transitions"

    if not _table_exists(conn, failures_table):
        print(f"No audit data found in '{args.db}'. Has the breaker run yet?")
        return 1

    total_failures = conn.execute(f"SELECT COUNT(*) FROM {failures_table}").fetchone()[0]
    total_transitions = conn.execute(f"SELECT COUNT(*) FROM {transitions_table}").fetchone()[0]

    breakers = conn.execute(
        f"SELECT DISTINCT breaker_name FROM {failures_table}"
    ).fetchall()
    breaker_names = [row["breaker_name"] for row in breakers]

    print(f"Audit ledger: {args.db}")
    print(f"Breakers seen: {', '.join(breaker_names) if breaker_names else '(none)'}")
    print(f"Total failures recorded:    {total_failures}")
    print(f"Total state transitions:    {total_transitions}")

    for name in breaker_names:
        count = conn.execute(
            f"SELECT COUNT(*) FROM {failures_table} WHERE breaker_name = ?", (name,)
        ).fetchone()[0]
        print(f"  {name}: {count} failure(s)")

    conn.close()
    return 0


def cmd_failures(args: argparse.Namespace) -> int:
    prefix = args.table_prefix
    conn = _connect(args.db, prefix)
    table = f"{prefix}failures"

    if not _table_exists(conn, table):
        print(f"No audit data found in '{args.db}'.")
        return 1

    query = f"SELECT breaker_name, category, error_message, timestamp FROM {table}"
    params: list[str] = []
    if args.breaker:
        query += " WHERE breaker_name = ?"
        params.append(args.breaker)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(str(args.limit))

    rows = conn.execute(query, params).fetchall()

    if not rows:
        print("No failures found matching that filter.")
        return 0

    for row in rows:
        print(f"[{row['breaker_name']}] {row['category']}: {row['error_message']}")

    conn.close()
    return 0


def cmd_transitions(args: argparse.Namespace) -> int:
    prefix = args.table_prefix
    conn = _connect(args.db, prefix)
    table = f"{prefix}transitions"

    if not _table_exists(conn, table):
        print(f"No audit data found in '{args.db}'.")
        return 1

    query = f"SELECT breaker_name, from_state, to_state, reason, timestamp FROM {table}"
    params: list[str] = []
    if args.breaker:
        query += " WHERE breaker_name = ?"
        params.append(args.breaker)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(str(args.limit))

    rows = conn.execute(query, params).fetchall()

    if not rows:
        print("No transitions found matching that filter.")
        return 0

    for row in rows:
        print(
            f"[{row['breaker_name']}] {row['from_state']} -> {row['to_state']}: "
            f"{row['reason']}"
        )

    conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentarmour",
        description="CascadeBreaker CLI — inspect your circuit breaker audit ledger.",
    )
    parser.add_argument(
        "--version", action="version", version=f"agentarmour {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command")

    ledger_parser = subparsers.add_parser("ledger", help="Inspect the audit ledger")
    ledger_sub = ledger_parser.add_subparsers(dest="ledger_command")

    common_args = {
        "--db": {"default": "cascadebreaker.db", "help": "Path to the SQLite ledger file"},
        "--table-prefix": {"default": "cb_", "help": "Table name prefix used by the ledger"},
    }

    summary_parser = ledger_sub.add_parser("summary", help="Show a high-level summary")
    summary_parser.add_argument("--db", default="cascadebreaker.db")
    summary_parser.add_argument("--table-prefix", default="cb_")
    summary_parser.set_defaults(func=cmd_summary)

    failures_parser = ledger_sub.add_parser("failures", help="List recorded failures")
    failures_parser.add_argument("--db", default="cascadebreaker.db")
    failures_parser.add_argument("--table-prefix", default="cb_")
    failures_parser.add_argument("--breaker", default=None, help="Filter by breaker name")
    failures_parser.add_argument("--limit", type=int, default=20)
    failures_parser.set_defaults(func=cmd_failures)

    transitions_parser = ledger_sub.add_parser("transitions", help="List state transitions")
    transitions_parser.add_argument("--db", default="cascadebreaker.db")
    transitions_parser.add_argument("--table-prefix", default="cb_")
    transitions_parser.add_argument("--breaker", default=None, help="Filter by breaker name")
    transitions_parser.add_argument("--limit", type=int, default=20)
    transitions_parser.set_defaults(func=cmd_transitions)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()