"""
cascadebreaker_basic.py — Pure Python example, zero extra dependencies.

Demonstrates the full CLOSED → OPEN → HALF_OPEN → CLOSED cycle without
needing LangGraph or LangChain installed.

Run with:
    python examples/cascadebreaker_basic.py
"""

from __future__ import annotations

import asyncio

from agentarmour.cascadebreaker import (
    CircuitBreaker,
    BreakerConfig,
    get_registry,
)
from agentarmour.cascadebreaker.strategies import CacheStrategy


# ── A flaky "agent" that fails the first 2 times, then recovers ─────────────

call_count = 0


async def flaky_agent(state: dict) -> dict:
    global call_count
    call_count += 1

    if call_count <= 2:
        raise RuntimeError(f"Simulated failure on call #{call_count}")

    return {**state, "result": f"Success on call #{call_count}"}


# ── Callbacks to print state changes ─────────────────────────────────────────

async def on_open(name: str) -> None:
    print(f"  ⚡ [{name}] Circuit OPEN — fallback active")


async def on_close(name: str) -> None:
    print(f"  ✅ [{name}] Circuit CLOSED — agent recovered")


async def on_half_open(name: str) -> None:
    print(f"  🔍 [{name}] Circuit HALF-OPEN — probing recovery...")


# ── Set up the breaker ────────────────────────────────────────────────────────

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


# ── Run the demo ──────────────────────────────────────────────────────────────

async def main() -> None:
    print("\n" + "=" * 60)
    print("  CascadeBreaker — Pure Python Demo (no LangGraph needed)")
    print("  Agent fails on calls 1-2, recovers from call 3 onward")
    print("=" * 60 + "\n")

    for i in range(1, 6):
        if i == 3:
            print("  ⏳ Waiting 2.5s for recovery timeout...")
            await asyncio.sleep(2.5)

        print(f"  Call {i} — Breaker state before: {breaker.state.value}")
        result = await protected_agent({"input": f"request-{i}"})
        print(f"  Result: {result}")
        print(f"  Breaker state after:  {breaker.state.value}\n")

    print("=" * 60)
    print("  Final metrics:")
    for key, value in breaker.metrics.items():
        print(f"    {key}: {value}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())