"""Playwright adapter for the dynamically rendered iDrix Contable plans."""

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

from .plans_playwright import PlaywrightPlanScraper

CONTABLE_ROOT_SELECTOR = '[id$="-content-contable"]'
PRICE_RE = re.compile(r"\$\s*[0-9][0-9.,]*")
IMPLEMENTATION_RE = re.compile(
    r"implementaci[oó]n\s+por\s+[uú]nica\s+vez\s+([0-9][0-9.,]*)",
    re.IGNORECASE,
)
USER_RE = re.compile(r"(\d+)\s+usuarios?", re.IGNORECASE)
ACCOUNTANT_RE = re.compile(r"(\d+)\s+usuario\s+contador", re.IGNORECASE)
FEATURE_KEY_RE = re.compile(r"[^a-z0-9]+")


class IdrixContablePlanScraper(PlaywrightPlanScraper):
    """Extract only cards from the dynamically generated accounting tab."""

    adapter_key = "idrixcontable_plans"
    wait_selector = f"{CONTABLE_ROOT_SELECTOR} h3"
    product = "sistema-contable"

    def _parse(self, html: str, source_url: str) -> list[ScrapedPlanDTO]:
        soup = BeautifulSoup(html, "lxml")
        root = soup.select_one(CONTABLE_ROOT_SELECTOR)
        if root is None:
            raise StructureChangedError(
                "No se encontró el panel cuyo id termina en '-content-contable'"
            )
        cards = self._cards(root)
        if not cards:
            raise SuspiciousEmptyResultError(
                "El panel del sistema contable no devolvió tarjetas de planes"
            )
        return [self._parse_card(card, source_url) for card in cards]

    def _cards(self, root: Tag) -> list[Tag]:
        grid = next(
            (
                child
                for child in root.find_all("div", recursive=False)
                if child.find("h3") is not None
            ),
            None,
        )
        if grid is None:
            return []
        return [
            child
            for child in grid.find_all("div", recursive=False)
            if child.find("h3") is not None and PRICE_RE.search(child.get_text(" ", strip=True))
        ]

    def _parse_card(self, card: Tag, source_url: str) -> ScrapedPlanDTO:
        heading = card.find("h3")
        if heading is None:
            raise StructureChangedError("Una tarjeta iDrix no contiene nombre")
        name = heading.get_text(" ", strip=True)
        price_node = next(
            (
                node
                for node in card.find_all("span")
                if PRICE_RE.fullmatch(normalize_name(node.get_text(" ", strip=True)))
            ),
            None,
        )
        if price_node is None:
            raise StructureChangedError(f"El plan {name!r} no contiene precio mensual")
        price_text = price_node.parent.get_text(" ", strip=True)
        try:
            price = parse_price(price_node.get_text(" ", strip=True))
        except ValueError as exc:
            raise NormalizationError(str(exc)) from exc
        if price is None:
            raise NormalizationError(f"El plan {name!r} no contiene un precio válido")

        description = self._description(heading)
        info_text = self._implementation_block_text(card)
        implementation_price = self._implementation_price(info_text)
        features, original_features = self._features(card, info_text)
        target_segment = self._target_segment(card)
        recommended = "recomendado" in normalize_name(card.get_text(" ", strip=True)).casefold()

        return ScrapedPlanDTO(
            external_id=self._external_id(name),
            original_name=name,
            normalized_name=normalize_name(name),
            price=price,
            currency="USD",
            periodicity=Periodicity.MONTHLY,
            price_text=price_text,
            original_features=original_features,
            normalized_features=features,
            source_url=source_url,
            raw_payload={
                "name": name,
                "product": self.product,
                "description": description,
                "target_segment": target_segment,
                "users_text": info_text,
                # TODO(schema): add a dedicated one-time implementation price to the DTO.
                "implementation_price": (
                    str(implementation_price) if implementation_price is not None else None
                ),
                "implementation_price_includes_vat": False,
                "monthly_price_includes_vat": False,
                "recommended": recommended,
            },
            product=self.product,
            monthly_price=price,
            effective_monthly_price=price,
        )

    def _description(self, heading: Tag) -> str:
        description = heading.find_next_sibling("p")
        return description.get_text(" ", strip=True) if description else ""

    def _implementation_block_text(self, card: Tag) -> str:
        for node in card.find_all("p"):
            text = node.get_text(" ", strip=True)
            if IMPLEMENTATION_RE.search(normalize_name(text)):
                parent = node.parent
                return parent.get_text(" ", strip=True) if parent else text
        return ""

    def _implementation_price(self, text: str) -> Decimal | None:
        match = IMPLEMENTATION_RE.search(text)
        if match is None:
            return None
        try:
            return parse_price(match.group(1))
        except ValueError as exc:
            raise NormalizationError(str(exc)) from exc

    def _target_segment(self, card: Tag) -> str:
        for paragraph in card.find_all("p"):
            text = paragraph.get_text(" ", strip=True)
            if normalize_name(text).casefold().startswith("empresas de"):
                return text
        return ""

    def _features(self, card: Tag, info_text: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
        normalized: dict[str, dict[str, Any]] = {}
        originals: list[str] = []
        for list_index, feature_list in enumerate(card.find_all("ul")):
            category = "Incluidas" if list_index == 0 else "Comunes"
            for item in feature_list.find_all("li", recursive=False):
                original = item.get_text(" ", strip=True)
                if not normalize_name(original) or original in originals:
                    continue
                self._add_feature(normalized, originals, original, True, category)

        users = USER_RE.search(info_text)
        accountant = ACCOUNTANT_RE.search(info_text)
        if users:
            self._add_feature(
                normalized, originals, f"Usuarios: {users.group(1)}", int(users.group(1)), "Límites"
            )
        if accountant:
            self._add_feature(
                normalized,
                originals,
                f"Usuarios contador: {accountant.group(1)}",
                int(accountant.group(1)),
                "Límites",
            )
        return normalized, originals

    def _add_feature(
        self,
        normalized: dict[str, dict[str, Any]],
        originals: list[str],
        original: str,
        value: bool | int,
        category: str,
    ) -> None:
        key = self._feature_key(original, normalized)
        feature = FeatureValue(FeatureState.OFFERED, value, original).to_dict()
        feature["category"] = category
        normalized[key] = feature
        originals.append(original)

    def _feature_key(self, value: str, existing: dict[str, Any]) -> str:
        ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        base = FEATURE_KEY_RE.sub("_", ascii_value.casefold()).strip("_") or "feature"
        key = base
        suffix = 2
        while key in existing:
            key = f"{base}_{suffix}"
            suffix += 1
        return key

    def _external_id(self, name: str) -> str:
        ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
        slug = FEATURE_KEY_RE.sub("-", ascii_name.casefold()).strip("-")
        return f"idrixcontable-{slug}"
