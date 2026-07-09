"""Top-level CLI for AgentArmour.

Each module contributes its own command group, so modules stay
independent of one another.

Usage:
    agentarmour --version
    agentarmour ledger summary
    agentarmour budget nodes
"""

from __future__ import annotations

import argparse
import sys

from agentarmour import __version__
from agentarmour.agentbudget.cli import add_budget_commands
from agentarmour.cascadebreaker.cli import add_ledger_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentarmour",
        description="AgentArmour CLI — inspect your reliability ledgers.",
    )
    parser.add_argument(
        "--version", action="version", version=f"agentarmour {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command")
    add_ledger_commands(subparsers)
    add_budget_commands(subparsers)

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