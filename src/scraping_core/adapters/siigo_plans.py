"""Siigo plans adapter backed by the page's Next.js data contract."""

from __future__ import annotations

import json
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from bs4 import BeautifulSoup

from scraping_core.errors import (
    NormalizationError,
    StructureChangedError,
    SuspiciousEmptyResultError,
)
from scraping_core.plans import (
    FeatureState,
    FeatureValue,
    Periodicity,
    ScrapedPlanDTO,
    normalize_name,
    normalize_periodicity,
)

from .plans_httpx import HttpxPlanScraper

FEATURE_KEY_RE = re.compile(r"[^a-z0-9]+")


class SiigoPlanScraper(HttpxPlanScraper):
    """Extract plans from ``props.pageProps.products.products`` in ``__NEXT_DATA__``."""

    adapter_key = "siigo_plans"

    included_products = ["accounting-suscripcion"]

    def _parse(self, html: str, source_url: str) -> list[ScrapedPlanDTO]:
        soup = BeautifulSoup(html, "lxml")
        node = soup.find("script", id="__NEXT_DATA__", attrs={"type": "application/json"})
        if node is None:
            raise StructureChangedError("No se encontró el script __NEXT_DATA__ de Siigo")
        serialized = node.string if node.string is not None else node.get_text()
        try:
            payload = json.loads(serialized)
        except (json.JSONDecodeError, TypeError) as exc:
            raise StructureChangedError(
                "El script __NEXT_DATA__ de Siigo no contiene JSON válido"
            ) from exc
        groups = self._product_groups(payload)
        variants = [
            self._to_dto(product, source_url)
            for products in groups.values()
            for product in self._product_list(products)
            if self._included_product(product)
        ]
        if not variants:
            raise SuspiciousEmptyResultError(
                "El JSON de Siigo no devolvió planes para los productos configurados"
            )
        return self._merge_period_variants(variants)

    def _included_product(self, product: dict[str, Any]) -> bool:
        product_name = normalize_name(self._required_text(product.get("product"), "product"))
        return product_name in self.included_products

    def _product_groups(self, payload: Any) -> dict[str, Any]:
        try:
            groups = payload["props"]["pageProps"]["products"]["products"]
        except (KeyError, TypeError) as exc:
            raise StructureChangedError(
                "No existe props.pageProps.products.products en __NEXT_DATA__"
            ) from exc
        if not isinstance(groups, dict):
            raise StructureChangedError("products.products debe ser un objeto de grupos")
        return groups

    def _product_list(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise StructureChangedError(
                "Cada grupo de productos Siigo debe ser una lista de objetos"
            )
        return value

    def _to_dto(self, product: dict[str, Any], source_url: str) -> ScrapedPlanDTO:
        external_key = normalize_name(self._required_text(product.get("key"), "key"))
        product_name = self._required_text(product.get("product"), "product")
        name = self._required_text(
            product.get("title") or product.get("subProduct") or product.get("name"),
            "title",
        )
        period = product.get("period")
        periodicity = self._periodicity(period, product.get("pricingInfo"))
        prices = self._mapping(product.get("prices"), "prices")
        pricing_info = self._mapping(product.get("pricingInfo"), "pricingInfo")
        discounted = self._money(
            self._first_present(
                prices, "descountedPrice", fallback=pricing_info.get("billedPrice")
            ),
            "prices.descountedPrice",
        )
        discount = self._percentage(prices.get("descount", 0), "prices.descount")
        currency = self._required_text(pricing_info.get("currency"), "pricingInfo.currency")
        features, original_features = self._features(product.get("features", []))
        monthly_price = discounted if periodicity == Periodicity.MONTHLY else None
        annual_total = discounted if periodicity == Periodicity.YEARLY else None
        effective_monthly = monthly_price
        if annual_total is not None:
            effective_monthly = (annual_total / Decimal(12)).quantize(Decimal("0.01"))
        promotion_text = self._promotion_text(product, pricing_info)
        return ScrapedPlanDTO(
            external_id=external_key,
            original_name=name,
            normalized_name=normalize_name(name),
            price=discounted,
            currency=currency,
            periodicity=periodicity,
            price_text=self._price_text(product, pricing_info, discounted, currency),
            original_features=original_features,
            normalized_features=features,
            source_url=source_url,
            raw_payload=dict(product),
            product=product_name,
            discount_percentage=discount,
            price_after_discount=discounted,
            monthly_price=monthly_price,
            annual_total_price=annual_total,
            effective_monthly_price=effective_monthly,
            is_offer_active=self._optional_bool(product.get("isCampaignActive")),
            promotion_text=promotion_text,
        )

    def _merge_period_variants(self, variants: list[ScrapedPlanDTO]) -> list[ScrapedPlanDTO]:
        grouped: dict[str, list[ScrapedPlanDTO]] = {}
        for variant in variants:
            if variant.external_id is None:
                raise StructureChangedError("Una variante Siigo no contiene clave estable")
            grouped.setdefault(variant.external_id, []).append(variant)
        return [self._merge_plan_variants(key, items) for key, items in grouped.items()]

    def _merge_plan_variants(
        self, external_key: str, variants: list[ScrapedPlanDTO]
    ) -> ScrapedPlanDTO:
        if len(variants) == 1:
            return variants[0]
        by_period = {variant.periodicity: variant for variant in variants}
        if len(by_period) != len(variants):
            raise StructureChangedError(
                f"Siigo devolvió periodicidades duplicadas para el plan {external_key}"
            )
        if set(by_period) != {Periodicity.MONTHLY, Periodicity.YEARLY}:
            raise StructureChangedError(
                f"Siigo devolvió variantes incompatibles para el plan {external_key}"
            )
        monthly = by_period[Periodicity.MONTHLY]
        annual = by_period[Periodicity.YEARLY]
        comparable_fields = (
            "original_name",
            "normalized_name",
            "currency",
            "original_features",
            "normalized_features",
            "source_url",
            "product",
        )
        for field in comparable_fields:
            if getattr(monthly, field) != getattr(annual, field):
                raise StructureChangedError(
                    f"Las variantes mensual/anual de {external_key} difieren en {field}"
                )
        promotion_parts = [
            f"{label}: {variant.promotion_text}"
            for label, variant in (("Mensual", monthly), ("Anual", annual))
            if variant.promotion_text
        ]
        offer_values = (monthly.is_offer_active, annual.is_offer_active)
        offer_active = (
            True
            if True in offer_values
            else False
            if all(value is False for value in offer_values)
            else None
        )
        return ScrapedPlanDTO(
            external_id=external_key,
            original_name=monthly.original_name,
            normalized_name=monthly.normalized_name,
            price=annual.price,
            currency=monthly.currency,
            periodicity=Periodicity.CUSTOM,
            price_text=f"{monthly.price_text} / mes · {annual.price_text} / año",
            original_features=monthly.original_features,
            normalized_features=monthly.normalized_features,
            source_url=monthly.source_url,
            raw_payload={
                "monthly": monthly.raw_payload,
                "annual": annual.raw_payload,
            },
            product=monthly.product,
            discount_percentage=annual.discount_percentage,
            price_after_discount=annual.price_after_discount,
            monthly_price=monthly.monthly_price,
            annual_total_price=annual.annual_total_price,
            effective_monthly_price=annual.effective_monthly_price,
            is_offer_active=offer_active,
            promotion_text=" · ".join(promotion_parts) or None,
        )

    def _features(self, value: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
        if not isinstance(value, list):
            raise StructureChangedError("features debe ser una lista")
        normalized: dict[str, dict[str, Any]] = {}
        original: list[str] = []
        for index, feature in enumerate(value):
            if not isinstance(feature, dict):
                raise StructureChangedError("Cada característica Siigo debe ser un objeto")
            name = self._required_text(feature.get("name"), "features.name")
            active = self._optional_bool(feature.get("active"))
            if active is None:
                raise StructureChangedError("features.active debe ser booleano")
            key = self._unique_feature_key(name, normalized, index)
            item = FeatureValue(
                FeatureState.OFFERED if active else FeatureState.NOT_OFFERED,
                active,
                name,
            ).to_dict()
            item["tooltip"] = str(feature.get("tooltip", ""))
            item["show"] = self._optional_bool(feature.get("show"))
            item["is_additional_feature"] = self._optional_bool(feature.get("isAdditionalFeature"))
            normalized[key] = item
            original.append(name)
        return normalized, original

    def _unique_feature_key(
        self, name: str, existing: dict[str, dict[str, Any]], index: int
    ) -> str:
        ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
        base = FEATURE_KEY_RE.sub("_", ascii_name.casefold()).strip("_") or f"feature_{index + 1}"
        key = base
        suffix = 2
        while key in existing:
            key = f"{base}_{suffix}"
            suffix += 1
        return key

    def _periodicity(self, period: Any, pricing_info: Any) -> Periodicity:
        if period == 1:
            return Periodicity.MONTHLY
        if period == 12:
            return Periodicity.YEARLY
        info = self._mapping(pricing_info, "pricingInfo")
        return normalize_periodicity(str(info.get("cycleLabel", "")))

    def _money(self, value: Any, field: str) -> Decimal:
        if value is None or isinstance(value, bool):
            raise NormalizationError(f"{field} ausente o inválido")
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise NormalizationError(f"{field} inválido") from exc
        if not amount.is_finite() or amount < 0:
            raise NormalizationError(f"{field} inválido")
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _percentage(self, value: Any, field: str) -> Decimal:
        amount = self._money(value, field)
        if amount > 100:
            raise NormalizationError(f"{field} debe estar entre 0 y 100")
        return amount

    def _mapping(self, value: Any, field: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise StructureChangedError(f"{field} debe ser un objeto")
        return value

    def _required_text(self, value: Any, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise StructureChangedError(f"{field} debe ser una cadena no vacía")
        return value

    def _optional_bool(self, value: Any) -> bool | None:
        return value if isinstance(value, bool) else None

    def _first_present(self, values: dict[str, Any], key: str, *, fallback: Any) -> Any:
        return values[key] if key in values and values[key] is not None else fallback

    def _promotion_text(self, product: dict[str, Any], pricing_info: dict[str, Any]) -> str | None:
        parts = []
        for value in (pricing_info.get("discountInfo"), product.get("infoText")):
            if isinstance(value, str) and value.strip():
                parts.append(value)
        return " · ".join(parts) or None

    def _price_text(
        self,
        product: dict[str, Any],
        pricing_info: dict[str, Any],
        discounted: Decimal,
        currency: str,
    ) -> str:
        if product.get("isFree") is True:
            return str(pricing_info.get("price") or "Gratis")
        return f"{currency} {discounted}"
