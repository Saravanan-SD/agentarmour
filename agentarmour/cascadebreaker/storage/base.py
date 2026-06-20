"""
Abstract base class for CascadeBreaker audit ledgers.

An audit ledger persists every failure and state transition a circuit
breaker records, so they survive process restarts and can be queried later
by a dashboard or analysis tool.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from agentarmour.cascadebreaker.states import FailureRecord, StateTransition


class AuditLedger(ABC):
    """Base class all audit ledger backends must implement.

    Implementations are responsible for their own lazy initialisation
    (e.g. creating tables on first use) and should be safe to call
    concurrently from multiple circuit breakers in the same process.
    """

    @abstractmethod
    async def log_failure(self, record: FailureRecord) -> None:
        """Persist a single failure record."""
        ...

    @abstractmethod
    async def log_transition(self, transition: StateTransition) -> None:
        """Persist a single state transition."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release any held resources (connections, file handles, etc.)."""
        ...