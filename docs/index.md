# AgentArmour

**Production reliability suite for LangChain/LangGraph multi-agent systems.**

Multi-agent pipelines fail in ways a plain try/except never catches. An agent loops and burns tokens. A hallucinated value poisons shared state. Costs blow past budget with no exception raised. AgentArmour is a set of independent modules, each targeting one of those failure modes at the individual node.

Grounded in ["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657) (Cemri et al., March 2025), which analysed over 1,600 execution traces across seven multi-agent frameworks and identified 14 distinct failure modes. None of them involve an API going down.

## Modules

- **[CascadeBreaker](cascadebreaker/index.md)** — circuit breaker and self-healing for failures that raise: loops, timeouts, cascading errors, contaminated state.
- **[AgentBudget](agentbudget/index.md)** — token and cost ceilings for the quieter failure: runaway spend that never raises anything.

## Shared Tooling

- **[Audit Ledger](storage.md)** — both modules persist to one SQLite file, in separate tables
- **[CLI](cli.md)** — inspect either ledger from the terminal
- **[Dashboard](dashboard.md)** — one Streamlit app, a tab per module
- **[Limitations](limitations.md)** — what this does not solve yet, stated plainly

## Install

```bash
pip install agentarmour-toolkit
```

Core install pulls in only `pydantic` and `structlog`. LangGraph integration, LangChain callbacks, and the dashboard are optional extras.

## Source

[github.com/Saravanan-SD/agentarmour](https://github.com/Saravanan-SD/agentarmour)
