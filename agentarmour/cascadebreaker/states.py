from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import structlog

logger = structlog.get_logger(__name__)


class BreakerState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class FailureCategory(str, Enum):
    REASONING_LOOP = "REASONING_LOOP"
    HALLUCINATION_STORM = "HALLUCINATION_STORM"
    TOOL_CALL_FAILURE = "TOOL_CALL_FAILURE"
    STATE_CORRUPTION = "STATE_CORRUPTION"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    LATENCY_BREACH = "LATENCY_BREACH"
    EXCEPTION = "EXCEPTION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class FailureRecord:
    breaker_name: str
    category: FailureCategory
    error_type: str
    error_message: str
    timestamp: float = field(default_factory=time.time)
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def age_seconds(self) -> float:
        return time.time() - self.timestamp


@dataclass(frozen=True, slots=True)
class StateTransition:
    breaker_name: str
    from_state: BreakerState
    to_state: BreakerState
    reason: str
    timestamp: float = field(default_factory=time.time)
    failure_count: int = 0


class BreakerStateMachine:
    def __init__(
        self,
        breaker_name: str,
        failure_threshold: int,
        recovery_timeout: float,
        window_seconds: float,
        half_open_max_calls: int = 1,
    ) -> None:
        self.breaker_name = breaker_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.window_seconds = window_seconds
        self.half_open_max_calls = half_open_max_calls

        self._state: BreakerState = BreakerState.CLOSED
        self._failures: list[FailureRecord] = []
        self._transitions: list[StateTransition] = []
        self._opened_at: float | None = None
        self._half_open_calls: int = 0
        self._total_calls: int = 0
        self._total_failures: int = 0
        self._total_fallbacks: int = 0
        self._lock = asyncio.Lock()

        logger.info(
            "breaker.initialised",
            breaker=breaker_name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

    @property
    def state(self) -> BreakerState:
        return self._state

    @property
    def failure_count(self) -> int:
        self._evict_stale_failures()
        return len(self._failures)

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "breaker_name": self.breaker_name,
            "state": self._state.value,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "total_fallbacks": self._total_fallbacks,
            "failure_count_window": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "opened_at": self._opened_at,
            "recovery_timeout": self.recovery_timeout,
            "success_rate": self._success_rate(),
        }

    def _success_rate(self) -> float:
        if self._total_calls == 0:
            return 1.0
        return (self._total_calls - self._total_failures) / self._total_calls

    def _evict_stale_failures(self) -> None:
        cutoff = time.time() - self.window_seconds
        self._failures = [f for f in self._failures if f.timestamp >= cutoff]

    async def is_call_permitted(self) -> bool:
        async with self._lock:
            self._total_calls += 1

            if self._state is BreakerState.CLOSED:
                return True

            if self._state is BreakerState.OPEN:
                if self._should_attempt_recovery():
                    await self._transition_to(
                        BreakerState.HALF_OPEN,
                        reason=f"Recovery timeout ({self.recovery_timeout}s) elapsed",
                    )
                    self._half_open_calls = 1
                    return True
                return False

            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    async def record_success(self) -> None:
        async with self._lock:
            if self._state is BreakerState.HALF_OPEN:
                await self._transition_to(
                    BreakerState.CLOSED,
                    reason="Probe call succeeded — agent recovered",
                )
                self._failures.clear()
                self._half_open_calls = 0

    async def record_failure(self, record: FailureRecord) -> None:
        async with self._lock:
            self._total_failures += 1
            self._failures.append(record)
            self._evict_stale_failures()

            logger.warning(
                "breaker.failure_recorded",
                breaker=self.breaker_name,
                category=record.category.value,
                error=record.error_message,
                failure_count=len(self._failures),
                threshold=self.failure_threshold,
            )

            if self._state is BreakerState.HALF_OPEN:
                await self._transition_to(
                    BreakerState.OPEN,
                    reason=f"Probe call failed: {record.error_message}",
                )
                self._opened_at = time.time()
                self._half_open_calls = 0
                return

            if (
                self._state is BreakerState.CLOSED
                and len(self._failures) >= self.failure_threshold
            ):
                await self._transition_to(
                    BreakerState.OPEN,
                    reason=f"Failure threshold ({self.failure_threshold}) exceeded",
                )
                self._opened_at = time.time()

    async def record_fallback(self) -> None:
        async with self._lock:
            self._total_fallbacks += 1

    def _should_attempt_recovery(self) -> bool:
        if self._opened_at is None:
            return False
        return (time.time() - self._opened_at) >= self.recovery_timeout

    async def _transition_to(self, new_state: BreakerState, reason: str) -> None:
        transition = StateTransition(
            breaker_name=self.breaker_name,
            from_state=self._state,
            to_state=new_state,
            reason=reason,
            failure_count=len(self._failures),
        )
        self._transitions.append(transition)
        self._state = new_state

        logger.info(
            "breaker.state_transition",
            breaker=self.breaker_name,
            from_state=transition.from_state.value,
            to_state=new_state.value,
            reason=reason,
        )

    async def reset(self) -> None:
        async with self._lock:
            old_state = self._state
            self._state = BreakerState.CLOSED
            self._failures.clear()
            self._opened_at = None
            self._half_open_calls = 0
            self._transitions.append(
                StateTransition(
                    breaker_name=self.breaker_name,
                    from_state=old_state,
                    to_state=BreakerState.CLOSED,
                    reason="Manual administrative reset",
                )
            )
            logger.info("breaker.manual_reset", breaker=self.breaker_name)