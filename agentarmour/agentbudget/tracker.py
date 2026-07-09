# agentarmour/agentbudget/tracker.py
from __future__ import annotations

import functools
from contextvars import ContextVar

import structlog

from .config import BudgetConfig, OverBudgetAction
from .pricing import cost_usd
from .breaker import BudgetState
from .registry import BudgetRegistry

logger = structlog.get_logger(__name__)

# per-task buffer of LLM calls seen during one node run
_usage_buffer: ContextVar[list | None] = ContextVar("usage_buffer", default=None)


class BudgetExceeded(Exception):
    """Raised when a limit is hit and the action is BLOCK."""

    def __init__(self, node: str, state: BudgetState) -> None:
        self.node = node
        self.state = state
        super().__init__(f"Budget exceeded at node '{node}' (state={state.value})")


def report(model: str, input_tokens: int, output_tokens: int) -> None:
    """Manually add one LLM call's tokens to the current node's buffer.

    Does nothing if called outside a tracked node, so it is always safe.
    """
    buffer = _usage_buffer.get()
    if buffer is None:
        return
    buffer.append((model, input_tokens, output_tokens))


def _extract_usage(response) -> tuple[str, int, int] | None:
    # LangChain's LLMResult carries token counts in llm_output.
    # Shapes vary by provider, so this covers the common case and
    # returns None when counts are not present.
    llm_output = getattr(response, "llm_output", None) or {}
    usage = llm_output.get("token_usage") or {}
    model = llm_output.get("model_name") or llm_output.get("model")
    inp = usage.get("prompt_tokens")
    out = usage.get("completion_tokens")
    if model is None or inp is None or out is None:
        return None
    return (model, inp, out)


def make_callback_handler():
    """Build a LangChain callback handler that feeds the usage buffer.

    Imports LangChain only when called, so the core install stays
    dependency-free.
    """
    try:
        from langchain_core.callbacks import BaseCallbackHandler
    except ImportError as exc:
        raise ImportError(
            "LangChain is needed for the callback handler. "
            "Install it with: pip install langchain-core"
        ) from exc

    class BudgetCallbackHandler(BaseCallbackHandler):
        def on_llm_end(self, response, **kwargs) -> None:
            usage = _extract_usage(response)
            if usage is not None:
                report(*usage)

    return BudgetCallbackHandler()


class Budget:
    def __init__(self, config: BudgetConfig, ledger=None) -> None:
        self.config = config
        self.registry = BudgetRegistry(config, ledger=ledger)

    def callback_handler(self):
        return make_callback_handler()

    def track(self, func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            token = _usage_buffer.set([])
            try:
                result = await func(*args, **kwargs)
                calls = list(_usage_buffer.get())
            finally:
                _usage_buffer.reset(token)

            node = func.__name__
            total_in = total_out = 0
            total_cost = 0.0
            for model, inp, out in calls:
                total_in += inp
                total_out += out
                total_cost += cost_usd(model, inp, out, self.config.prices)

            state = await self.registry.record(
                node, total_in, total_out, total_cost
            )

            if state is BudgetState.EXCEEDED:
                if self.config.action is OverBudgetAction.BLOCK:
                    raise BudgetExceeded(node, state)
                logger.warning("budget.exceeded", node=node, cost_usd=total_cost)
            elif state is BudgetState.WARNING:
                logger.warning("budget.warning", node=node, cost_usd=total_cost)

            return result

        return wrapper