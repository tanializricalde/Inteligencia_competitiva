import pytest

from apps.scraping.application.dtos import ScrapeSourceDTO
from apps.scraping.application.errors import StructureChangedError
from apps.scraping.infrastructure.providers.example_playwright import (
    ExamplePlaywrightProviderScraper,
)


class FakePage:
    def __init__(self):
        self.closed = False

    def route(self, *_args):
        return None

    def goto(self, *_args, **_kwargs):
        return None

    def wait_for_selector(self, *_args, **_kwargs):
        return None

    def content(self):
        return """<section data-plans-root><article class="plan-card">
        <h2 class="plan-name">Pro</h2><span class="plan-price">10</span>
        <span class="plan-feature" data-key="support" data-state="invalid">Support</span>
        </article></section>"""

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, page):
        self.page = page
        self.closed = False

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, context):
        self.context = context
        self.closed = False

    def new_context(self, **_kwargs):
        return self.context

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, browser):
        self.browser = browser

    def launch(self, **_kwargs):
        return self.browser


class FakeManager:
    def __init__(self):
        self.page = FakePage()
        self.context = FakeContext(self.page)
        self.browser = FakeBrowser(self.context)
        self.chromium = FakeChromium(self.browser)
        self.exited = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.exited = True


def test_extraction_error_closes_page_context_browser_and_manager():
    manager = FakeManager()
    adapter = ExamplePlaywrightProviderScraper(playwright_factory=lambda: manager)

    with pytest.raises(StructureChangedError):
        adapter.scrape(ScrapeSourceDTO(None, "https://example.test/plans"))

    assert manager.page.closed
    assert manager.context.closed
    assert manager.browser.closed
    assert manager.exited
