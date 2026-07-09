# CLI

A terminal command for inspecting both module ledgers without writing a script every time.

## Ledger Commands

### Summary

```bash
agentarmour ledger summary
```

```
Audit ledger: agentarmour.db
Breakers seen: research_agent, summarise_agent
Total failures recorded:    5
Total state transitions:    2
research_agent: 2 failure(s)
summarise_agent: 3 failure(s)
```

### Failures

```bash
agentarmour ledger failures
agentarmour ledger failures --breaker research_agent
agentarmour ledger failures --limit 5
```

### Transitions

```bash
agentarmour ledger transitions
agentarmour ledger transitions --breaker research_agent
```

## Ledger Options

All three ledger subcommands accept:

| Flag | Default | Purpose |
|---|---|---|
| `--db` | `agentarmour.db` | Path to the SQLite ledger file |
| `--table-prefix` | `cb_` | Table prefix, must match what `SQLiteLedger` was configured with |
| `--breaker` | none | Filter to a single breaker name |
| `--limit` | `20` | Max rows to display (failures/transitions only) |

## Budget Commands

### Summary

```bash
agentarmour budget summary
```

Prints total spend, nodes and runs seen, token totals, and a count of events per state.

### Nodes

```bash
agentarmour budget nodes
```

Cost breakdown per node, most expensive first. The fastest way to find which agent is eating your budget.

### Events

```bash
agentarmour budget events
agentarmour budget events --node research_agent
agentarmour budget events --limit 5
```

## Budget Options

| Flag | Default | Purpose |
|---|---|---|
| `--db` | `agentarmour.db` | Path to the SQLite ledger file |
| `--table-prefix` | `ab_` | Table prefix, must match what `SQLiteBudgetLedger` was configured with |
| `--node` | none | Filter to a single node name (events only) |
| `--limit` | `20` | Max rows to display (events only) |

## Checking the Version

```bash
agentarmour --version
```
