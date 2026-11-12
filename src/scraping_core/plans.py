import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Protocol


class Periodicity(StrEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"
    ONE_TIME = "one_time"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class FeatureState(StrEnum):
    OFFERED = "offered"
    NOT_OFFERED = "not_offered"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FeatureValue:
    state: FeatureState
    value: bool | int | float | str | None = None
    original: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PlanSourceDTO:
    id: int | None
    url: str
    timeout_seconds: int = 20
    retry_limit: int = 2
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScrapedPlanDTO:
    external_id: str | None
    original_name: str
    normalized_name: str
    price: Decimal | None
    currency: str
    periodicity: Periodicity
    price_text: str
    original_features: list[str]
    normalized_features: dict[str, dict[str, Any]]
    source_url: str
    raw_payload: dict[str, Any]
    discount_percentage: Decimal | None = None
    price_after_discount: Decimal | None = None
    monthly_price: Decimal | None = None
    annual_total_price: Decimal | None = None
    effective_monthly_price: Decimal | None = None
    is_offer_active: bool | None = None
    promotion_text: str | None = None
    product: str | None = None


class PlanScraper(Protocol):
    adapter_key: str

    def scrape(self, source: PlanSourceDTO) -> list[ScrapedPlanDTO]: ...


SPACE_RE = re.compile(r"\s+")
MONEY_RE = re.compile(r"[^0-9,.-]")


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return SPACE_RE.sub(" ", normalized).strip()


def normalize_periodicity(value: str | None) -> Periodicity:
    text = normalize_name(value or "").casefold()
    if any(token in text for token in ("mes", "month", "/mo")):
        return Periodicity.MONTHLY
    if any(token in text for token in ("año", "anual", "year", "/yr")):
        return Periodicity.YEARLY
    if any(token in text for token in ("único", "unico", "one-time", "once")):
        return Periodicity.ONE_TIME
    return Periodicity.UNKNOWN if not text else Periodicity.CUSTOM


def parse_price(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = MONEY_RE.sub("", normalize_name(value))
    if not text:
        raise ValueError(f"Precio inválido: {value!r}")
    if "," in text and "." in text:
        decimal_separator = "," if text.rfind(",") > text.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        text = text.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in text:
        tail = text.rsplit(",", 1)[-1]
        text = text.replace(",", "." if len(tail) <= 2 else "")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Precio inválido: {value!r}") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"Precio inválido: {value!r}")
    return amount.quantize(Decimal("0.01"))


def canonical_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": 2,
        "name": normalize_name(str(payload.get("name", ""))),
        "product": (normalize_name(str(payload["product"])) if payload.get("product") else None),
        "price": str(payload["price"]) if payload.get("price") is not None else None,
        "currency": str(payload.get("currency", "")).upper(),
        "periodicity": str(payload.get("periodicity", Periodicity.UNKNOWN)),
        "features": {
            key: payload.get("features", {})[key] for key in sorted(payload.get("features", {}))
        },
    }


def stable_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        canonical_payload(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "v2:" + hashlib.sha256(serialized.encode()).hexdigest()


def diff_payloads(old: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
    if old is None:
        return {"kind": "plan_added", "after": canonical_payload(new)}
    before = canonical_payload(old)
    after = canonical_payload(new)
    changes: dict[str, Any] = {}
    for field_name in ("name", "product", "price", "currency", "periodicity"):
        if before[field_name] != after[field_name]:
            changes[field_name] = {"before": before[field_name], "after": after[field_name]}
    old_features = before["features"]
    new_features = after["features"]
    feature_changes: dict[str, Any] = {}
    for key in sorted(old_features.keys() | new_features.keys()):
        if old_features.get(key) != new_features.get(key):
            feature_changes[key] = {
                "before": old_features.get(key),
                "after": new_features.get(key),
            }
    if feature_changes:
        changes["features"] = feature_changes
    return changes


def empty_result_is_failure(previous_plan_count: int, scraped_plan_count: int) -> bool:
    return previous_plan_count > 0 and scraped_plan_count == 0


def may_retire(missing_successes: int, threshold: int = 3) -> bool:
    return missing_successes >= threshold
