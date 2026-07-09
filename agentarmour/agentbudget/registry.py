# agentarmour/agentbudget/registry.py
import time
from .usage import UsageRecord, BudgetEvent

import asyncio
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

from .config import BudgetConfig
from .breaker import BudgetState, evaluate


# holds the current run id for whatever task is running right now
_current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)


@contextmanager
def run_context(run_id: str | None = None):
    token = _current_run_id.set(run_id or uuid.uuid4().hex)
    try:
        yield _current_run_id.get()
    finally:
        _current_run_id.reset(token)


def current_run_id() -> str | None:
    return _current_run_id.get()


_ORDER = {BudgetState.WITHIN: 0, BudgetState.WARNING: 1, BudgetState.EXCEEDED: 2}


def _worst(states: list[BudgetState]) -> BudgetState:
    return max(states, key=lambda s: _ORDER[s])


class BudgetRegistry:
    def __init__(self, config: BudgetConfig, ledger=None):
        self.config = config
        self.ledger = ledger
        self._lock = asyncio.Lock()
        self._global = UsageRecord()
        self._runs: dict[str, UsageRecord] = {}
        self._nodes: dict[str, UsageRecord] = {}

    async def record(
        self,
        node: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> BudgetState:
        run_id = current_run_id()

        async with self._lock:
            self._global.add(input_tokens, output_tokens, cost_usd)

            node_usage = self._nodes.setdefault(node, UsageRecord())
            node_usage.add(input_tokens, output_tokens, cost_usd)

            run_cost = 0.0
            if run_id is not None:
                run_usage = self._runs.setdefault(run_id, UsageRecord())
                run_usage.add(input_tokens, output_tokens, cost_usd)
                run_cost = run_usage.cost_usd

            # snapshot the totals while we still hold the lock
            node_cost = node_usage.cost_usd
            global_cost = self._global.cost_usd

        states = [
            evaluate(node_cost, self.config.node_limit_usd, self.config.warn_threshold),
            evaluate(run_cost, self.config.run_limit_usd, self.config.warn_threshold),
            evaluate(global_cost, self.config.global_limit_usd, self.config.warn_threshold),
        ]
        state = _worst(states)

        if self.ledger is not None:
            event = BudgetEvent(
                node=node,
                run_id=run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                state=state.value,
                timestamp=time.time(),
            )
            await self.ledger.log_event(event)

        return state