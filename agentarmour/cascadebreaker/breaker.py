from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Callable, Awaitable, TypeVar, Optional
import structlog

from agentarmour.cascadebreaker.config import BreakerConfig
from agentarmour.cascadebreaker.states import (
    BreakerState,
    BreakerStateMachine,
    FailureCategory,
    FailureRecord,
)
from agentarmour.cascadebreaker.strategies import (
    BaseFallbackStrategy,
    CacheStrategy,
    DegradeStrategy,
    DecomposeStrategy,
    EscalateStrategy,
    FallbackResult,
    FallbackStrategy,
)

logger = structlog.get_logger(__name__)

NodeFn = TypeVar("NodeFn", bound=Callable[..., Awaitable[dict[str, Any]]])


def _classify_exception(exc: Exception) -> FailureCategory:
    exc_type = type(exc).__name__.lower()
    msg = str(exc).lower()

    if "timeout" in exc_type or "timeout" in msg:
        return FailureCategory.LATENCY_BREACH
    if "recursion" in exc_type or "loop" in msg:
        return FailureCategory.REASONING_LOOP
    if "token" in msg or "context" in msg or "length" in msg:
        return FailureCategory.CONTEXT_OVERFLOW
    if "tool" in msg or "function" in msg:
        return FailureCategory.TOOL_CALL_FAILURE
    if "invalid" in msg and "state" in msg:
        return FailureCategory.STATE_CORRUPTION
    return FailureCategory.EXCEPTION


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        config: Optional[BreakerConfig] = None,
        fallback_strategy: Any = FallbackStrategy.CACHE,
        on_open: Optional[Callable[[str], Awaitable[None]]] = None,
        on_close: Optional[Callable[[str], Awaitable[None]]] = None,
        on_half_open: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> None:
        self.name = name
        self.config = config or BreakerConfig()

        if isinstance(fallback_strategy, FallbackStrategy):
            self._strategy_enum = fallback_strategy
            self._strategy = self._build_default_strategy(fallback_strategy)
        else:
            self._strategy_enum = None
            self._strategy = fallback_strategy

        self._state_machine = BreakerStateMachine(
            breaker_name=name,
            failure_threshold=self.config.failure_threshold,
            recovery_timeout=self.config.recovery_timeout,
            window_seconds=self.config.window_seconds,
            half_open_max_calls=self.config.half_open_max_calls,
        )

        self._on_open = on_open
        self._on_close = on_close
        self._on_half_open = on_half_open
        self._prev_state: BreakerState = BreakerState.CLOSED

        logger.info(
            "circuit_breaker.created",
            name=name,
            strategy=str(fallback_strategy),
            failure_threshold=self.config.failure_threshold,
        )

    @property
    def state(self) -> BreakerState:
        return self._state_machine.state

    @property
    def metrics(self) -> dict[str, Any]:
        return self._state_machine.metrics

    @property
    def is_open(self) -> bool:
        return self._state_machine.state is BreakerState.OPEN

    @property
    def is_closed(self) -> bool:
        return self._state_machine.state is BreakerState.CLOSED

    def protect(self, fn: NodeFn) -> NodeFn:
        if not asyncio.iscoroutinefunction(fn):
            raise TypeError(
                f"CircuitBreaker.protect requires an async function; "
                f"'{fn.__name__}' is synchronous."
            )

        @functools.wraps(fn)
        async def _wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            state = kwargs.get("state") or (args[0] if args else {})
            if not isinstance(state, dict):
                state = {}
            return await self.call(fn, state, *args[1:], **kwargs)

        _wrapper.__cascadebreaker__ = self
        _wrapper.__wrapped__ = fn
        return _wrapper

    async def call(
        self,
        fn: Callable[..., Awaitable[dict[str, Any]]],
        state: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not self.config.enabled:
            return await fn(state, *args, **kwargs)

        permitted = await self._state_machine.is_call_permitted()
        prev_state = self._prev_state

        if not permitted:
            logger.info(
                "circuit_breaker.short_circuited",
                name=self.name,
                state=self.state.value,
            )
            await self._state_machine.record_fallback()
            result = await self._invoke_fallback(state, {})
            return result.state

        t0 = time.monotonic()
        try:
            if self.config.call_timeout is not None:
                result_state = await asyncio.wait_for(
                    fn(state, *args, **kwargs),
                    timeout=self.config.call_timeout,
                )
            else:
                result_state = await fn(state, *args, **kwargs)

            if isinstance(self._strategy, CacheStrategy):
                self._strategy.store(self.name, result_state)

            await self._state_machine.record_success()
            await self._fire_transition_callbacks(prev_state)
            self._prev_state = self.state
            return result_state

        except asyncio.TimeoutError as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            return await self._handle_failure(
                exc=exc,
                state=state,
                latency_ms=latency_ms,
                category=FailureCategory.LATENCY_BREACH,
                prev_state=prev_state,
            )

        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            return await self._handle_failure(
                exc=exc,
                state=state,
                latency_ms=latency_ms,
                category=_classify_exception(exc),
                prev_state=prev_state,
            )

    async def _handle_failure(
        self,
        exc: Exception,
        state: dict[str, Any],
        latency_ms: float,
        category: FailureCategory,
        prev_state: BreakerState,
    ) -> dict[str, Any]:
        record = FailureRecord(
            breaker_name=self.name,
            category=category,
            error_type=f"{type(exc).__module__}.{type(exc).__name__}",
            error_message=str(exc),
            latency_ms=latency_ms,
        )
        await self._state_machine.record_failure(record)
        await self._state_machine.record_fallback()
        await self._fire_transition_callbacks(prev_state)
        self._prev_state = self.state

        failure_context = {
            "last_error": str(exc),
            "failure_count": self._state_machine.failure_count,
            "category": category.value,
        }
        result = await self._invoke_fallback(state, failure_context)
        return result.state

    async def _invoke_fallback(
        self,
        state: dict[str, Any],
        failure_context: dict[str, Any],
    ) -> FallbackResult:
        try:
            return await self._strategy.execute(
                state=state,
                breaker_name=self.name,
                failure_context=failure_context,
            )
        except Exception as exc:
            logger.error(
                "circuit_breaker.fallback_strategy_error",
                name=self.name,
                error=str(exc),
            )
            safe_state = dict(state)
            safe_state["__cascadebreaker_fallback_failed__"] = str(exc)
            return FallbackResult(
                state=safe_state,
                strategy_used=FallbackStrategy.CACHE,
                degraded=True,
                confidence=0.0,
            )

    async def _fire_transition_callbacks(self, prev_state: BreakerState) -> None:
        current = self.state
        if current == prev_state:
            return
        try:
            if current is BreakerState.OPEN and self._on_open:
                await self._on_open(self.name)
            elif current is BreakerState.CLOSED and self._on_close:
                await self._on_close(self.name)
            elif current is BreakerState.HALF_OPEN and self._on_half_open:
                await self._on_half_open(self.name)
        except Exception as exc:
            logger.warning(
                "circuit_breaker.callback_error",
                name=self.name,
                error=str(exc),
            )

    async def reset(self) -> None:
        await self._state_machine.reset()
        self._prev_state = BreakerState.CLOSED

    def _build_default_strategy(
        self, strategy_enum: FallbackStrategy
    ) -> BaseFallbackStrategy:
        if strategy_enum is FallbackStrategy.CACHE:
            return CacheStrategy()

        if strategy_enum is FallbackStrategy.DEGRADE:
            async def _noop_backup(state: dict[str, Any]) -> dict[str, Any]:
                return state
            return DegradeStrategy(backup_fn=_noop_backup, confidence_override=0.1)

        if strategy_enum is FallbackStrategy.ESCALATE:
            async def _noop_escalate(
                breaker_name: str,
                state: dict[str, Any],
                context: dict[str, Any],
            ) -> Optional[dict[str, Any]]:
                return None
            return EscalateStrategy(
                escalation_fn=_noop_escalate,
                notification_only=True,
            )

        if strategy_enum is FallbackStrategy.DECOMPOSE:
            async def _noop_decompose(state: dict[str, Any]) -> list[dict[str, Any]]:
                return [state]
            async def _noop_execute(sub: dict[str, Any]) -> dict[str, Any]:
                return sub
            return DecomposeStrategy(
                decompose_fn=_noop_decompose,
                execute_fn=_noop_execute,
            )

        raise ValueError(f"Unknown FallbackStrategy: {strategy_enum}")

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name={self.name!r}, "
            f"state={self.state.value})"
        )