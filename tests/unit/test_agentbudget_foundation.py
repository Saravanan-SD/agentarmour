# tests/agentbudget/test_foundation.py
import pytest

from agentarmour.agentbudget.config import (
    BudgetConfig,
    ModelPrice,
    OverBudgetAction,
)
from agentarmour.agentbudget.pricing import (
    cost_usd,
    price_for,
    UnknownModelError,
)
from agentarmour.agentbudget.usage import UsageRecord
from agentarmour.agentbudget.breaker import BudgetState, evaluate


# ---------- config.py ----------

def test_config_defaults():
    cfg = BudgetConfig()
    assert cfg.prices == {}
    assert cfg.node_limit_usd is None
    assert cfg.run_limit_usd is None
    assert cfg.global_limit_usd is None
    assert cfg.warn_threshold == 0.8
    assert cfg.action is OverBudgetAction.WARN


def test_config_with_prices():
    cfg = BudgetConfig(
        prices={"my-model": ModelPrice(input_per_million=3.0, output_per_million=15.0)},
        run_limit_usd=5.0,
    )
    assert cfg.run_limit_usd == 5.0
    assert cfg.prices["my-model"].output_per_million == 15.0


def test_action_serializes_as_string():
    # str, Enum means it saves as plain text in the ledger
    assert OverBudgetAction.WARN == "warn"
    assert OverBudgetAction.BLOCK.value == "block"


def test_default_factory_does_not_share():
    # two configs must not share the same dict
    a = BudgetConfig()
    b = BudgetConfig()
    a.prices["x"] = ModelPrice(input_per_million=1.0, output_per_million=2.0)
    assert b.prices == {}


# ---------- pricing.py ----------

PRICES = {"m": ModelPrice(input_per_million=3.0, output_per_million=15.0)}


def test_cost_math():
    # 1000 input -> 0.003, 500 output -> 0.0075, total 0.0105
    result = cost_usd("m", 1000, 500, PRICES)
    assert result == pytest.approx(0.0105)


def test_cost_zero_tokens():
    assert cost_usd("m", 0, 0, PRICES) == 0.0


def test_unknown_model_raises():
    with pytest.raises(UnknownModelError):
        cost_usd("missing", 100, 100, PRICES)


def test_price_for_returns_model_price():
    assert price_for("m", PRICES).input_per_million == 3.0


# ---------- usage.py ----------

def test_usage_starts_empty():
    u = UsageRecord()
    assert u.input_tokens == 0
    assert u.cost_usd == 0.0
    assert u.calls == 0


def test_usage_accumulates():
    u = UsageRecord()
    u.add(input_tokens=100, output_tokens=50, cost_usd=0.01)
    u.add(input_tokens=200, output_tokens=25, cost_usd=0.02)
    assert u.input_tokens == 300
    assert u.output_tokens == 75
    assert u.cost_usd == pytest.approx(0.03)
    assert u.calls == 2


# ---------- breaker.py ----------

def test_no_limit_is_always_within():
    assert evaluate(cost_usd=999.0, limit_usd=None, warn_threshold=0.8) == BudgetState.WITHIN


def test_within_below_threshold():
    assert evaluate(cost_usd=5.0, limit_usd=10.0, warn_threshold=0.8) == BudgetState.WITHIN


def test_warning_at_threshold():
    assert evaluate(cost_usd=8.0, limit_usd=10.0, warn_threshold=0.8) == BudgetState.WARNING


def test_exceeded_at_limit():
    assert evaluate(cost_usd=10.0, limit_usd=10.0, warn_threshold=0.8) == BudgetState.EXCEEDED


def test_exceeded_above_limit():
    assert evaluate(cost_usd=12.0, limit_usd=10.0, warn_threshold=0.8) == BudgetState.EXCEEDED