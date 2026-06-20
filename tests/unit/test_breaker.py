"""Unit tests for agentarmour.cascadebreaker.breaker — CircuitBreaker class."""

from __future__ import annotations

import asyncio
import pytest

from agentarmour.cascadebreaker import CircuitBreaker, BreakerConfig, FallbackStrategy
from agentarmour.cascadebreaker.states import BreakerState
from agentarmour.cascadebreaker.strategies import CacheStrategy


@pytest.fixture
def config() -> BreakerConfig:
    return BreakerConfig(
        failure_threshold=2,
        recovery_timeout=0.1,
        window_seconds=5.0,
        call_timeout=1.0,
    )


@pytest.fixture
def cache_breaker(config: BreakerConfig) -> CircuitBreaker:
    return CircuitBreaker(
        name="test_breaker",
        config=config,
        fallback_strategy=CacheStrategy(max_age_seconds=60),
    )


class TestDecoratorPattern:
    @pytest.mark.asyncio
    async def test_protect_decorator_passes_through_on_success(
        self, cache_breaker: CircuitBreaker
    ) -> None:
        @cache_breaker.protect
        async def node(state: dict) -> dict:
            return {**state, "processed": True}

        result = await node({"input": "hello"})
        assert result["processed"] is True

    @pytest.mark.asyncio
    async def test_protect_attaches_breaker_attribute(
        self, cache_breaker: CircuitBreaker
    ) -> None:
        @cache_breaker.protect
        async def node(state: dict) -> dict:
            return state

        assert hasattr(node, "__cascadebreaker__")
        assert node.__cascadebreaker__ is cache_breaker

    def test_protect_rejects_sync_functions(
        self, cache_breaker: CircuitBreaker
    ) -> None:
        with pytest.raises(TypeError, match="async function"):
            @cache_breaker.protect
            def sync_node(state: dict) -> dict:  # type: ignore
                return state


class TestFailureHandling:
    @pytest.mark.asyncio
    async def test_trips_after_threshold(self, cache_breaker: CircuitBreaker) -> None:
        @cache_breaker.protect
        async def flaky_node(state: dict) -> dict:
            raise RuntimeError("agent down")

        for _ in range(3):
            await flaky_node({"q": "test"})

        assert cache_breaker.state is BreakerState.OPEN

    @pytest.mark.asyncio
    async def test_short_circuits_when_open(self, cache_breaker: CircuitBreaker) -> None:
        real_call_count = 0

        @cache_breaker.protect
        async def tracked_node(state: dict) -> dict:
            nonlocal real_call_count
            real_call_count += 1
            raise RuntimeError("down")

        for _ in range(3):
            await tracked_node({"q": "test"})

        assert cache_breaker.state is BreakerState.OPEN
        calls_before = real_call_count

        await tracked_node({"q": "next"})
        assert real_call_count == calls_before

    @pytest.mark.asyncio
    async def test_recovery_cycle(self, config: BreakerConfig) -> None:
        """Full CLOSED -> OPEN -> HALF_OPEN -> CLOSED cycle."""
        fail_count = 0
        max_fails = 2

        breaker = CircuitBreaker(
            name="recovery_test",
            config=config,
            fallback_strategy=CacheStrategy(),
        )

        @breaker.protect
        async def recoverable_node(state: dict) -> dict:
            nonlocal fail_count
            if fail_count < max_fails:
                fail_count += 1
                raise RuntimeError("temporary failure")
            return {**state, "ok": True}

        await recoverable_node({"x": 1})
        await recoverable_node({"x": 2})
        assert breaker.state is BreakerState.OPEN

        await asyncio.sleep(0.15)

        result = await recoverable_node({"x": 3})
        assert breaker.state is BreakerState.CLOSED
        assert result.get("ok") is True


class TestTimeoutHandling:
    @pytest.mark.asyncio
    async def test_slow_node_triggers_timeout_failure(self) -> None:
        breaker = CircuitBreaker(
            name="timeout_test",
            config=BreakerConfig(
                failure_threshold=1,
                recovery_timeout=60,
                call_timeout=0.05,
            ),
            fallback_strategy=CacheStrategy(),
        )

        @breaker.protect
        async def slow_node(state: dict) -> dict:
            await asyncio.sleep(1.0)
            return state

        await slow_node({"q": "slow"})
        assert breaker.state is BreakerState.OPEN


class TestCallbacks:
    @pytest.mark.asyncio
    async def test_on_open_callback_fires(self) -> None:
        fired: list[str] = []

        async def on_open(name: str) -> None:
            fired.append(name)

        breaker = CircuitBreaker(
            name="cb_test",
            config=BreakerConfig(failure_threshold=1, recovery_timeout=60),
            fallback_strategy=CacheStrategy(),
            on_open=on_open,
        )

        @breaker.protect
        async def fail_node(state: dict) -> dict:
            raise RuntimeError("fail")

        await fail_node({})
        assert "cb_test" in fired


class TestDisabledBreaker:
    @pytest.mark.asyncio
    async def test_disabled_breaker_passes_through(self) -> None:
        breaker = CircuitBreaker(
            name="disabled_test",
            config=BreakerConfig(failure_threshold=1, enabled=False),
            fallback_strategy=FallbackStrategy.CACHE,
        )

        @breaker.protect
        async def node(state: dict) -> dict:
            raise RuntimeError("this should propagate")

        with pytest.raises(RuntimeError, match="this should propagate"):
            await node({})


class TestTracebackCapture:
    @pytest.mark.asyncio
    async def test_traceback_attached_to_fallback_state(self) -> None:
        breaker = CircuitBreaker(
            name="traceback_test",
            config=BreakerConfig(failure_threshold=100, call_timeout=None),
            fallback_strategy=CacheStrategy(),
        )

        @breaker.protect
        async def failing_node(state: dict) -> dict:
            def inner_fn():
                raise ValueError("specific failure")
            inner_fn()
            return state

        result = await failing_node({"x": 1})
        assert "__cascadebreaker_traceback__" in result
        assert "inner_fn" in result["__cascadebreaker_traceback__"]
        assert "ValueError" in result["__cascadebreaker_traceback__"]