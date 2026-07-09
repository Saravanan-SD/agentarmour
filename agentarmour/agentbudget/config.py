# agentarmour/agentbudget/config.py
from enum import Enum
from pydantic import BaseModel, Field


class OverBudgetAction(str, Enum):
    WARN = "warn"
    BLOCK = "block"


class ModelPrice(BaseModel):
    input_per_million: float
    output_per_million: float


class BudgetConfig(BaseModel):
    prices: dict[str, ModelPrice] = Field(default_factory=dict)
    node_limit_usd: float | None = None
    run_limit_usd: float | None = None
    global_limit_usd: float | None = None
    warn_threshold: float = 0.8
    action: OverBudgetAction = OverBudgetAction.WARN