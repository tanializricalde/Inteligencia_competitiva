from decimal import Decimal
from pathlib import Path

import httpx

import scraper_cli.runner as runner
from scraper_cli.config import load_config
from scraping_core.adapters.siigo_plans import SiigoPlanScraper as CoreSiigoPlanScraper

ROOT = Path(__file__).resolve().parents[2]


def test_cli_runs_siigo_adapter_and_maps_external_rows(tmp_path, monkeypatch):
    html = (ROOT / "tests/fixtures/providers/siigo_planes.html").read_text(encoding="utf-8")
    clients: list[httpx.Client] = []

    def adapter_factory(**kwargs):
        def response(request):
            return httpx.Response(
                200,
                text=html,
                headers={"content-type": "text/html"},
                request=request,
            )

        client = httpx.Client(transport=httpx.MockTransport(response))
        clients.append(client)
        return CoreSiigoPlanScraper(client, **kwargs)

    monkeypatch.setattr(runner, "SiigoPlanScraper", adapter_factory)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[providers]]
code = "siigo_ec"
name = "Siigo Ecuador"

  [[providers.plan_sources]]
  name = "Planes públicos Siigo"
  adapter_key = "siigo_plans"
  url = "https://www.siigo.com/ec/planes/"
""".strip(),
        encoding="utf-8",
    )

    try:
        result = runner.run_plans(load_config(config_path))
    finally:
        for client in clients:
            client.close()

    assert result.exit_code == 0
    assert result.attempted == result.succeeded == 1
    assert len(result.rows) == 1
    assert result.rows[0]["competidor_id"] == "siigo_ec"
    assert result.rows[0]["producto"] == "accounting-suscripcion"
    assert result.rows[0]["plan_id"] == "9700003000182"
    assert result.rows[0]["precio_mensual"] == Decimal("54.00")
    assert result.rows[0]["precio_anual_total"] == Decimal("567.00")
    assert result.rows[0]["precio_mensual_efectivo"] == Decimal("47.25")
    assert result.feature_rows[0]["nombre_modulo"] == "Múltiples bodegas"
