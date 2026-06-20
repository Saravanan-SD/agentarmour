from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from agentarmour.cascadebreaker.breaker import CircuitBreaker

logger = structlog.get_logger(__name__)


class BreakerRegistry:
    def __init__(self) -> None:
        self._breakers: dict[str, "CircuitBreaker"] = {}
        self._lock = asyncio.Lock()

    def register(self, breaker: "CircuitBreaker") -> None:
        self._breakers[breaker.name] = breaker
        logger.debug("registry.registered", name=breaker.name)

    def unregister(self, name: str) -> None:
        self._breakers.pop(name, None)
        logger.debug("registry.unregistered", name=name)

    def get(self, name: str):
        return self._breakers.get(name)

    def all(self) -> list["CircuitBreaker"]:
        return list(self._breakers.values())

    def snapshot(self) -> list[dict[str, Any]]:
        return [b.metrics for b in self._breakers.values()]

    async def reset_all(self) -> None:
        for breaker in self._breakers.values():
            await breaker.reset()
        logger.info("registry.all_reset", count=len(self._breakers))

    async def reset(self, name: str) -> bool:
        breaker = self._breakers.get(name)
        if breaker:
            await breaker.reset()
            return True
        return False

    def __len__(self) -> int:
        return len(self._breakers)

    def __repr__(self) -> str:
        return f"BreakerRegistry(breakers={list(self._breakers.keys())})"


_registry: "BreakerRegistry | None" = None


def get_registry() -> BreakerRegistry:
    global _registry
    if _registry is None:
        _registry = BreakerRegistry()
    return _registry