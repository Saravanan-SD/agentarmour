"""Streamlit view for AgentBudget.

Reads the ab_events table written by tracked nodes.
Rendered as a tab by the top-level AgentArmour dashboard.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


def load_events(db_path: str, table_prefix: str = "ab_") -> pd.DataFrame:
    """Load the budget events table into a DataFrame."""
    if not Path(db_path).exists():
        return pd.DataFrame()

    conn = sqlite3.connect(db_path)
    try:
        events = pd.read_sql_query(f"SELECT * FROM {table_prefix}events", conn)
    except pd.errors.DatabaseError:
        events = pd.DataFrame()
    conn.close()

    if not events.empty:
        events["timestamp"] = pd.to_datetime(events["timestamp"], unit="s")

    return events


def cost_per_node(events: pd.DataFrame) -> pd.DataFrame:
    """Total cost and tokens per node, most expensive first."""
    if events.empty:
        return pd.DataFrame()
    grouped = (
        events.groupby("node")
        .agg(
            calls=("id", "count"),
            input_tokens=("input_tokens", "sum"),
            output_tokens=("output_tokens", "sum"),
            cost_usd=("cost_usd", "sum"),
        )
        .reset_index()
        .sort_values("cost_usd", ascending=False)
    )
    return grouped


def cumulative_cost(events: pd.DataFrame) -> pd.DataFrame:
    """Running total of spend over time."""
    if events.empty:
        return pd.DataFrame()
    df = events.sort_values("timestamp").copy()
    df["cumulative_usd"] = df["cost_usd"].cumsum()
    return df


def render(db_path: str) -> None:
    """Render the AgentBudget section. Assumes page config is already set."""
    events = load_events(db_path)

    if events.empty:
        st.warning(
            f"No budget data found in '{db_path}'. "
            "Run a tracked node at least once to generate data."
        )
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Spend", f"${events['cost_usd'].sum():.4f}")
    col2.metric("Nodes Tracked", events["node"].nunique())
    col3.metric("Runs Seen", events["run_id"].nunique())
    col4.metric(
        "Total Tokens",
        f"{int(events['input_tokens'].sum() + events['output_tokens'].sum()):,}",
    )

    over = int((events["state"] == "exceeded").sum())
    if over:
        st.error(f"{over} event(s) exceeded a budget limit.")

    st.divider()

    st.subheader("Cumulative Spend Over Time")
    cum = cumulative_cost(events)
    fig = px.line(
        cum,
        x="timestamp",
        y="cumulative_usd",
        title="Running total spend",
        markers=True,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("Cost Per Node")
    per_node = cost_per_node(events)
    fig = px.bar(
        per_node,
        x="node",
        y="cost_usd",
        color="cost_usd",
        title="Which agents are eating your budget",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(per_node, use_container_width=True, hide_index=True)

    st.divider()

    st.subheader("Recent Budget Events")
    display_cols = ["timestamp", "node", "run_id", "cost_usd", "state"]
    st.dataframe(
        events[display_cols].sort_values("timestamp", ascending=False).head(50),
        use_container_width=True,
        hide_index=True,
    )