from scraping_core.adapters import GoogleMapsReviewsAdapter
from scraping_core.reviews import ReviewSourceDTO


class Cards:
    def __init__(self, counts):
        self.counts = iter(counts)
        self.current = 0
        self.evaluations = 0

    @property
    def last(self):
        return self

    def count(self):
        self.current = next(self.counts, self.current)
        return self.current

    def evaluate(self, _script):
        self.evaluations += 1


class Container:
    @property
    def first(self):
        return self

    def filter(self, **_kwargs):
        return self

    def count(self):
        return 1

    def hover(self, **_kwargs):
        return None


class Mouse:
    def __init__(self):
        self.wheels = 0
        self.distances = []

    def wheel(self, _x, distance):
        self.wheels += 1
        self.distances.append(distance)


class Page:
    def __init__(self, counts):
        self.cards = Cards(counts)
        self.container = Container()
        self.mouse = Mouse()
        self.waits = []

    def locator(self, selector):
        if selector == GoogleMapsReviewsAdapter.selectors["card"]:
            return self.cards
        return self.container

    def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)


def test_maps_loading_uses_wheel_and_stops_after_stable_card_count():
    page = Page([5, 10, 10, 10])
    source = ReviewSourceDTO(
        id=None,
        provider_code="anfibius",
        platform="google_maps",
        source_url="https://example.test/maps",
        adapter_config={
            "max_scrolls": 10,
            "stable_scroll_attempts": 2,
            "scroll_pause_ms": 100,
            "scroll_pause_jitter_ms": 0,
            "scroll_distance_min": 321,
            "scroll_distance_max": 321,
            "max_load_seconds": 10,
        },
    )

    exhausted = GoogleMapsReviewsAdapter()._load_cards(page, source, target=20)

    assert exhausted is True
    assert page.mouse.wheels == 3
    assert page.mouse.distances == [321, 321, 321]
    assert page.waits == [100, 100, 100, 350]


def test_maps_loading_uses_last_card_fallback_after_repeated_stalls():
    page = Page([5, 5, 5, 5, 5])
    source = ReviewSourceDTO(
        id=None,
        provider_code="siigo_ec",
        platform="google_maps",
        source_url="https://example.test/maps",
        adapter_config={
            "max_scrolls": 10,
            "stable_scroll_attempts": 4,
            "scroll_pause_ms": 100,
            "scroll_pause_jitter_ms": 0,
            "scroll_rest_ms": 0,
            "max_load_seconds": 10,
        },
    )

    exhausted = GoogleMapsReviewsAdapter()._load_cards(page, source, target=20)

    assert exhausted is True
    assert page.mouse.wheels == 3
    assert page.cards.evaluations == 1
