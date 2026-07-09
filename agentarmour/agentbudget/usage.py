# agentarmour/agentbudget/usage.py
from pydantic import BaseModel


class UsageRecord(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0

    def add(self, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd += cost_usd
        self.calls += 1

class BudgetEvent(BaseModel):
    node: str
    run_id: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    state: str
    timestamp: float