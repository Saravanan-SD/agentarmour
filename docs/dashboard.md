# Dashboard

A Streamlit dashboard for visually inspecting breaker health, reading from the same SQLite ledger as the CLI.

## Install

```bash
pip install agentarmour-toolkit[dashboard]
```

## Run

```bash
streamlit run agentarmour/cascadebreaker/dashboard/app.py
```

This opens a browser tab, usually at `http://localhost:8501`.

To point it at a non-default database file:

```bash
streamlit run agentarmour/cascadebreaker/dashboard/app.py -- --db path/to/your.db
```

## What It Shows

**Top metrics** — total failures, total state transitions, number of breakers tracked.

**Current state per breaker** — inferred from each breaker's most recent transition row.

**Failures over time** — a scatter chart, one point per failure, colored by failure category, plotted against timestamp.

**Recent failures table** — the 50 most recent failure rows: timestamp, breaker name, category, error message, latency.

**Recent transitions table** — the 50 most recent state changes: timestamp, breaker name, from-state, to-state, reason.

## Important: Single Process Only

The dashboard reads from a file on disk, not from a live in-memory breaker. It will not show real-time updates the instant something happens, it shows whatever has already been written to the SQLite file. Refresh the page (or use Streamlit's auto-refresh) to see new data.

This also means: if you're running multiple separate processes, each writing to its own SQLite file, the dashboard only shows the file you point it at. See [Limitations](limitations.md) for why breaker state itself doesn't currently sync across processes either.