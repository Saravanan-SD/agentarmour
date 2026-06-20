from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Callable, Awaitable, Optional
import structlog

logger = structlog.get_logger(__name__)


class QuarantineEntry:
    __slots__ = ("field", "source_node", "reason", "quarantined_at", "expires_at")

    def __init__(
        self,
        field: str,
        source_node: str,
        reason: str,
        quarantined_at: Optional[float] = None,
        expires_at: Optional[float] = None,
    ) -> None:
        self.field = field
        self.source_node = source_node
        self.reason = reason
        self.quarantined_at = quarantined_at or time.time()
        self.expires_at = expires_at

    @property
    def is_active(self) -> bool:
        if self.expires_at is None:
            return True
        return time.time() < self.expires_at


class ContaminatedStateError(Exception):
    def __init__(
        self,
        field: str,
        node_name: str,
        quarantine_info: list[QuarantineEntry],
    ) -> None:
        reasons = "; ".join(
            f"{e.source_node}: {e.reason}" for e in quarantine_info if e.is_active
        )
        super().__init__(
            f"Node '{node_name}' attempted to read quarantined field "
            f"'{field}'. Sources: [{reasons}]"
        )
        self.field = field
        self.node_name = node_name
        self.quarantine_info = quarantine_info


class CascadeGuard:
    def __init__(
        self,
        quarantine_ttl_seconds: Optional[float] = 300.0,
        strict_mode: bool = False,
    ) -> None:
        self._quarantine_ttl = quarantine_ttl_seconds
        self._strict_mode = strict_mode
        self._quarantines: dict[str, list[QuarantineEntry]] = {}
        self._lock = asyncio.Lock()
        self._total_contaminations_blocked: int = 0

        logger.info(
            "cascade_guard.initialised",
            quarantine_ttl=quarantine_ttl_seconds,
            strict_mode=strict_mode,
        )

    async def quarantine_field(
        self,
        field: str,
        source_node: str,
        reason: str = "Unknown contamination source",
    ) -> None:
        async with self._lock:
            expires_at = (
                time.time() + self._quarantine_ttl
                if self._quarantine_ttl is not None
                else None
            )
            entry = QuarantineEntry(
                field=field,
                source_node=source_node,
                reason=reason,
                expires_at=expires_at,
            )
            self._quarantines.setdefault(field, []).append(entry)

        logger.warning(
            "cascade_guard.field_quarantined",
            field=field,
            source_node=source_node,
            reason=reason,
        )

    async def lift_quarantine(self, field: str) -> bool:
        async with self._lock:
            if field in self._quarantines:
                del self._quarantines[field]
                return True
        return False

    def is_quarantined(self, field: str) -> bool:
        entries = self._quarantines.get(field, [])
        return any(e.is_active for e in entries)

    @property
    def quarantined_fields(self) -> list[str]:
        return [
            f for f, entries in self._quarantines.items()
            if any(e.is_active for e in entries)
        ]

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "quarantined_fields": self.quarantined_fields,
            "quarantine_count": len(self.quarantined_fields),
            "total_contaminations_blocked": self._total_contaminations_blocked,
        }

    def sanitise_state(
        self,
        state: dict[str, Any],
        node_name: str,
        reads_from: Optional[list[str]] = None,
        field_defaults: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        sanitised = dict(state)
        fields_to_check = reads_from if reads_from else list(state.keys())
        defaults = field_defaults or {}

        for field in fields_to_check:
            if field in state and self.is_quarantined(field):
                if self._strict_mode:
                    raise ContaminatedStateError(
                        field=field,
                        node_name=node_name,
                        quarantine_info=self._quarantines.get(field, []),
                    )
                replacement = defaults.get(field, None)
                sanitised[field] = replacement
                self._total_contaminations_blocked += 1
                logger.warning(
                    "cascade_guard.contamination_blocked",
                    field=field,
                    node=node_name,
                )

        return sanitised

    def protect_node(
        self,
        node_name: str,
        quarantine_on_failure: Optional[list[str]] = None,
        reads_from: Optional[list[str]] = None,
        field_defaults: Optional[dict[str, Any]] = None,
    ) -> Callable[
        [Callable[..., Awaitable[dict[str, Any]]]],
        Callable[..., Awaitable[dict[str, Any]]],
    ]:
        def decorator(
            fn: Callable[..., Awaitable[dict[str, Any]]]
        ) -> Callable[..., Awaitable[dict[str, Any]]]:

            @functools.wraps(fn)
            async def _wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
                state: dict[str, Any] = kwargs.get("state") or (
                    args[0] if args else {}
                )

                clean_state = self.sanitise_state(
                    state=state,
                    node_name=node_name,
                    reads_from=reads_from,
                    field_defaults=field_defaults,
                )

                new_args = (clean_state,) + args[1:] if args else args
                new_kwargs = (
                    {**kwargs, "state": clean_state}
                    if "state" in kwargs
                    else kwargs
                )

                try:
                    return await fn(*new_args, **new_kwargs)
                except Exception as exc:
                    if quarantine_on_failure:
                        for field in quarantine_on_failure:
                            await self.quarantine_field(
                                field=field,
                                source_node=node_name,
                                reason=f"Node failed: {type(exc).__name__}: {exc}",
                            )
                    raise

            _wrapper.__cascade_guard__ = self
            return _wrapper

        return