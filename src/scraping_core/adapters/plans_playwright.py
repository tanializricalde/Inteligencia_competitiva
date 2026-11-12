from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from scraping_core.errors import ScrapeError, ScrapeTimeoutError, StructureChangedError
from scraping_core.evidence import sanitize_html_evidence
from scraping_core.plans import PlanSourceDTO, ScrapedPlanDTO
from scraping_core.security import validate_source_url

from .plans_httpx import HttpxPlanScraper


class PlaywrightPlanScraper(HttpxPlanScraper):
    adapter_key = "example_playwright"
    wait_selector = "[data-plans-root] .plan-card"

    def __init__(
        self,
        playwright_factory=sync_playwright,
        evidence_dir: Path | None = None,
        *,
        user_agent: str = "MarketMonitorCLI/1.0",
        allow_private_hosts: bool = False,
    ):
        self.playwright_factory = playwright_factory
        self.evidence_dir = evidence_dir
        self.user_agent = user_agent
        self.allow_private_hosts = allow_private_hosts

    def scrape(self, source: PlanSourceDTO) -> list[ScrapedPlanDTO]:
        validate_source_url(
            source.url,
            allow_private_hosts=self.allow_private_hosts,
            resolve_host=self.playwright_factory is sync_playwright,
        )
        browser = context = page = None
        manager = self.playwright_factory()
        playwright = manager.__enter__()
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900}, user_agent=self.user_agent
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
            page.goto(source.url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector(self.wait_selector, state="attached", timeout=timeout_ms)
            return self._parse(page.content(), source.url)
        except PlaywrightTimeoutError as exc:
            self._capture_evidence(page, source, "timeout")
            raise ScrapeTimeoutError("Playwright agotó el tiempo esperando planes") from exc
        except ScrapeError:
            self._capture_evidence(page, source, "scrape-error")
            raise
        except (PlaywrightError, ValueError) as exc:
            self._capture_evidence(page, source, "extraction-error")
            raise StructureChangedError("Falló la extracción de la página renderizada") from exc
        finally:
            if page is not None:
                page.close()
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()
            manager.__exit__(None, None, None)

    def _capture_evidence(self, page, source: PlanSourceDTO, reason: str) -> None:
        if page is None or source.id is None or self.evidence_dir is None:
            return
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        directory = self.evidence_dir / f"source-{source.id}"
        directory.mkdir(parents=True, exist_ok=True)
        basename = f"{stamp}-{reason}"
        try:
            page.screenshot(path=str(directory / f"{basename}.png"), full_page=False)
            safe_html = sanitize_html_evidence(page.content())
            (directory / f"{basename}.html.txt").write_text(safe_html, encoding="utf-8")
        except PlaywrightError:
            return
