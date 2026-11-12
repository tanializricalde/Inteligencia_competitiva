from pathlib import Path

import scraper_cli.runner as runner
from scraper_cli.config import load_config
from scraping_core.adapters import AnfibiusPlanScraper, PerseoPlanScraper

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "providers"


class _StaticAdapter:
    def __init__(self, parser, fixture: str):
        self.parser = parser
        self.html = (FIXTURES / fixture).read_text(encoding="utf-8")

    def scrape(self, source):
        return self.parser._parse(self.html, source.url)


def test_cli_accepts_builds_and_executes_legacy_plan_adapters(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runner,
        "AnfibiusPlanScraper",
        lambda **_kwargs: _StaticAdapter(AnfibiusPlanScraper(), "anfibius_plans.html"),
    )
    monkeypatch.setattr(
        runner,
        "PerseoPlanScraper",
        lambda **_kwargs: _StaticAdapter(PerseoPlanScraper(), "perseo_plans.html"),
    )
    path = tmp_path / "config.toml"
    path.write_text(
        """
[[providers]]
code = "anfibius"
name = "Anfibius"
  [[providers.plan_sources]]
  name = "Planes Anfibius"
  adapter_key = "anfibius_plans"
  url = "https://anfibius.net/planes/"

[[providers]]
code = "perseo"
name = "Perseo"
  [[providers.plan_sources]]
  name = "Planes Perseo"
  adapter_key = "perseo_plans"
  url = "https://tusistemacontable.com/"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(path)
    result = runner.run_plans(config)

    assert [
        source.adapter_key for provider in config.providers for source in provider.plan_sources
    ] == [
        "anfibius_plans",
        "perseo_plans",
    ]
    assert result.exit_code == 0
    assert result.attempted == result.succeeded == 2
    assert len(result.rows) == 6
    assert {row["producto"] for row in result.rows} == {
        "facturacion-electronica",
        "perseo-web",
        "perseo-pc",
        "perseo-prime",
    }
