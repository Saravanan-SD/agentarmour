import logging
import structlog

# Silence all logging noise so it doesn't flood the output
logging.basicConfig(level=logging.CRITICAL)
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
)

import asyncio
import time
import statistics
from agentarmour.cascadebreaker import CircuitBreaker, BreakerConfig
from agentarmour.cascadebreaker.strategies import CacheStrategy

ITERATIONS = 5000

async def raw_node(state: dict) -> dict:
    return {**state, "ok": True}

breaker = CircuitBreaker(
    name="bench",
    config=BreakerConfig(failure_threshold=100, call_timeout=None),
    fallback_strategy=CacheStrategy(),
)

@breaker.protect
async def protected_node(state: dict) -> dict:
    return {**state, "ok": True}

async def bench_raw():
    times = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        await raw_node({"x": 1})
        times.append((time.perf_counter() - t0) * 1_000_000)
    return times

async def bench_protected():
    times = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        await protected_node({"x": 1})
        times.append((time.perf_counter() - t0) * 1_000_000)
    return times

async def main():
    raw_times = await bench_raw()
    protected_times = await bench_protected()

    raw_mean = statistics.mean(raw_times)
    raw_median = statistics.median(raw_times)
    prot_mean = statistics.mean(protected_times)
    prot_median = statistics.median(protected_times)

    print("=" * 60)
    print(f"Raw call       - mean: {raw_mean:.2f}us, median: {raw_median:.2f}us")
    print(f"Protected call - mean: {prot_mean:.2f}us, median: {prot_median:.2f}us")
    print(f"Overhead (mean):   {prot_mean - raw_mean:.2f}us absolute")
    print(f"Overhead (mean):   {((prot_mean/raw_mean)-1)*100:.1f}% relative increase")
    print("=" * 60)

asyncio.run(main())