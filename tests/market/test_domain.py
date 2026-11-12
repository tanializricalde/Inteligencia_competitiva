from decimal import Decimal

import pytest

from apps.market.domain.normalization import (
    FeatureState,
    FeatureValue,
    Periodicity,
    diff_payloads,
    empty_result_is_failure,
    may_retire,
    normalize_periodicity,
    parse_price,
    stable_hash,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("S/ 1.299,90", Decimal("1299.90")), ("$1,299.90", Decimal("1299.90")), (None, None)],
)
def test_parse_price(raw, expected):
    assert parse_price(raw) == expected


def test_price_rejects_invalid_value():
    with pytest.raises(ValueError):
        parse_price("gratis?")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("por mes", Periodicity.MONTHLY), ("Anual", Periodicity.YEARLY), ("", Periodicity.UNKNOWN)],
)
def test_periodicity(raw, expected):
    assert normalize_periodicity(raw) == expected


def test_hash_is_stable_and_ignores_volatile_fields():
    first = {"name": " Pro ", "price": Decimal("10.00"), "features": {"b": 2, "a": 1}, "at": 1}
    second = {"name": "Pro", "price": Decimal("10.00"), "features": {"a": 1, "b": 2}, "at": 2}

    assert stable_hash(first) == stable_hash(second)


def test_diff_reports_price_and_feature_changes():
    old = {"name": "Pro", "price": Decimal("10"), "features": {"support": {"state": "unknown"}}}
    new = {
        "name": "Pro",
        "price": Decimal("12"),
        "features": {"support": {"state": "offered", "value": True}},
    }

    diff = diff_payloads(old, new)

    assert diff["price"] == {"before": "10", "after": "12"}
    assert "support" in diff["features"]


def test_feature_unknown_is_distinct_from_not_offered():
    unknown = FeatureValue(FeatureState.UNKNOWN)
    not_offered = FeatureValue(FeatureState.NOT_OFFERED, False)

    assert unknown.to_dict() != not_offered.to_dict()


def test_empty_and_retirement_policies_are_conservative():
    assert empty_result_is_failure(previous_plan_count=2, scraped_plan_count=0)
    assert not may_retire(2)
    assert may_retire(3)
