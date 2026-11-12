from decimal import Decimal
from typing import Any

from scraping_core.errors import (
    ScrapeTimeoutError,
    StructureChangedError,
    SuspiciousEmptyResultError,
)
from scraping_core.plans import (
    Periodicity,
    PlanSourceDTO,
    ScrapedPlanDTO,
    normalize_name,
)


def _decimal(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


class FixturePlanScraper:
    adapter_key = "fixture_plans"

    def scrape(self, source: PlanSourceDTO) -> list[ScrapedPlanDTO]:
        error = source.config.get("simulate_error")
        if error == "timeout":
            raise ScrapeTimeoutError("Timeout fixture solicitado")
        if error == "structure":
            raise StructureChangedError("Estructura fixture inválida")
        rows = source.config.get("fixture_plans")
        if not isinstance(rows, list):
            raise StructureChangedError("fixture_plans debe ser una lista")
        if not rows and not source.config.get("allow_empty", False):
            raise SuspiciousEmptyResultError("La fuente fixture devolvió cero planes")
        return [self._item(source, row) for row in rows]

    def _item(self, source: PlanSourceDTO, row: Any) -> ScrapedPlanDTO:
        if not isinstance(row, dict) or not row.get("name"):
            raise StructureChangedError("Cada plan fixture requiere name")
        name = str(row["name"])
        product = row.get("product")
        if product is not None and (not isinstance(product, str) or not product.strip()):
            raise StructureChangedError("product debe ser una cadena no vacía o null")
        features = row.get("features", {})
        if not isinstance(features, dict):
            raise StructureChangedError("features debe ser un objeto")
        try:
            periodicity = Periodicity(row.get("periodicity", Periodicity.UNKNOWN))
        except ValueError as exc:
            raise StructureChangedError("periodicity fixture inválida") from exc
        return ScrapedPlanDTO(
            external_id=row.get("external_id"),
            original_name=name,
            normalized_name=normalize_name(name),
            price=_decimal(row.get("price")),
            currency=str(row.get("currency", "USD")),
            periodicity=periodicity,
            price_text=str(row.get("price_text", row.get("price", ""))),
            original_features=[
                str(value.get("original", key)) if isinstance(value, dict) else str(key)
                for key, value in features.items()
            ],
            normalized_features=features,
            source_url=source.url,
            raw_payload=dict(row),
            product=product,
            discount_percentage=_decimal(row.get("discount_percentage")),
            price_after_discount=_decimal(row.get("price_after_discount")),
            monthly_price=_decimal(row.get("monthly_price")),
            annual_total_price=_decimal(row.get("annual_total_price")),
            effective_monthly_price=_decimal(row.get("effective_monthly_price")),
            is_offer_active=row.get("is_offer_active"),
            promotion_text=row.get("promotion_text"),
        )
