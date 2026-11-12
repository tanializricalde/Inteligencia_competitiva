"""Adapters for the legacy Anfibius and Perseo pricing pages."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Any

from bs4 import BeautifulSoup, Tag

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
    parse_price,
)

from .plans_httpx import HttpxPlanScraper

CARD_SELECTOR = ", ".join(
    (
        "[data-pricing-plan]",
        ".elementor-price-table",
        ".et_pb_pricing_table",
        '.et_pb_section[id^="planes_"] .et_pb_column',
        ".pricing-table",
        ".price-table",
    )
)
HEADING_SELECTOR = ", ".join(
    (
        "[data-plan-name]",
        ".elementor-price-table__heading",
        ".et_pb_pricing_title",
        ".pricing-title",
        "h1",
        "h2",
        "h3",
        "h4",
    )
)
MONEY = r"\$\s*([0-9][0-9.,]*)"
MONTHLY_PATTERNS = (
    re.compile(rf"plan\s+mensual.{{0,100}}?{MONEY}", re.IGNORECASE),
    re.compile(rf"{MONEY}\s*(?:/|por\s+)?\s*mes\b", re.IGNORECASE),
)
ANNUAL_PATTERNS = (
    re.compile(rf"plan\s+anual.{{0,100}}?{MONEY}", re.IGNORECASE),
    re.compile(rf"{MONEY}\s*(?:/|por\s+)?\s*(?:año|anual)\b", re.IGNORECASE),
    re.compile(rf"réntalo\s+.{{0,40}}?{MONEY}\s*/?\s*año", re.IGNORECASE),
    re.compile(rf"réntalo\s+(?:a\s+tan\s+solo\s+)?{MONEY}(?:\s*\+\s*iva)?", re.IGNORECASE),
)
ONE_TIME_PATTERNS = (
    re.compile(rf"(?:cómpralo|compralo|pago\s+único).{{0,60}}?{MONEY}", re.IGNORECASE),
)
FEATURE_NOISE = re.compile(
    r"\$|\b(?:usd|comprar|cotiz|elegir|contratar|empezar|suscrib|ver módulos)\b",
    re.IGNORECASE,
)
FEATURE_KEY_RE = re.compile(r"[^a-z0-9]+")


class LegacyPricingParser:
    """Parse narrowly identified pricing cards without the legacy broad-container duplicates."""

    adapter_key: str
    external_prefix: str
    default_product: str

    def _parse(self, html: str, source_url: str) -> list[ScrapedPlanDTO]:
        soup = BeautifulSoup(html, "lxml")
        cards = self._cards(soup)
        if not cards:
            raise StructureChangedError("No se encontraron tarjetas de precios compatibles")
        plans = [self._parse_card(card, source_url) for card in cards]
        if not plans:
            raise SuspiciousEmptyResultError("La fuente devolvió cero planes")
        return plans

    def _cards(self, soup: BeautifulSoup) -> list[Tag]:
        candidates = [node for node in soup.select(CARD_SELECTOR) if isinstance(node, Tag)]
        candidate_ids = {id(node) for node in candidates}
        cards = [
            node
            for node in candidates
            if not any(id(child) in candidate_ids for child in node.select(CARD_SELECTOR))
        ]
        return [card for card in cards if self._looks_like_plan(card)]

    def _looks_like_plan(self, card: Tag) -> bool:
        text = normalize_name(card.get_text(" ", strip=True))
        return card.select_one(HEADING_SELECTOR) is not None and bool(
            re.search(r"\$|\bgratis\b", text, re.IGNORECASE)
        )

    def _parse_card(self, card: Tag, source_url: str) -> ScrapedPlanDTO:
        heading = card.select_one(HEADING_SELECTOR)
        if heading is None:
            raise StructureChangedError("Una tarjeta de precios no contiene nombre")
        name = heading.get_text(" ", strip=True)
        if len(normalize_name(name)) < 2:
            raise StructureChangedError("Una tarjeta contiene un nombre de plan inválido")
        text = normalize_name(card.get_text(" ", strip=True))
        monthly = self._price(text, MONTHLY_PATTERNS)
        annual = self._price(text, ANNUAL_PATTERNS)
        one_time = self._price(text, ONE_TIME_PATTERNS)
        free = bool(re.search(r"\bgratis\b", text, re.IGNORECASE))
        if monthly is None and annual is None and one_time is None and not free:
            raise NormalizationError(f"No se encontró un precio válido para el plan {name!r}")
        price, periodicity = self._canonical_price(monthly, annual, one_time, free)
        product = self._product(card, text)
        features, originals = self._features(card, name)
        external_id = card.get("data-plan-id") or self._external_id(product, name)
        effective_monthly = monthly
        if effective_monthly is None and annual is not None:
            effective_monthly = (annual / Decimal(12)).quantize(Decimal("0.01"))
        return ScrapedPlanDTO(
            external_id=str(external_id),
            original_name=name,
            normalized_name=normalize_name(name),
            price=price,
            currency="USD",
            periodicity=periodicity,
            price_text=self._price_text(monthly, annual, one_time, free),
            original_features=originals,
            normalized_features=features,
            source_url=source_url,
            raw_payload={
                "name": name,
                "product": product,
                "monthly_price": str(monthly) if monthly is not None else None,
                "annual_total_price": str(annual) if annual is not None else None,
                # TODO(schema): expose a dedicated one-time price in ScrapedPlanDTO/CLI.
                "one_time_price": str(one_time) if one_time is not None else None,
            },
            product=product,
            monthly_price=monthly,
            annual_total_price=annual,
            effective_monthly_price=effective_monthly,
        )

    def _price(self, text: str, patterns: tuple[re.Pattern[str], ...]) -> Decimal | None:
        for pattern in patterns:
            if match := pattern.search(text):
                try:
                    return parse_price(match.group(1))
                except ValueError as exc:
                    raise NormalizationError(str(exc)) from exc
        return None

    def _canonical_price(
        self,
        monthly: Decimal | None,
        annual: Decimal | None,
        one_time: Decimal | None,
        free: bool,
    ) -> tuple[Decimal, Periodicity]:
        if monthly is not None:
            return monthly, Periodicity.MONTHLY
        if annual is not None:
            return annual, Periodicity.YEARLY
        if one_time is not None:
            return one_time, Periodicity.ONE_TIME
        if free:
            return Decimal("0.00"), Periodicity.CUSTOM
        raise AssertionError("unreachable")

    def _product(self, card: Tag, text: str) -> str:
        explicit = card.get("data-product")
        return str(explicit) if explicit else self._infer_product(text)

    def _infer_product(self, text: str) -> str:
        return self.default_product

    def _features(self, card: Tag, plan_name: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
        candidates = self._feature_candidates(card)
        return self._normalize_features(candidates, plan_name)

    def _feature_candidates(self, card: Tag) -> list[str]:
        candidates = [node.get_text(" ", strip=True) for node in card.select("li")]
        if candidates:
            return candidates
        blocks = card.select(".et_pb_text_inner")
        for index, block in enumerate(blocks[:-1]):
            marker = normalize_name(block.get_text(" ", strip=True)).casefold().rstrip(":")
            if marker in {"incluye", "incluye sin costo"}:
                return list(blocks[index + 1].stripped_strings)
        return [
            node.get_text(" ", strip=True) for node in card.select("[data-feature], .plan-feature")
        ]

    def _normalize_features(
        self, candidates: list[str], plan_name: str
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        normalized: dict[str, dict[str, Any]] = {}
        originals: list[str] = []
        seen: set[str] = set()
        for index, candidate in enumerate(candidates):
            original = candidate
            folded = normalize_name(original).casefold()
            if (
                len(normalize_name(original)) < 3
                or folded == normalize_name(plan_name).casefold()
                or folded in seen
                or FEATURE_NOISE.search(original)
            ):
                continue
            seen.add(folded)
            key = self._feature_key(original, normalized, index)
            value: bool | int = True
            users = re.search(r"(\d+)\s*(?:usuario|usuarios|licencia|licencias)", original, re.I)
            users = users or re.search(
                r"(?:usuario|usuarios|licencia|licencias)\s*\(?(\d+)", original, re.I
            )
            if users:
                value = int(users.group(1))
            normalized[key] = FeatureValue(FeatureState.OFFERED, value, original).to_dict()
            originals.append(original)
        return normalized, originals

    def _feature_key(self, name: str, existing: dict[str, dict[str, Any]], index: int) -> str:
        ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
        base = FEATURE_KEY_RE.sub("_", ascii_name.casefold()).strip("_") or f"feature_{index + 1}"
        key = base
        suffix = 2
        while key in existing:
            key = f"{base}_{suffix}"
            suffix += 1
        return key

    def _external_id(self, product: str, name: str) -> str:
        value = f"{self.external_prefix}-{product}-{name}"
        ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        return FEATURE_KEY_RE.sub("-", ascii_value.casefold()).strip("-")

    def _price_text(
        self,
        monthly: Decimal | None,
        annual: Decimal | None,
        one_time: Decimal | None,
        free: bool,
    ) -> str:
        parts = []
        if monthly is not None:
            parts.append(f"${monthly} /MES")
        if annual is not None:
            parts.append(f"${annual} /AÑO")
        if one_time is not None:
            parts.append(f"${one_time} PAGO ÚNICO")
        return "; ".join(parts) or ("GRATIS" if free else "")


class AnfibiusPlanScraper(LegacyPricingParser, HttpxPlanScraper):
    adapter_key = "anfibius_plans"
    external_prefix = "anfibius"
    default_product = "facturacion-electronica"

    def _parse(self, html: str, source_url: str) -> list[ScrapedPlanDTO]:
        soup = BeautifulSoup(html, "lxml")
        plans = self._article_plans(soup, source_url)
        return plans or super()._parse(html, source_url)

    def _article_plans(self, soup: BeautifulSoup, source_url: str) -> list[ScrapedPlanDTO]:
        section = next(
            (
                heading
                for heading in soup.find_all("h2")
                if "incluye cada plan"
                in normalize_name(heading.get_text(" ", strip=True)).casefold()
            ),
            None,
        )
        if section is None:
            return []

        plans: list[ScrapedPlanDTO] = []
        node = section.find_next_sibling()
        while node is not None and node.name != "h2":
            if node.name == "h3":
                name = node.get_text(" ", strip=True)
                description_node = node.find_next_sibling()
                description = (
                    description_node.get_text(" ", strip=True)
                    if description_node is not None and description_node.name == "p"
                    else ""
                )
                features, originals = self._normalize_features(
                    self._article_features(description), name
                )
                plans.append(
                    ScrapedPlanDTO(
                        external_id=self._external_id(self.default_product, name),
                        original_name=name,
                        normalized_name=normalize_name(name),
                        price=None,
                        currency="USD",
                        periodicity=Periodicity.UNKNOWN,
                        price_text="",
                        original_features=originals,
                        normalized_features=features,
                        source_url=source_url,
                        raw_payload={"name": name, "description": description},
                        product=self.default_product,
                    )
                )
            node = node.find_next_sibling()
        return plans

    def _article_features(self, description: str) -> list[str]:
        groups = re.findall(
            r"(?:incluye|incorpora|suma)\s+(.+?)(?:\.|$)",
            description,
            re.IGNORECASE,
        )
        features: list[str] = []
        for group in groups:
            features.extend(re.split(r",\s*|\s+y\s+(?=[^,]+$)", group))
        return [feature for feature in features if normalize_name(feature)]


class PerseoPlanScraper(LegacyPricingParser, HttpxPlanScraper):
    adapter_key = "perseo_plans"
    external_prefix = "perseo"
    default_product = "perseo-web"

    def _infer_product(self, text: str) -> str:
        folded = text.casefold()
        if re.search(r"\bnivel\s+\d+\b|\bram\b|\bssd\b|características del servidor", folded):
            return "perseo-prime"
        if "opción 1" in folded or "licencia en el servidor" in folded or "perseohybrid" in folded:
            return "perseo-pc"
        return self.default_product
