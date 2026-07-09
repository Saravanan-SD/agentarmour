# seed_demo.py
import asyncio

from agentarmour.agentbudget import (
    Budget,
    BudgetConfig,
    ModelPrice,
    SQLiteBudgetLedger,
    report,
    run_context,
)

PRICES = {"demo-model": ModelPrice(input_per_million=3.0, output_per_million=15.0)}


async def main() -> None:
    ledger = SQLiteBudgetLedger(db_path="agentarmour.db")
    budget = Budget(BudgetConfig(prices=PRICES, run_limit_usd=0.05), ledger=ledger)

    @budget.track
    async def cheap_node():
        report("demo-model", 500, 100)

    @budget.track
    async def pricey_node():
        report("demo-model", 5000, 2000)

    # two runs, so the dashboard has more than one run_id
    for _ in range(2):
        with run_context():
            await cheap_node()
            await pricey_node()
            await pricey_node()


if __name__ == "__main__":
    asyncio.run(main())