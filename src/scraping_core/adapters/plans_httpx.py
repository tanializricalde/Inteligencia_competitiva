from decimal import Decimal
from typing import Any

import httpx
from bs4 import BeautifulSoup

from scraping_core.errors import (
    AccessBlockedError,
    HttpResponseError,
    NormalizationError,
    ResponseTooLargeError,
    ScrapeTimeoutError,
    StructureChangedError,
    SuspiciousEmptyResultError,
    TransportError,
)
from scraping_core.plans import (
    FeatureState,
    FeatureValue,
    PlanSourceDTO,
    ScrapedPlanDTO,
    normalize_name,
    normalize_periodicity,
    parse_price,
)
from scraping_core.security import validate_source_url


class HttpxPlanScraper:
    adapter_key = "example_httpx"
    transient_statuses = {408, 425, 429, 500, 502, 503, 504}

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        user_agent: str = "MarketMonitorCLI/1.0",
        max_response_bytes: int = 5_000_000,
        allow_private_hosts: bool = False,
    ):
        self._owns_client = client is None
        self.client = client or httpx.Client(
            headers={"User-Agent": user_agent},
            follow_redirects=False,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        )
        self.max_response_bytes = max_response_bytes
        self.allow_private_hosts = allow_private_hosts

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def scrape(self, source: PlanSourceDTO) -> list[ScrapedPlanDTO]:
        validate_source_url(
            source.url,
            allow_private_hosts=self.allow_private_hosts,
            resolve_host=self._owns_client,
        )
        try:
            response = self._fetch(source)
            return self._parse(response.text, source.url)
        finally:
            self.close()

    def _fetch(self, source: PlanSourceDTO) -> httpx.Response:
        attempts = source.retry_limit + 1
        for attempt in range(attempts):
            try:
                response = self.client.get(source.url, timeout=source.timeout_seconds)
            except httpx.TimeoutException as exc:
                if attempt + 1 == attempts:
                    raise ScrapeTimeoutError("La descarga excedió el timeout") from exc
                continue
            except httpx.TransportError as exc:
                if attempt + 1 == attempts:
                    raise TransportError("No fue posible conectar con la fuente") from exc
                continue
            if response.is_redirect:
                raise HttpResponseError("Las redirecciones HTTP no están permitidas")
            if response.status_code in {401, 403}:
                raise AccessBlockedError(f"Acceso rechazado (HTTP {response.status_code})")
            if response.status_code in self.transient_statuses and attempt + 1 < attempts:
                continue
            if response.is_error:
                raise HttpResponseError(f"Respuesta HTTP {response.status_code}")
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type:
                raise HttpResponseError("La respuesta no es HTML")
            if len(response.content) > self.max_response_bytes:
                raise ResponseTooLargeError("La respuesta excede el tamaño permitido")
            return response
        raise TransportError("No fue posible descargar la fuente")

    def _parse(self, html: str, source_url: str) -> list[ScrapedPlanDTO]:
        soup = BeautifulSoup(html, "lxml")
        root = soup.select_one("[data-plans-root]")
        if root is None:
            raise StructureChangedError("No se encontró el contenedor obligatorio de planes")
        cards = root.select(".plan-card")
        if not cards:
            raise SuspiciousEmptyResultError("La fuente devolvió cero planes")
        return [self._parse_card(card, source_url) for card in cards]

    def _optional_price(self, card: Any, attribute: str) -> Decimal | None:
        value = card.get(attribute)
        if value in (None, ""):
            return None
        try:
            return parse_price(str(value))
        except ValueError as exc:
            raise NormalizationError(str(exc)) from exc

    def _parse_card(self, card: Any, source_url: str) -> ScrapedPlanDTO:
        name_node = card.select_one(".plan-name")
        price_node = card.select_one(".plan-price")
        if name_node is None or price_node is None:
            raise StructureChangedError("Un plan no contiene nombre o precio")
        name = name_node.get_text(" ", strip=True)
        price_text = price_node.get_text(" ", strip=True)
        try:
            price = parse_price(price_text)
        except ValueError as exc:
            raise NormalizationError(str(exc)) from exc
        periodicity_node = card.select_one(".plan-periodicity")
        periodicity = normalize_periodicity(
            periodicity_node.get_text(" ", strip=True) if periodicity_node else ""
        )
        original_features: list[str] = []
        normalized_features: dict[str, dict[str, Any]] = {}
        for feature in card.select(".plan-feature"):
            original = feature.get_text(" ", strip=True)
            key = feature.get("data-key")
            if not key:
                raise StructureChangedError("Una característica no tiene data-key")
            state = FeatureState(feature.get("data-state", FeatureState.OFFERED))
            value: bool | str = feature.get("data-value", True)
            original_features.append(original)
            normalized = FeatureValue(state, value, original).to_dict()
            if category := feature.get("data-category"):
                normalized["category"] = str(category)
            if additional_cost := feature.get("data-additional-cost"):
                normalized["additional_cost"] = str(parse_price(str(additional_cost)))
            normalized_features[str(key)] = normalized
        promotion_node = card.select_one(".plan-promotion")
        offer_attribute = card.get("data-offer-active")
        is_offer_active = None
        if offer_attribute is not None:
            is_offer_active = str(offer_attribute).casefold() in {"1", "true", "yes", "si", "sí"}
        discount_percentage = self._optional_price(card, "data-discount-pct")
        price_after_discount = self._optional_price(card, "data-discounted-price")
        monthly_price = self._optional_price(card, "data-monthly-price")
        annual_total = self._optional_price(card, "data-annual-total")
        effective_monthly = self._optional_price(card, "data-effective-monthly")
        if monthly_price is None and periodicity.value == "monthly":
            monthly_price = price
        if annual_total is None and periodicity.value == "yearly":
            annual_total = price
        if effective_monthly is None:
            effective_monthly = price_after_discount
        return ScrapedPlanDTO(
            external_id=card.get("data-plan-id"),
            original_name=name,
            normalized_name=normalize_name(name),
            price=price,
            currency=str(price_node.get("data-currency", "PEN")),
            periodicity=periodicity,
            price_text=price_text,
            original_features=original_features,
            normalized_features=normalized_features,
            source_url=source_url,
            raw_payload={
                "plan_id": card.get("data-plan-id"),
                "name": name,
                "product": card.get("data-product"),
            },
            discount_percentage=discount_percentage,
            price_after_discount=price_after_discount,
            monthly_price=monthly_price,
            annual_total_price=annual_total,
            effective_monthly_price=effective_monthly,
            is_offer_active=is_offer_active,
            product=(str(card.get("data-product")) if card.get("data-product") else None),
            promotion_text=(promotion_node.get_text(" ", strip=True) if promotion_node else None),
        )
