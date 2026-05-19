from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable
import structlog

logger = structlog.get_logger(__name__)


class FallbackStrategy(str, Enum):
    DEGRADE = "DEGRADE"
    CACHE = "CACHE"
    ESCALATE = "ESCALATE"
    DECOMPOSE = "DECOMPOSE"


@dataclass
class FallbackResult:
    state: dict[str, Any]
    strategy_used: FallbackStrategy
    degraded: bool = True
    confidence: float = 0.5
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseFallbackStrategy(ABC):
    @abstractmethod
    async def execute(
        self,
        state: dict[str, Any],
        breaker_name: str,
        failure_context: dict[str, Any],
    ) -> FallbackResult:
        ...


class CacheStrategy(BaseFallbackStrategy):
    def __init__(self, max_age_seconds: float = 300.0) -> None:
        self._max_age_seconds = max_age_seconds
        self._cache: dict[str, tuple[dict[str, Any], float]] = {}

    def store(self, breaker_name: str, state: dict[str, Any]) -> None:
        self._cache[breaker_name] = (dict(state), time.monotonic())

    async def execute(
        self,
        state: dict[str, Any],
        breaker_name: str,
        failure_context: dict[str, Any],
    ) -> FallbackResult:
        t0 = time.monotonic()

        if breaker_name not in self._cache:
            fallback_state = dict(state)
            fallback_state["__cascadebreaker_cache_miss__"] = True
            return FallbackResult(
                state=fallback_state,
                strategy_used=FallbackStrategy.CACHE,
                confidence=0.0,
                latency_ms=(time.monotonic() - t0) * 1000,
                metadata={"cache_hit": False},
            )

        cached_state, cached_at = self._cache[breaker_name]
        age_seconds = time.monotonic() - cached_at
        is_stale = age_seconds > self._max_age_seconds
        confidence = 0.2 if is_stale else 0.8

        returned_state = dict(cached_state)
        returned_state["__cascadebreaker_from_cache__"] = True

        return FallbackResult(
            state=returned_state,
            strategy_used=FallbackStrategy.CACHE,
            confidence=confidence,
            latency_ms=(time.monotonic() - t0) * 1000,
            metadata={"cache_hit": True, "age_seconds": round(age_seconds, 1)},
        )


class DegradeStrategy(BaseFallbackStrategy):
    def __init__(
        self,
        backup_fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
        confidence_override: float = 0.6,
    ) -> None:
        self._backup_fn = backup_fn
        self._confidence_override = confidence_override

    async def execute(
        self,
        state: dict[str, Any],
        breaker_name: str,
        failure_context: dict[str, Any],
    ) -> FallbackResult:
        t0 = time.monotonic()
        try:
            degraded_state = await self._backup_fn(state)
            return FallbackResult(
                state=degraded_state,
                strategy_used=FallbackStrategy.DEGRADE,
                confidence=self._confidence_override,
                latency_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            fallback_state = dict(state)
            fallback_state["__cascadebreaker_error__"] = str(exc)
            return FallbackResult(
                state=fallback_state,
                strategy_used=FallbackStrategy.DEGRADE,
                confidence=0.0,
                latency_ms=(time.monotonic() - t0) * 1000,
            )


class EscalateStrategy(BaseFallbackStrategy):
    def __init__(
        self,
        escalation_fn: Callable[
            [str, dict[str, Any], dict[str, Any]],
            Awaitable[dict[str, Any] | None],
        ],
        human_timeout_seconds: float = 5.0,
        notification_only: bool = False,
    ) -> None:
        self._escalation_fn = escalation_fn
        self._human_timeout_seconds = human_timeout_seconds
        self._notification_only = notification_only

    async def execute(
        self,
        state: dict[str, Any],
        breaker_name: str,
        failure_context: dict[str, Any],
    ) -> FallbackResult:
        t0 = time.monotonic()
        human_state: dict[str, Any] | None = None

        if self._notification_only:
            asyncio.create_task(
                self._escalation_fn(breaker_name, state, failure_context)
            )
        else:
            try:
                human_state = await asyncio.wait_for(
                    self._escalation_fn(breaker_name, state, failure_context),
                    timeout=self._human_timeout_seconds,
                )
            except (asyncio.TimeoutError, Exception):
                pass

        if human_state is not None:
            result_state = human_state
            confidence = 0.9
        else:
            result_state = dict(state)
            result_state["__cascadebreaker_escalated__"] = True
            confidence = 0.1

        return FallbackResult(
            state=result_state,
            strategy_used=FallbackStrategy.ESCALATE,
            confidence=confidence,
            latency_ms=(time.monotonic() - t0) * 1000,
        )


class DecomposeStrategy(BaseFallbackStrategy):
    def __init__(
        self,
        decompose_fn: Callable[[dict[str, Any]], Awaitable[list[dict[str, Any]]]],
        execute_fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
        merge_fn: Callable[
            [dict[str, Any], list[dict[str, Any]]], Awaitable[dict[str, Any]]
        ] | None = None,
        max_subtasks: int = 10,
        subtask_timeout: float = 15.0,
    ) -> None:
        self._decompose_fn = decompose_fn
        self._execute_fn = execute_fn
        self._merge_fn = merge_fn or self._default_merge
        self._max_subtasks = max_subtasks
        self._subtask_timeout = subtask_timeout

    @staticmethod
    async def _default_merge(
        original: dict[str, Any],
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        merged = dict(original)
        for result in results:
            merged.update(result)
        return merged

    async def execute(
        self,
        state: dict[str, Any],
        breaker_name: str,
        failure_context: dict[str, Any],
    ) -> FallbackResult:
        t0 = time.monotonic()

        try:
            subtasks = await self._decompose_fn(state)
        except Exception as exc:
            fallback_state = dict(state)
            fallback_state["__cascadebreaker_decompose_error__"] = str(exc)
            return FallbackResult(
                state=fallback_state,
                strategy_used=FallbackStrategy.DECOMPOSE,
                confidence=0.0,
                latency_ms=(time.monotonic() - t0) * 1000,
            )

        subtasks = subtasks[: self._max_subtasks]

        async def _run(sub: dict[str, Any]) -> dict[str, Any] | None:
            try:
                return await asyncio.wait_for(
                    self._execute_fn(sub),
                    timeout=self._subtask_timeout,
                )
            except Exception:
                return None

        raw = await asyncio.gather(*[_run(st) for st in subtasks])
        results = [r for r in raw if r is not None]
        success_rate = len(results) / len(subtasks) if subtasks else 0.0

        merged_state = await self._merge_fn(state, results)

        return FallbackResult(
            state=merged_state,
            strategy_used=FallbackStrategy.DECOMPOSE,
            confidence=success_rate * 0.8,
            latency_ms=(time.monotonic() - t0) * 1000,
            metadata={"subtask_count": len(subtasks), "succeeded": len(results)},
        )