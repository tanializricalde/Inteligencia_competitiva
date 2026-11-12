from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from scraping_core.adapters import GoogleMapsReviewsAdapter
from scraping_core.errors import ReviewTransportError
from scraping_core.reviews import ReviewScrapeCheckpoint, ReviewSourceDTO

FIXTURE = Path(__file__).parents[1] / "fixtures/providers/maps_reviews_minimal.html"


class FakeLocator:
    def __init__(self, count=8):
        self._count = count

    def count(self):
        return self._count


class FakePage:
    def __init__(self):
        self.closed = False

    def route(self, *_args):
        return None

    def goto(self, *_args, **_kwargs):
        return None

    def wait_for_selector(self, *_args, **_kwargs):
        return None

    def wait_for_timeout(self, *_args, **_kwargs):
        return None

    def locator(self, selector):
        if selector == GoogleMapsReviewsAdapter.selectors["limited_view"]:
            return FakeLocator(0)
        return FakeLocator()

    def content(self):
        return FIXTURE.read_text(encoding="utf-8")

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


def test_maps_browser_transport_returns_batch_and_closes_resources():
    manager = FakeManager()
    adapter = GoogleMapsReviewsAdapter(playwright_factory=lambda: manager)
    source = ReviewSourceDTO(
        id=None,
        provider_code="anfibius",
        platform="google_maps",
        source_url="https://example.test/maps",
        country_code="EC",
        max_items=4,
        adapter_config={"page_size": 8},
    )

    batch = adapter.scrape(source, None)

    assert len(batch.reviews) == 4
    assert batch.next_checkpoint.cursor == {"offset": 4}
    assert batch.has_more
    assert batch.metadata["total_reviews"] == 50
    assert manager.page.closed
    assert manager.context.closed
    assert manager.browser.closed
    assert manager.exited


@pytest.mark.parametrize(
    "failure",
    [
        ReviewTransportError("Google Maps excedió max_load_seconds"),
        PlaywrightTimeoutError("hover timed out"),
    ],
)
def test_maps_transport_returns_loaded_cards_when_the_last_load_step_fails(
    monkeypatch, failure
):
    manager = FakeManager()
    adapter = GoogleMapsReviewsAdapter(playwright_factory=lambda: manager)
    source = ReviewSourceDTO(
        id=None,
        provider_code="anfibius",
        platform="google_maps",
        source_url="https://example.test/maps",
        country_code="EC",
        retry_limit=0,
        max_items=20,
        adapter_config={"page_size": 20},
    )

    calls = 0

    def fail_after_loading(*_args):
        nonlocal calls
        calls += 1
        raise failure

    monkeypatch.setattr(adapter, "_load_cards", fail_after_loading)

    batch = adapter.scrape(source, None)

    assert len(batch.reviews) == 8
    assert batch.next_checkpoint.cursor == {"offset": 8}
    assert batch.has_more
    assert batch.metadata["partial"] is True
    assert "se conservaron 8 reseñas" in batch.warnings[-1]
    assert calls == 1


def test_maps_caps_scroll_target_to_the_visible_metadata_total(monkeypatch):
    manager = FakeManager()
    adapter = GoogleMapsReviewsAdapter(playwright_factory=lambda: manager)
    source = ReviewSourceDTO(
        id=None,
        provider_code="anfibius",
        platform="google_maps",
        source_url="https://example.test/maps",
        max_items=1_000,
        adapter_config={"page_size": 500},
    )
    targets = []

    def capture_target(_page, _source, target):
        targets.append(target)
        return True

    monkeypatch.setattr(adapter, "_load_cards", capture_target)

    adapter.scrape(source, None)

    assert targets and set(targets) == {50}


def test_maps_partial_batch_stops_cleanly_when_checkpoint_cannot_advance(monkeypatch):
    manager = FakeManager()
    adapter = GoogleMapsReviewsAdapter(playwright_factory=lambda: manager)
    source = ReviewSourceDTO(
        id=None,
        provider_code="anfibius",
        platform="google_maps",
        source_url="https://example.test/maps",
        country_code="EC",
        retry_limit=0,
        max_items=20,
        adapter_config={"page_size": 20},
    )
    monkeypatch.setattr(adapter, "_load_cards", lambda *_args: True)

    batch = adapter.scrape(source, ReviewScrapeCheckpoint({"offset": 8}))

    assert batch.reviews == []
    assert batch.next_checkpoint.cursor == {"offset": 8}
    assert not batch.has_more
    assert batch.metadata["partial"] is True


def test_maps_later_initial_timeout_preserves_previous_checkpoint():
    manager = FakeManager()
    manager.page.wait_for_selector = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        PlaywrightTimeoutError("timed out")
    )
    manager.page.content = lambda: "<html><body></body></html>"
    adapter = GoogleMapsReviewsAdapter(playwright_factory=lambda: manager)
    source = ReviewSourceDTO(
        id=None,
        provider_code="siigo_ec",
        platform="google_maps",
        source_url="https://example.test/maps",
        country_code="EC",
        retry_limit=0,
        max_items=100,
        adapter_config={"page_size": 20},
    )

    batch = adapter.scrape(source, ReviewScrapeCheckpoint({"offset": 40}))

    assert batch.reviews == []
    assert batch.next_checkpoint.cursor == {"offset": 40}
    assert not batch.has_more
    assert batch.metadata["partial"] is True
    assert "se conservaron 40 reseñas" in batch.warnings[-1]


def test_maps_limited_view_fails_fast_with_a_specific_error():
    manager = FakeManager()
    manager.page.locator = lambda selector: FakeLocator(
        1 if selector == GoogleMapsReviewsAdapter.selectors["limited_view"] else 0
    )
    manager.page.content = lambda: (
        "<html><body><button aria-label='Ver más'></button></body></html>"
    )
    adapter = GoogleMapsReviewsAdapter(playwright_factory=lambda: manager)
    source = ReviewSourceDTO(
        id=None,
        provider_code="anfibius",
        platform="google_maps",
        source_url="https://example.test/maps",
        retry_limit=0,
    )

    with pytest.raises(ReviewTransportError, match="vista limitada"):
        adapter.scrape(source, None)
