"""
langgraph_example.py — CascadeBreaker integrated with a real LangGraph graph.

Demonstrates a two-node LangGraph pipeline where the first node is protected
by a CircuitBreaker and the second node is protected by a CascadeGuard against
cross-agent contamination.

Run with:
    uv run python examples/langgraph_example.py

Requires the langgraph optional dependency:
    uv add --optional langgraph langgraph langchain-core
"""

from __future__ import annotations

import logging
import structlog

logging.basicConfig(level=logging.WARNING)
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
)

import asyncio
from typing import TypedDict

from langgraph.graph import StateGraph, END

from agentarmour.cascadebreaker import (
    CircuitBreaker,
    BreakerConfig,
    CascadeGuard,
    get_registry,
)
from agentarmour.cascadebreaker.strategies import CacheStrategy


class ResearchState(TypedDict):
    query: str
    research_result: str | None
    summary: str | None


call_count = 0


async def flaky_llm(query: str) -> str:
    global call_count
    call_count += 1
    if call_count <= 2:
        raise RuntimeError(f"Simulated LLM failure on call #{call_count}")
    return f"Research findings for '{query}' (call #{call_count})"


breaker = CircuitBreaker(
    name="research_agent",
    config=BreakerConfig(failure_threshold=2, recovery_timeout=2.0),
    fallback_strategy=CacheStrategy(max_age_seconds=300),
)
get_registry().register(breaker)

guard = CascadeGuard(quarantine_ttl_seconds=60)


@breaker.protect
async def research_node(state: ResearchState) -> ResearchState:
    result = await flaky_llm(state["query"])
    return {**state, "research_result": result}


@guard.protect_node(
    node_name="summarise_agent",
    reads_from=["research_result"],
)
async def summarise_node(state: ResearchState) -> ResearchState:
    research = state.get("research_result")
    if research is None:
        summary = "Summary unavailable — upstream research degraded."
    else:
        summary = f"Summary: {research}"
    return {**state, "summary": summary}


def build_graph():
    builder = StateGraph(ResearchState)
    builder.add_node("research", research_node)
    builder.add_node("summarise", summarise_node)
    builder.set_entry_point("research")
    builder.add_edge("research", "summarise")
    builder.add_edge("summarise", END)
    return builder.compile()


async def main() -> None:
    graph = build_graph()

    print("\n" + "=" * 60)
    print("  CascadeBreaker + LangGraph — Two-Node Pipeline Demo")
    print("=" * 60 + "\n")

    queries = [
        "ocean temperature trends",
        "satellite altimetry methods",
        "deep ocean currents",
    ]

    for i, query in enumerate(queries, 1):
        if i == 3:
            print("  Waiting 2.5s for recovery timeout...\n")
            await asyncio.sleep(2.5)

        print(f"  Run {i}: query='{query}'")
        print(f"  Breaker state before: {breaker.state.value}")

        result = await graph.ainvoke({
            "query": query,
            "research_result": None,
            "summary": None,
        })

        print(f"  Summary: {result['summary']}")
        print(f"  Breaker state after:  {breaker.state.value}\n")

    print("=" * 60)
    print("  Final metrics:", breaker.metrics)
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())