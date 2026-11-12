from scraper_cli.config import load_config
from scraper_cli.runner import _plan_adapter
from scraping_core.adapters import SiigoPlanScraper


def test_siigo_adapter_is_accepted_and_built_with_cli_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[defaults]
user_agent = "Configured CLI/1.0"
max_response_bytes = 12345

[[providers]]
code = "siigo_ec"
name = "Siigo Ecuador"

  [[providers.plan_sources]]
  name = "Planes"
  adapter_key = "siigo_plans"
  url = "https://www.siigo.com/ec/planes/"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(path)
    adapter = _plan_adapter("siigo_plans", config)

    assert config.providers[0].plan_sources[0].adapter_key == "siigo_plans"
    assert isinstance(adapter, SiigoPlanScraper)
    assert adapter.max_response_bytes == 12345
    assert adapter.client.headers["user-agent"] == "Configured CLI/1.0"
    adapter.close()
