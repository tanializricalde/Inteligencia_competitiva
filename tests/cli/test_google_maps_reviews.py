from pathlib import Path

import scraper_cli.runner as runner
from scraper_cli.config import (
    CliConfig,
    Defaults,
    ProviderConfig,
    ReviewSourceConfig,
    load_config,
)
from scraping_core.adapters import GoogleMapsReviewsAdapter
from scraping_core.reviews import ReviewScrapeBatch, ReviewScrapeCheckpoint

ROOT = Path(__file__).resolve().parents[2]


class FixtureGoogleMapsAdapter(GoogleMapsReviewsAdapter):
    def scrape(self, source, checkpoint):
        reviews, metadata, warnings = self._parse_html(
            (ROOT / "tests/fixtures/providers/maps_reviews_minimal.html").read_text(
                encoding="utf-8"
            ),
            source,
        )
        return ReviewScrapeBatch(
            reviews=reviews,
            next_checkpoint=ReviewScrapeCheckpoint({"offset": len(reviews)}),
            has_more=False,
            metadata=metadata,
            warnings=warnings,
        )


class PartialFixtureGoogleMapsAdapter(FixtureGoogleMapsAdapter):
    def scrape(self, source, checkpoint):
        batch = super().scrape(source, checkpoint)
        return ReviewScrapeBatch(
            reviews=batch.reviews,
            next_checkpoint=batch.next_checkpoint,
            has_more=False,
            metadata={**batch.metadata, "partial": True},
            warnings=("Resultado parcial de prueba",),
        )


class RecoveredFixtureGoogleMapsAdapter(FixtureGoogleMapsAdapter):
    def scrape(self, source, checkpoint):
        reviews, metadata, _warnings = self._parse_html(
            (ROOT / "tests/fixtures/providers/maps_reviews_minimal.html").read_text(
                encoding="utf-8"
            ),
            source,
        )
        offset = (checkpoint.cursor if checkpoint else {}).get("offset", 0)
        end = 2 if offset == 0 else len(reviews)
        return ReviewScrapeBatch(
            reviews=reviews[offset:end],
            next_checkpoint=ReviewScrapeCheckpoint({"offset": end}),
            has_more=end < len(reviews),
            metadata={**metadata, "partial": offset == 0},
            warnings=("Resultado parcial: primer intento",) if offset == 0 else (),
        )


def test_cli_runs_google_maps_adapter_and_maps_reviews(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runner,
        "GoogleMapsReviewsAdapter",
        lambda **kwargs: FixtureGoogleMapsAdapter(**kwargs),
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[providers]]
code = "anfibius"
name = "Anfibius"

  [[providers.review_sources]]
  name = "Reseñas Google Maps Anfibius"
  adapter_key = "google_maps_reviews"
  url = "https://www.google.com/maps/place/Anfibius+Ecuador/"
  platform = "google_maps"
  country_code = "EC"

    [providers.review_sources.config]
    page_size = 20
    max_scrolls = 30
    stable_scroll_attempts = 3
    scroll_pause_ms = 750
""".strip(),
        encoding="utf-8",
    )

    result = runner.run_reviews(load_config(config_path))

    assert result.exit_code == 0
    assert result.attempted == result.succeeded == 1
    assert len(result.rows) == 8
    assert result.rows[0]["competidor_id"] == "anfibius"
    assert result.rows[0]["plataforma"] == "google_maps"
    assert result.rows[0]["pais_codigo"] == "EC"
    assert result.rows[0]["usuario_nombre"] == "Angie Ocampo"
    assert result.rows[0]["calificacion_estrellas"] == 5
    assert result.rows[0]["fecha_comentario"] is None
    assert result.rows[0]["likes_comentario"] is None
    assert result.rows[0]["tiene_respuesta"] is False


def test_example_config_has_bounded_maps_source_for_each_real_provider():
    config = load_config(ROOT / "config.example.toml")
    providers = {provider.code: provider for provider in config.providers}
    expected = {
        "perseo": (45, 2, 10, 60),
        "idrixcontable": (60, 2, 25, 120),
        "anfibius": (90, 3, 100, 300),
        "siigo_ec": (180, 3, 500, 1200),
    }

    for code, (timeout, retries, page_size, max_load) in expected.items():
        [source] = providers[code].review_sources
        assert source.adapter_key == "google_maps_reviews"
        assert source.platform == "google_maps"
        assert source.country_code == "EC"
        assert source.timeout_seconds == timeout
        assert source.retry_limit == retries
        assert source.max_pages == 2
        assert source.config["page_size"] == page_size
        assert source.config["max_load_seconds"] == max_load
        assert source.config["scroll_pause_jitter_ms"] > 0


def test_cli_exports_partial_maps_rows_and_returns_partial_exit_code(monkeypatch):
    monkeypatch.setattr(
        runner,
        "GoogleMapsReviewsAdapter",
        lambda **kwargs: PartialFixtureGoogleMapsAdapter(**kwargs),
    )
    source = ReviewSourceConfig(
        name="Reseñas Maps",
        adapter_key="google_maps_reviews",
        url="https://www.google.com/maps/place/example/",
        platform="google_maps",
        country_code="EC",
    )
    config = CliConfig(
        Defaults(),
        (ProviderConfig("example", "Example", review_sources=(source,)),),
    )

    result = runner.run_reviews(config)

    assert len(result.rows) == 8
    assert result.succeeded == 1
    assert result.errors == []
    assert result.warnings == ["example/Reseñas Maps: Resultado parcial de prueba"]
    assert result.exit_code == 4


def test_cli_clears_intermediate_partial_warning_after_full_recovery(monkeypatch):
    monkeypatch.setattr(
        runner,
        "GoogleMapsReviewsAdapter",
        lambda **kwargs: RecoveredFixtureGoogleMapsAdapter(**kwargs),
    )
    source = ReviewSourceConfig(
        name="Reseñas Maps",
        adapter_key="google_maps_reviews",
        url="https://www.google.com/maps/place/example/",
        platform="google_maps",
        country_code="EC",
        max_pages=2,
    )
    config = CliConfig(
        Defaults(max_items=8),
        (ProviderConfig("example", "Example", review_sources=(source,)),),
    )

    result = runner.run_reviews(config)

    assert len(result.rows) == 8
    assert result.warnings == []
    assert result.exit_code == 0
