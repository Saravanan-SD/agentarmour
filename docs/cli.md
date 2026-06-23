# CLI

A terminal command for inspecting the audit ledger without writing a script every time.

## Commands

### Summary

```bash
agentarmour ledger summary
```

Audit ledger: cascadebreaker.db
Breakers seen: research_agent, summarise_agent
Total failures recorded:    5
Total state transitions:    2
research_agent: 2 failure(s)
summarise_agent: 3 failure(s)

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

## Options

All three subcommands accept:

| Flag | Default | Purpose |
|---|---|---|
| `--db` | `cascadebreaker.db` | Path to the SQLite ledger file |
| `--table-prefix` | `cb_` | Table prefix, must match what `SQLiteLedger` was configured with |
| `--breaker` | none | Filter to a single breaker name |
| `--limit` | `20` | Max rows to display (failures/transitions only) |

## Checking the Version

```bash
agentarmour --version
```