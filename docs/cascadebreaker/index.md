# CascadeBreaker

**Circuit breaker and self-healing layer for LangGraph multi-agent systems.**

## Why This Exists

Existing circuit breaker tools for LLMs (`llm-circuit`, `aeneassoft`, `llm-cascade`) only protect against **LLM API provider outages**. OpenAI down, Anthropic rate-limited.

They do nothing about what actually breaks production multi-agent systems: an agent stuck in a reasoning loop, a hallucinated value silently poisoning shared state, one agent's failure cascading through every downstream node.

A March 2025 paper, ["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657) (Cemri et al.), analysed over 1,600 execution traces across seven multi-agent frameworks and identified 14 distinct failure modes. None of them involve an API going down.

CascadeBreaker operates one level below the API, at the individual LangGraph node.

## In This Section

- **[Fallback Strategies](strategies.md)** — the four ways to respond when a breaker trips
- **[Cross-Agent Guard](guard.md)** — stopping contaminated data from spreading between agents

For install and your first protected node, see [Getting Started](../getting-started.md).
