from scraper_cli.config import load_config
from scraper_cli.runner import _plan_adapter
from scraping_core.adapters import IdrixContablePlanScraper


def test_idrix_adapter_is_accepted_and_built_with_cli_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[defaults]
user_agent = "Configured CLI/1.0"

[[providers]]
code = "idrixcontable"
name = "iDrix Contable"

  [[providers.plan_sources]]
  name = "Planes contables"
  adapter_key = "idrixcontable_plans"
  url = "https://idrixcontable.com/planes"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(path)
    adapter = _plan_adapter("idrixcontable_plans", config)

    assert isinstance(adapter, IdrixContablePlanScraper)
    assert adapter.user_agent == "Configured CLI/1.0"
    assert config.providers[0].plan_sources[0].adapter_key == "idrixcontable_plans"
