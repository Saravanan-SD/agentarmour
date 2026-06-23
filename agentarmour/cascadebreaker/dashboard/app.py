"""
Streamlit dashboard for CascadeBreaker.

Reads directly from the SQLite audit ledger written by your circuit
breakers. Run with:

    uv run streamlit run agentarmour/cascadebreaker/dashboard/app.py

Or point it at a specific database:

    uv run streamlit run agentarmour/cascadebreaker/dashboard/app.py -- --db path/to/your.db
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


def get_db_path() -> str:
    """Read --db from the command line if provided, otherwise use the default."""
    args = sys.argv[1:]
    if "--db" in args:
        idx = args.index("--db")
        if idx + 1 < len(args):
            return args[idx + 1]
    return "cascadebreaker.db"


def load_data(db_path: str, table_prefix: str = "cb_") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load failures and transitions tables into pandas DataFrames."""
    if not Path(db_path).exists():
        return pd.DataFrame(), pd.DataFrame()

    conn = sqlite3.connect(db_path)
    try:
        failures = pd.read_sql_query(f"SELECT * FROM {table_prefix}failures", conn)
    except pd.errors.DatabaseError:
        failures = pd.DataFrame()
    try:
        transitions = pd.read_sql_query(f"SELECT * FROM {table_prefix}transitions", conn)
    except pd.errors.DatabaseError:
        transitions = pd.DataFrame()
    conn.close()

    if not failures.empty:
        failures["timestamp"] = pd.to_datetime(failures["timestamp"], unit="s")
    if not transitions.empty:
        transitions["timestamp"] = pd.to_datetime(transitions["timestamp"], unit="s")

    return failures, transitions


def current_state_per_breaker(transitions: pd.DataFrame) -> pd.DataFrame:
    """Infer each breaker's current state from its most recent transition."""
    if transitions.empty:
        return pd.DataFrame()
    latest = transitions.sort_values("timestamp").groupby("breaker_name").tail(1)
    return latest[["breaker_name", "to_state", "timestamp"]].rename(
        columns={"to_state": "current_state", "timestamp": "as_of"}
    )


def main() -> None:
    st.set_page_config(page_title="CascadeBreaker Dashboard", layout="wide")
    st.title("CascadeBreaker Dashboard")

    db_path = get_db_path()
    st.caption(f"Reading audit ledger from: {db_path}")

    failures, transitions = load_data(db_path)

    if failures.empty and transitions.empty:
        st.warning(
            f"No audit data found in '{db_path}'. "
            "Run a protected agent at least once to generate data."
        )
        return

    # --- Top row: live status cards ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Failures", len(failures))
    col2.metric("Total State Transitions", len(transitions))
    col3.metric("Breakers Tracked", failures["breaker_name"].nunique() if not failures.empty else 0)

    st.divider()

    # --- Current state per breaker ---
    st.subheader("Current State (inferred from latest transition)")
    state_df = current_state_per_breaker(transitions)
    if not state_df.empty:
        st.dataframe(state_df, use_container_width=True, hide_index=True)
    else:
        st.info("No state transitions recorded yet.")

    st.divider()

    # --- Failures over time chart ---
    if not failures.empty:
        st.subheader("Failures Over Time")
        chart_df = failures.copy()
        chart_df["count"] = 1
        fig = px.scatter(
            chart_df,
            x="timestamp",
            y="breaker_name",
            color="category",
            hover_data=["error_message"],
            title="Failure events by breaker",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # --- Recent failures table ---
    st.subheader("Recent Failures")
    if not failures.empty:
        display_cols = ["timestamp", "breaker_name", "category", "error_message", "latency_ms"]
        st.dataframe(
            failures[display_cols].sort_values("timestamp", ascending=False).head(50),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No failures recorded yet.")

    st.divider()

    # --- Recent transitions table ---
    st.subheader("Recent State Transitions")
    if not transitions.empty:
        display_cols = ["timestamp", "breaker_name", "from_state", "to_state", "reason"]
        st.dataframe(
            transitions[display_cols].sort_values("timestamp", ascending=False).head(50),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No transitions recorded yet.")


if __name__ == "__main__":
    main()