from scraping_core.adapters.fixture_plans import FixturePlanScraper
from scraping_core.plans import PlanSourceDTO


def test_fixture_plan_preserves_source_values_and_keeps_canonical_name_separate():
    row = {
        "name": "  Plan   Pró  ",
        "product": " Accounting-Suscripción ",
        "currency": "usd ",
        "price": "10.00",
        "periodicity": "monthly",
        "features": {},
    }
    plan = FixturePlanScraper().scrape(
        PlanSourceDTO(
            id=None,
            url="https://fixture.invalid/plans",
            config={"fixture_plans": [row]},
        )
    )[0]

    assert plan.original_name == row["name"]
    assert plan.normalized_name == "Plan Pró"
    assert plan.product == row["product"]
    assert plan.currency == row["currency"]
    assert plan.raw_payload == row
