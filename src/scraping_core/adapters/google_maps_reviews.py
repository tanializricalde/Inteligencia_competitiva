"""Google Maps review adapter backed by the rendered, public page DOM."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from random import randint
from time import monotonic
from typing import Any

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from scraping_core.errors import (
    ReviewConfigurationError,
    ReviewStructureChangedError,
    ReviewTransportError,
)
from scraping_core.evidence import sanitize_html_evidence
from scraping_core.reviews import (
    ReviewScrapeBatch,
    ReviewScrapeCheckpoint,
    ReviewSourceDTO,
    ScrapedReviewDTO,
    normalize_country_code,
)
from scraping_core.security import validate_source_url


class GoogleMapsReviewsAdapter:
    """Load and parse review cards exposed in the rendered Google Maps DOM."""

    adapter_key = "google_maps_reviews"
    selectors = {
        "card": "div.jftiEf[data-review-id]:has(.kvMYJc[role='img'][aria-label])",
        "author": ".d4r55",
        "author_link": ".al6Kxe[data-href]",
        "author_avatar": "img.NBa7we",
        "author_stats": ".RfnDt",
        "rating": ".kvMYJc[role='img'][aria-label]",
        "relative_date": ".rsqaWe",
        "text": ".MyEned .wiI7pd",
        "language": ".MyEned[lang]",
        "translation": ".oqftme button[aria-controls]",
        "owner_response": ".CDe7pd",
        "owner_response_text": ".wiI7pd",
        "owner_response_date": ".DZSIDd",
        "owner_response_language": ".wiI7pd[lang]",
        "owner_response_translation": ".yJtsKb button[aria-controls]",
        "limited_view": "button.kyuRq[aria-label='Ver más']",
    }
    config_keys = {
        "page_size",
        "max_scrolls",
        "stable_scroll_attempts",
        "scroll_pause_ms",
        "scroll_pause_jitter_ms",
        "scroll_distance_min",
        "scroll_distance_max",
        "scroll_rest_every",
        "scroll_rest_ms",
        "max_load_seconds",
    }

    def __init__(
        self,
        playwright_factory=sync_playwright,
        evidence_dir: Path | None = None,
        *,
        user_agent: str = "MarketMonitorCLI/1.0",
        allow_private_hosts: bool = False,
    ) -> None:
        self.playwright_factory = playwright_factory
        self.evidence_dir = evidence_dir
        self.user_agent = user_agent
        self.allow_private_hosts = allow_private_hosts

    def validate_config(self, source: ReviewSourceDTO) -> None:
        unknown = sorted(set(source.adapter_config) - self.config_keys)
        if unknown:
            raise ReviewConfigurationError(
                f"Configuración Google Maps desconocida: {', '.join(unknown)}"
            )
        self._bounded_int(source, "page_size", 20, 1, 1_000)
        self._bounded_int(source, "max_scrolls", 200, 1, 1_000)
        self._bounded_int(source, "stable_scroll_attempts", 5, 1, 20)
        self._bounded_int(source, "scroll_pause_ms", 1_200, 100, 10_000)
        self._bounded_int(source, "scroll_pause_jitter_ms", 350, 0, 5_000)
        distance_min = self._bounded_int(source, "scroll_distance_min", 700, 100, 5_000)
        distance_max = self._bounded_int(source, "scroll_distance_max", 1_400, 100, 5_000)
        if distance_min > distance_max:
            raise ReviewConfigurationError(
                "scroll_distance_min no puede ser mayor que scroll_distance_max"
            )
        self._bounded_int(source, "scroll_rest_every", 10, 1, 100)
        self._bounded_int(source, "scroll_rest_ms", 4_000, 0, 30_000)
        self._bounded_int(source, "max_load_seconds", 180, 10, 3_600)
        if source.platform != "google_maps":
            raise ReviewConfigurationError("Google Maps requiere platform='google_maps'")

    def scrape(
        self,
        source: ReviewSourceDTO,
        checkpoint: ReviewScrapeCheckpoint | None,
    ) -> ReviewScrapeBatch:
        self.validate_config(source)
        offset = self._offset(checkpoint)
        page_size = self._bounded_int(source, "page_size", 20, 1, 1_000)
        if source.max_items is not None:
            page_size = min(page_size, max(1, source.max_items - offset))
        validate_source_url(
            source.source_url,
            allow_private_hosts=self.allow_private_hosts,
            resolve_host=self.playwright_factory is sync_playwright,
        )

        browser = context = page = None
        manager = self.playwright_factory()
        playwright = manager.__enter__()
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=self.user_agent,
                locale="es-EC",
            )
            page = context.new_page()
            page.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in {"image", "font", "media"}
                    else route.continue_()
                ),
            )
            timeout_ms = source.timeout_seconds * 1000
            target = offset + page_size
            reviews: list[ScrapedReviewDTO] = []
            metadata: dict[str, Any] = {}
            warnings: tuple[str, ...] = ()
            total: int | None = None
            exhausted = True
            complete = False
            last_failure: ReviewTransportError | None = None
            for attempt in range(source.retry_limit + 1):
                try:
                    try:
                        page.goto(
                            source.source_url,
                            wait_until="domcontentloaded",
                            timeout=timeout_ms,
                        )
                    except PlaywrightTimeoutError as exc:
                        raise ReviewTransportError(
                            "Playwright agotó el tiempo durante la navegación inicial "
                            "de Google Maps"
                        ) from exc
                    try:
                        page.wait_for_selector(
                            f"{self.selectors['card']}, {self.selectors['limited_view']}",
                            state="attached",
                            timeout=timeout_ms,
                        )
                    except PlaywrightTimeoutError as exc:
                        raise ReviewTransportError(
                            "Google Maps no mostró la primera tarjeta de reseña dentro del timeout"
                        ) from exc
                    if (
                        page.locator(self.selectors["card"]).count() == 0
                        and page.locator(self.selectors["limited_view"]).count() > 0
                    ):
                        raise ReviewTransportError(
                            "Google Maps entregó una vista limitada que no expone las reseñas "
                            "a esta sesión anónima"
                        )
                    initial_reviews, initial_metadata, initial_warnings = self._parse_html(
                        page.content(), source
                    )
                    if len(initial_reviews) >= len(reviews):
                        reviews = initial_reviews
                        metadata = initial_metadata
                        warnings = initial_warnings
                        total = initial_metadata.get("total_reviews")
                    attempt_target = min(target, total) if total is not None else target
                    attempt_exhausted = self._load_cards(page, source, attempt_target)
                    attempt_reviews, attempt_metadata, attempt_warnings = self._parse_html(
                        page.content(), source
                    )
                    if len(attempt_reviews) >= len(reviews):
                        reviews = attempt_reviews
                        metadata = attempt_metadata
                        warnings = attempt_warnings
                        exhausted = attempt_exhausted
                        total = metadata.get("total_reviews")
                    expected = min(target, total) if total is not None else target
                    if not attempt_exhausted or len(attempt_reviews) >= expected:
                        complete = True
                        reviews = attempt_reviews
                        metadata = attempt_metadata
                        warnings = attempt_warnings
                        exhausted = attempt_exhausted
                        total = attempt_metadata.get("total_reviews")
                        break
                    last_failure = ReviewTransportError(
                        "Google Maps detuvo la carga en "
                        f"{len(attempt_reviews)} de {expected} reseñas esperadas "
                        f"durante el intento {attempt + 1}"
                    )
                except (PlaywrightTimeoutError, ReviewTransportError) as exc:
                    last_failure = (
                        ReviewTransportError(
                            "Playwright agotó el tiempo durante el desplazamiento "
                            "de reseñas de Google Maps"
                        )
                        if isinstance(exc, PlaywrightTimeoutError)
                        else exc
                    )
                    partial = self._parse_available(page, source)
                    if partial is not None and len(partial[0]) > len(reviews):
                        reviews, metadata, warnings = partial
                        total = metadata.get("total_reviews")
                if attempt == source.retry_limit:
                    break
                page.close()
                context.close()
                context = browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent=self.user_agent,
                    locale="es-EC",
                )
                page = context.new_page()
                page.route(
                    "**/*",
                    lambda route: (
                        route.abort()
                        if route.request.resource_type in {"image", "font", "media"}
                        else route.continue_()
                    ),
                )
                page.wait_for_timeout(
                    self._bounded_int(source, "scroll_pause_ms", 1_200, 100, 10_000)
                )
            if not reviews:
                failure = last_failure or ReviewTransportError(
                    "Google Maps no devolvió reseñas después de los reintentos"
                )
                if offset > 0:
                    return ReviewScrapeBatch(
                        reviews=[],
                        next_checkpoint=ReviewScrapeCheckpoint({"offset": offset}),
                        has_more=False,
                        metadata={
                            "offset": offset,
                            "returned": 0,
                            "loaded": 0,
                            "partial": True,
                        },
                        warnings=(
                            "Resultado parcial: se conservaron "
                            f"{offset} reseñas de lotes anteriores; {failure}",
                        ),
                    )
                raise failure
            selected = reviews[offset:target]
            partial_result = not complete
            if partial_result:
                reason = str(last_failure or "la carga se detuvo antes del lote esperado")
                partial_warning = (
                    f"Resultado parcial: se conservaron {len(reviews)} reseñas cargadas; {reason}"
                )
                warnings = (*warnings, partial_warning)
            end = offset + len(selected)
            if partial_result:
                # One more batch may advance from the best checkpoint. If Maps stalls at
                # the same count, the next call returns no rows and closes pagination.
                has_more = bool(selected) and (total is None or end < total)
            else:
                has_more = not exhausted and (total is None or end < total)
            metadata.update(
                offset=offset,
                returned=len(selected),
                loaded=len(reviews),
                partial=partial_result,
            )
            return ReviewScrapeBatch(
                reviews=selected,
                next_checkpoint=ReviewScrapeCheckpoint({"offset": end}),
                has_more=has_more,
                metadata=metadata,
                warnings=warnings,
            )
        except PlaywrightTimeoutError as exc:
            self._capture_evidence(page, source, "timeout")
            raise ReviewTransportError(
                "Playwright agotó el tiempo esperando reseñas de Google Maps"
            ) from exc
        except (ReviewConfigurationError, ReviewStructureChangedError, ReviewTransportError):
            self._capture_evidence(page, source, "scrape-error")
            raise
        except (PlaywrightError, ValueError) as exc:
            self._capture_evidence(page, source, "extraction-error")
            raise ReviewStructureChangedError(
                "Falló la extracción de la página renderizada de Google Maps"
            ) from exc
        finally:
            if page is not None:
                page.close()
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()
            manager.__exit__(None, None, None)

    def _parse_available(
        self, page: Any, source: ReviewSourceDTO
    ) -> tuple[list[ScrapedReviewDTO], dict[str, Any], tuple[str, ...]] | None:
        """Return a usable DOM snapshot after a transport failure, if one exists."""
        try:
            return self._parse_html(page.content(), source)
        except (PlaywrightError, ReviewStructureChangedError):
            return None

    def _load_cards(self, page: Any, source: ReviewSourceDTO, target: int) -> bool:
        max_scrolls = self._bounded_int(source, "max_scrolls", 200, 1, 1_000)
        stable_limit = self._bounded_int(source, "stable_scroll_attempts", 5, 1, 20)
        pause_ms = self._bounded_int(source, "scroll_pause_ms", 1_200, 100, 10_000)
        pause_jitter_ms = self._bounded_int(source, "scroll_pause_jitter_ms", 350, 0, 5_000)
        distance_min = self._bounded_int(source, "scroll_distance_min", 700, 100, 5_000)
        distance_max = self._bounded_int(source, "scroll_distance_max", 1_400, 100, 5_000)
        rest_every = self._bounded_int(source, "scroll_rest_every", 10, 1, 100)
        rest_ms = self._bounded_int(source, "scroll_rest_ms", 4_000, 0, 30_000)
        deadline = monotonic() + self._bounded_int(source, "max_load_seconds", 180, 10, 3_600)
        cards = page.locator(self.selectors["card"])
        previous = cards.count()
        if previous >= target:
            return False
        container = page.locator('div.m6QErb.DxyBCb[tabindex="-1"]').filter(has=cards).first
        # Maps can ignore wheel input while the review drawer is still settling.
        # A bounded initial pause also makes the first lazy-load request reliable.
        page.wait_for_timeout(self._jittered_pause(pause_ms, pause_jitter_ms))
        stable = 0
        for scroll_index in range(1, max_scrolls + 1):
            if previous >= target:
                return False
            if monotonic() >= deadline:
                raise ReviewTransportError(
                    "Google Maps excedió max_load_seconds mientras cargaba reseñas"
                )
            if container.count():
                if stable >= 2 and stable % 3 == 0:
                    cards.last.evaluate("element => element.scrollIntoView({block: 'end'})")
                else:
                    container.hover(force=True)
                    page.mouse.wheel(0, randint(distance_min, distance_max))
            else:
                cards.last.evaluate("element => element.scrollIntoView({block: 'end'})")
            wait_ms = self._jittered_pause(pause_ms, pause_jitter_ms)
            if stable:
                wait_ms = min(10_000, wait_ms + stable * 250)
            page.wait_for_timeout(wait_ms)
            if rest_ms and scroll_index % rest_every == 0:
                page.wait_for_timeout(self._jittered_pause(rest_ms, min(pause_jitter_ms, rest_ms)))
            current = cards.count()
            stable = stable + 1 if current <= previous else 0
            previous = current
            if stable >= stable_limit:
                return True
        return previous < target

    def _jittered_pause(self, pause_ms: int, jitter_ms: int) -> int:
        if jitter_ms == 0:
            return pause_ms
        return randint(max(100, pause_ms - jitter_ms), min(10_000, pause_ms + jitter_ms))

    def _parse_html(
        self, html: str, source: ReviewSourceDTO
    ) -> tuple[list[ScrapedReviewDTO], dict[str, Any], tuple[str, ...]]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(self.selectors["card"])
        if not cards:
            raise ReviewStructureChangedError(
                "No se encontraron tarjetas con data-review-id en Google Maps"
            )
        reviews: list[ScrapedReviewDTO] = []
        seen: set[str] = set()
        for card in cards:
            review_id = self._required_attribute(card, "data-review-id")
            if review_id in seen:
                continue
            seen.add(review_id)
            reviews.append(self._parse_card(card, source, review_id))
        metadata = self._summary(soup)
        warnings: list[str] = []
        distribution_total = sum(
            item["review_count"] for item in metadata.get("rating_distribution", [])
        )
        if metadata.get("total_reviews") is not None and distribution_total not in {
            0,
            metadata["total_reviews"],
        }:
            warnings.append("El total visible difiere de la distribución por estrellas")
        return reviews, metadata, tuple(warnings)

    def _parse_card(self, card: Tag, source: ReviewSourceDTO, review_id: str) -> ScrapedReviewDTO:
        author_url = self._attribute(card, self.selectors["author_link"], "data-href")
        author_stats = self._text(card, self.selectors["author_stats"])
        language_node = card.select_one(self.selectors["language"])
        response_node = card.select_one(self.selectors["owner_response"])
        response_text = (
            self._text(response_node, self.selectors["owner_response_text"])
            if response_node
            else None
        )
        response_language_node = (
            response_node.select_one(self.selectors["owner_response_language"])
            if response_node
            else None
        )
        raw_payload = {
            "author_url": author_url,
            "author_id": self._author_id(author_url),
            "author_avatar_url": self._attribute(card, self.selectors["author_avatar"], "src"),
            "author_review_count": self._review_count(author_stats),
            "author_stats_text": author_stats,
            "relative_date": self._text(card, self.selectors["relative_date"]),
            "displayed_language": language_node.get("lang") if language_node else None,
            "is_translation": card.select_one(self.selectors["translation"]) is not None,
            "original_text": None,
            "original_language": None,
            "likes": None,
            "owner_response": (
                {
                    "relative_date": self._text(
                        response_node, self.selectors["owner_response_date"]
                    ),
                    "displayed_language": (
                        response_language_node.get("lang") if response_language_node else None
                    ),
                    "is_translation": response_node.select_one(
                        self.selectors["owner_response_translation"]
                    )
                    is not None,
                }
                if response_node
                else None
            ),
            "sentiment": None,
        }
        return ScrapedReviewDTO(
            external_review_id=review_id,
            app_id=None,
            platform=source.platform,
            country_code=normalize_country_code(source.country_code),
            published_at=None,
            author_name=self._text(card, self.selectors["author"]),
            rating=self._rating(card),
            review_text=self._text(card, self.selectors["text"]),
            app_version=None,
            helpful_votes=None,
            developer_response_text=response_text,
            developer_response_at=None,
            source_url=source.source_url,
            raw_payload=raw_payload,
            response_known=True,
        )

    def _summary(self, soup: BeautifulSoup) -> dict[str, Any]:
        average_node = soup.select_one(".jANrlb .fontDisplayLarge")
        total_node = soup.select_one(".jANrlb .fontBodySmall")
        distribution = []
        for row in soup.select("tr.BHOKXe[role='img'][aria-label]"):
            values = re.search(
                r"([1-5])\D+([\d.,]+)\s+(?:review|reseña)",
                str(row.get("aria-label", "")),
                re.IGNORECASE,
            )
            if values:
                distribution.append(
                    {"rating": int(values.group(1)), "review_count": self._integer(values.group(2))}
                )
        return {
            "average_rating": self._decimal(average_node.get_text(strip=True))
            if average_node
            else None,
            "total_reviews": self._first_integer(total_node.get_text(" ", strip=True))
            if total_node
            else None,
            "rating_distribution": distribution,
        }

    def _rating(self, card: Tag) -> int:
        label = self._attribute(card, self.selectors["rating"], "aria-label")
        match = re.search(r"(?<!\d)([1-5])(?:[.,]0)?(?!\d)", label or "")
        if not match:
            raise ReviewStructureChangedError("Una reseña no contiene calificación válida")
        return int(match.group(1))

    def _bounded_int(
        self, source: ReviewSourceDTO, key: str, default: int, minimum: int, maximum: int
    ) -> int:
        value = source.adapter_config.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ReviewConfigurationError(f"{key} debe estar entre {minimum} y {maximum}")
        return value

    def _offset(self, checkpoint: ReviewScrapeCheckpoint | None) -> int:
        value = (checkpoint.cursor if checkpoint else {}).get("offset", 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ReviewConfigurationError("checkpoint.offset debe ser un entero no negativo")
        return value

    def _required_attribute(self, node: Tag, name: str) -> str:
        value = node.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ReviewStructureChangedError(f"Una reseña no contiene {name}")
        return value.strip()

    def _text(self, card: Tag, selector: str) -> str | None:
        node = card.select_one(selector)
        if node is None:
            return None
        # BeautifulSoup must remove markup to expose visible text, but do not
        # change case, punctuation, or same-line spacing. Google Maps includes
        # layout/user line separators inside text nodes; flatten only those so
        # one exported review remains on one physical CSV line.
        value = node.get_text(" ", strip=True)
        if value:
            value = " ".join(part.strip() for part in value.splitlines() if part.strip())
        return value or None

    def _attribute(self, card: Tag, selector: str, name: str) -> str | None:
        node = card.select_one(selector)
        value = node.get(name) if node else None
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _author_id(self, url: str | None) -> str | None:
        match = re.search(r"/maps/contrib/(\d+)/reviews", url or "")
        return match.group(1) if match else None

    def _review_count(self, value: str | None) -> int | None:
        match = re.search(r"([\d.,]+)\s+(?:review|reseña)", value or "", re.IGNORECASE)
        return self._integer(match.group(1)) if match else None

    def _first_integer(self, value: str) -> int | None:
        match = re.search(r"[\d.,]+", value)
        return self._integer(match.group()) if match else None

    def _integer(self, value: str) -> int:
        return int(re.sub(r"[^0-9]", "", value))

    def _decimal(self, value: str) -> float | None:
        match = re.search(r"\d+(?:[.,]\d+)?", value)
        return float(match.group().replace(",", ".")) if match else None

    def _capture_evidence(self, page: Any, source: ReviewSourceDTO, reason: str) -> None:
        if page is None or source.id is None or self.evidence_dir is None:
            return
        directory = self.evidence_dir / f"review-source-{source.id}"
        directory.mkdir(parents=True, exist_ok=True)
        try:
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            page.screenshot(path=str(directory / f"{stamp}-{reason}.png"), full_page=False)
            (directory / f"{stamp}-{reason}.html.txt").write_text(
                sanitize_html_evidence(page.content()), encoding="utf-8"
            )
        except PlaywrightError:
            return
