# agentarmour/agentbudget/breaker.py
from enum import Enum


class BudgetState(str, Enum):
    WITHIN = "within"
    WARNING = "warning"
    EXCEEDED = "exceeded"


def evaluate(
    cost_usd: float,
    limit_usd: float | None,
    warn_threshold: float,
) -> BudgetState:
    if limit_usd is None:
        return BudgetState.WITHIN
    if cost_usd >= limit_usd:
        return BudgetState.EXCEEDED
    if cost_usd >= limit_usd * warn_threshold:
        return BudgetState.WARNING
    return BudgetState.WITHIN