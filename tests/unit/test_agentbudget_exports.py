# tests/unit/test_agentbudget_exports.py
import agentarmour.agentbudget as ab


def test_public_names_importable():
    for name in ab.__all__:
        assert hasattr(ab, name), f"{name} in __all__ but not importable"


def test_top_level_import_works():
    from agentarmour.agentbudget import Budget, BudgetConfig, report

    budget = Budget(BudgetConfig())
    assert budget.registry is not None
    assert callable(report)


def test_internals_not_exported():
    # these stay private, reachable only through submodules
    for name in ("BudgetRegistry", "UsageRecord", "BudgetEvent", "evaluate"):
        assert name not in ab.__all__