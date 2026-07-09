# Dashboard

A Streamlit dashboard for visually inspecting reliability data, reading from the same SQLite ledger as the CLI. One app, a tab per module.

## Install

```bash
pip install agentarmour-toolkit[dashboard]
```

## Run

```bash
streamlit run agentarmour/dashboard/app.py
```

Opens a browser tab, usually at `http://localhost:8501`, with one tab per module: CascadeBreaker and AgentBudget.

Point it at a non-default database file:

```bash
streamlit run agentarmour/dashboard/app.py -- --db path/to/your.db
```

## What It Shows

### CascadeBreaker Tab

**Top metrics** — total failures, total state transitions, number of breakers tracked.

**Current state per breaker** — inferred from each breaker's most recent transition row.

**Failures over time** — a scatter chart, one point per failure, colored by failure category, plotted against timestamp.

**Recent failures table** — the 50 most recent failure rows: timestamp, breaker name, category, error message, latency.

**Recent transitions table** — the 50 most recent state changes: timestamp, breaker name, from-state, to-state, reason.

### AgentBudget Tab

**Top metrics** — total spend, nodes tracked, runs seen, total tokens.

**Cumulative spend over time** — a running total line. A runaway loop shows up as the line bending upward instead of stepping evenly.

**Cost per node** — a bar chart and table, most expensive node first.

**Recent budget events** — the 50 most recent rows: timestamp, node, run, cost, state.

## Important: Single Process Only

The dashboard reads from a file on disk, not from a live in-memory breaker or budget. It will not show real-time updates the instant something happens, it shows whatever has already been written to the SQLite file. Refresh the page (or use Streamlit's auto-refresh) to see new data.

This also means: if you're running multiple separate processes, each writing to its own SQLite file, the dashboard only shows the file you point it at. See [Limitations](limitations.md) for why breaker and budget state itself doesn't currently sync across processes either.
