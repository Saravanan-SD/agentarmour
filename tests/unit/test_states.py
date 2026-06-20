"""Unit tests for agentarmour.cascadebreaker.states — the state machine core."""

from __future__ import annotations

import asyncio
import pytest

from agentarmour.cascadebreaker.states import (
    BreakerState,
    BreakerStateMachine,
    FailureCategory,
    FailureRecord,
)


@pytest.fixture
def machine() -> BreakerStateMachine:
    return BreakerStateMachine(
        breaker_name="test",
        failure_threshold=3,
        recovery_timeout=0.1,
        window_seconds=5.0,
    )


class TestInitialState:
    def test_starts_closed(self, machine: BreakerStateMachine) -> None:
        assert machine.state is BreakerState.CLOSED

    def test_zero_failures_initially(self, machine: BreakerStateMachine) -> None:
        assert machine.failure_count == 0

    def test_metrics_structure(self, machine: BreakerStateMachine) -> None:
        m = machine.metrics
        assert m["breaker_name"] == "test"
        assert m["state"] == "CLOSED"
        assert m["total_calls"] == 0


class TestClosedState:
    @pytest.mark.asyncio
    async def test_permits_calls_when_closed(self, machine: BreakerStateMachine) -> None:
        assert await machine.is_call_permitted() is True

    @pytest.mark.asyncio
    async def test_trips_at_threshold(self, machine: BreakerStateMachine) -> None:
        for _ in range(3):
            await machine.record_failure(FailureRecord(
                breaker_name="test",
                category=FailureCategory.EXCEPTION,
                error_type="RuntimeError",
                error_message="boom",
            ))
        assert machine.state is BreakerState.OPEN

    @pytest.mark.asyncio
    async def test_does_not_trip_below_threshold(self, machine: BreakerStateMachine) -> None:
        for _ in range(2):
            await machine.record_failure(FailureRecord(
                breaker_name="test",
                category=FailureCategory.EXCEPTION,
                error_type="RuntimeError",
                error_message="boom",
            ))
        assert machine.state is BreakerState.CLOSED


class TestOpenState:
    @pytest.mark.asyncio
    async def test_blocks_calls_when_open(self, machine: BreakerStateMachine) -> None:
        for _ in range(3):
            await machine.record_failure(FailureRecord(
                breaker_name="test",
                category=FailureCategory.EXCEPTION,
                error_type="RuntimeError",
                error_message="boom",
            ))
        assert machine.state is BreakerState.OPEN
        permitted = await machine.is_call_permitted()
        assert permitted is False

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(
        self, machine: BreakerStateMachine
    ) -> None:
        for _ in range(3):
            await machine.record_failure(FailureRecord(
                breaker_name="test",
                category=FailureCategory.EXCEPTION,
                error_type="RuntimeError",
                error_message="boom",
            ))
        await asyncio.sleep(0.15)
        permitted = await machine.is_call_permitted()
        assert permitted is True
        assert machine.state is BreakerState.HALF_OPEN


class TestHalfOpenState:
    @pytest.mark.asyncio
    async def test_success_in_half_open_closes_breaker(
        self, machine: BreakerStateMachine
    ) -> None:
        for _ in range(3):
            await machine.record_failure(FailureRecord(
                breaker_name="test",
                category=FailureCategory.EXCEPTION,
                error_type="RuntimeError",
                error_message="boom",
            ))
        await asyncio.sleep(0.15)
        await machine.is_call_permitted()
        await machine.record_success()
        assert machine.state is BreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_failure_in_half_open_reopens(
        self, machine: BreakerStateMachine
    ) -> None:
        for _ in range(3):
            await machine.record_failure(FailureRecord(
                breaker_name="test",
                category=FailureCategory.EXCEPTION,
                error_type="RuntimeError",
                error_message="boom",
            ))
        await asyncio.sleep(0.15)
        await machine.is_call_permitted()
        await machine.record_failure(FailureRecord(
            breaker_name="test",
            category=FailureCategory.EXCEPTION,
            error_type="RuntimeError",
            error_message="still broken",
        ))
        assert machine.state is BreakerState.OPEN


class TestManualReset:
    @pytest.mark.asyncio
    async def test_reset_closes_open_breaker(self, machine: BreakerStateMachine) -> None:
        for _ in range(3):
            await machine.record_failure(FailureRecord(
                breaker_name="test",
                category=FailureCategory.EXCEPTION,
                error_type="RuntimeError",
                error_message="boom",
            ))
        assert machine.state is BreakerState.OPEN
        await machine.reset()
        assert machine.state is BreakerState.CLOSED
        assert machine.failure_count == 0


class TestWindowEviction:
    @pytest.mark.asyncio
    async def test_old_failures_evicted(self) -> None:
        machine = BreakerStateMachine(
            breaker_name="evict_test",
            failure_threshold=3,
            recovery_timeout=60,
            window_seconds=0.05,
        )
        for _ in range(2):
            await machine.record_failure(FailureRecord(
                breaker_name="evict_test",
                category=FailureCategory.EXCEPTION,
                error_type="RuntimeError",
                error_message="old",
            ))
        await asyncio.sleep(0.1)
        assert machine.failure_count == 0
        assert machine.state is BreakerState.CLOSED