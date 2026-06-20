import logging
import structlog
logging.basicConfig(level=logging.CRITICAL)
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))

import asyncio
from agentarmour.cascadebreaker import CircuitBreaker, BreakerConfig
from agentarmour.cascadebreaker.strategies import CacheStrategy

breaker = CircuitBreaker(
    name="trace_test",
    config=BreakerConfig(failure_threshold=100, call_timeout=None),
    fallback_strategy=CacheStrategy(),
)

@breaker.protect
async def failing_node(state: dict) -> dict:
    def inner_fn():
        raise ValueError("Something specific broke deep in here")
    inner_fn()
    return state

async def main():
    print("Calling a node that raises ValueError deep in a nested call...")
    result = await failing_node({"x": 1})
    print(f"Returned result (no exception propagated): {result}")
    print()
    print("If you see a clean dict above with no Python traceback printed,")
    print("that confirms the original error and its stack trace were swallowed.")

asyncio.run(main())