"""
CascadeBreaker — Circuit breaker and self-healing layer for LangGraph multi-agent systems.
"""

from agentarmour.cascadebreaker.breaker import CircuitBreaker
from agentarmour.cascadebreaker.config import BreakerConfig
from agentarmour.cascadebreaker.states import BreakerState, FailureRecord, StateTransition
from agentarmour.cascadebreaker.strategies import (
    FallbackStrategy,
    FallbackResult,
    DegradeStrategy,
    CacheStrategy,
    EscalateStrategy,
    DecomposeStrategy,
)
from agentarmour.cascadebreaker.guard import CascadeGuard
from agentarmour.cascadebreaker.registry import BreakerRegistry, get_registry

__all__ = [
    "CircuitBreaker",
    "BreakerConfig",
    "BreakerState",
    "FailureRecord",
    "StateTransition",
    "FallbackStrategy",
    "FallbackResult",
    "DegradeStrategy",
    "CacheStrategy",
    "EscalateStrategy",
    "DecomposeStrategy",
    "CascadeGuard",
    "BreakerRegistry",
    "get_registry",
]