"""Top-level AgentArmour dashboard.

Composes each module's view into a tab. Modules stay independent.

    uv run streamlit run agentarmour/dashboard/app.py
    uv run streamlit run agentarmour/dashboard/app.py -- --db path/to/your.db
"""

from __future__ import annotations

import sys

import streamlit as st

from agentarmour.agentbudget.dashboard import app as budget_view
from agentarmour.cascadebreaker.dashboard import app as breaker_view


def get_db_path() -> str:
    args = sys.argv[1:]
    if "--db" in args:
        idx = args.index("--db")
        if idx + 1 < len(args):
            return args[idx + 1]
    return "agentarmour.db"


def main() -> None:
    st.set_page_config(page_title="AgentArmour Dashboard", layout="wide")
    st.title("AgentArmour Dashboard")

    db_path = get_db_path()
    st.caption(f"Reading ledger from: {db_path}")

    breaker_tab, budget_tab = st.tabs(["CascadeBreaker", "AgentBudget"])

    with breaker_tab:
        breaker_view.render(db_path)

    with budget_tab:
        budget_view.render(db_path)


if __name__ == "__main__":
    main()