"""
basic_usage.py — CascadeBreaker pure Python example, zero extra dependencies.

Demonstrates the full CLOSED -> OPEN -> HALF_OPEN -> CLOSED cycle without
needing LangGraph or LangChain installed.

Run with:
    uv run python examples/basic_usage.py
"""

from __future__ import annotations

import logging
import structlog

# Quiet down internal logs so the demo output stays readable.
# Remove this block if you want to see full internal logging.
logging.basicConfig(level=logging.WARNING)
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
)

import asyncio

from agentarmour.cascadebreaker import (
    CircuitBreaker,
    BreakerConfig,
    get_registry,
)
from agentarmour.cascadebreaker.strategies import CacheStrategy


call_count = 0


async def flaky_agent(state: dict) -> dict:
    global call_count
    call_count += 1

    if call_count <= 2:
        raise RuntimeError(f"Simulated failure on call #{call_count}")

    return {**state, "result": f"Success on call #{call_count}"}


async def on_open(name: str) -> None:
    print(f"  Circuit OPEN  — [{name}] fallback active")


async def on_close(name: str) -> None:
    print(f"  Circuit CLOSED — [{name}] agent recovered")


async def on_half_open(name: str) -> None:
    print(f"  Circuit HALF-OPEN — [{name}] probing recovery...")


breaker = CircuitBreaker(
    name="demo_agent",
    config=BreakerConfig(
        failure_threshold=2,
        recovery_timeout=2.0,
        window_seconds=30.0,
    ),
    fallback_strategy=CacheStrategy(max_age_seconds=60),
    on_open=on_open,
    on_close=on_close,
    on_half_open=on_half_open,
)

get_registry().register(breaker)


@breaker.protect
async def protected_agent(state: dict) -> dict:
    return await flaky_agent(state)


async def main() -> None:
    print("\n" + "=" * 60)
    print("  CascadeBreaker — Basic Demo (no LangGraph needed)")
    print("  Agent fails on calls 1-2, recovers from call 3 onward")
    print("=" * 60 + "\n")

    for i in range(1, 6):
        if i == 3:
            print("  Waiting 2.5s for recovery timeout...")
            await asyncio.sleep(2.5)

        print(f"  Call {i} — state before: {breaker.state.value}")
        result = await protected_agent({"input": f"request-{i}"})
        print(f"  Result: {result}")
        print(f"  State after:  {breaker.state.value}\n")

    print("=" * 60)
    print("  Final metrics:")
    for key, value in breaker.metrics.items():
        print(f"    {key}: {value}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())