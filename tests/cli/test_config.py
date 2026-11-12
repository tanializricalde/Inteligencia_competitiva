from pathlib import Path

import pytest

from scraper_cli.config import ConfigError, load_config, resolve_output_file, selected_providers

ROOT = Path(__file__).resolve().parents[2]


def test_example_config_is_valid_and_has_multiple_source_types():
    config = load_config(ROOT / "config.example.toml")

    assert len(config.providers) == 5
    assert config.providers[0].plan_sources[0].adapter_key == "fixture_plans"
    assert config.providers[0].review_sources[0].max_pages == 10
    assert [provider.code for provider in config.providers[1:]] == [
        "idrixcontable",
        "siigo_ec",
        "anfibius",
        "perseo",
    ]
    assert config.output.directory == "cli_dist/csv"
    assert config.providers[2].plans_filename == "planes_siigo.csv"

    expected_plan_sources = {
        "idrixcontable": ("idrixcontable_plans", "https://idrixcontable.com/planes"),
        "siigo_ec": ("siigo_plans", "https://www.siigo.com/ec/planes/"),
        "anfibius": (
            "anfibius_plans",
            "https://anfibius.net/planes-de-facturacion-electronica-cual-elegir-segun-tu-empresa/",
        ),
        "perseo": ("perseo_plans", "https://tusistemacontable.com/"),
    }
    for provider in config.providers[1:]:
        [source] = provider.plan_sources
        assert (source.adapter_key, source.url) == expected_plan_sources[provider.code]
        assert source.enabled is True


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            '[[providers]]\ncode="a"\nname="A"\nunknown=true\n',
            "claves desconocidas",
        ),
        (
            '[[providers]]\ncode="a"\nname="A"\n'
            '[[providers.plan_sources]]\nname="x"\nadapter_key="missing"\n'
            'url="https://example.com"\n',
            "adapter desconocido",
        ),
        (
            '[[providers]]\ncode="a"\nname="A"\n'
            '[[providers.plan_sources]]\nname="x"\nadapter_key="fixture_plans"\n'
            'url="file:///tmp/input"\n',
            "HTTP/HTTPS",
        ),
    ],
)
def test_invalid_config_reports_field_location(tmp_path, body, message):
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")

    with pytest.raises(ConfigError, match=message):
        load_config(path)


def test_unknown_provider_is_rejected():
    config = load_config(ROOT / "config.example.toml")

    with pytest.raises(ConfigError, match="proveedor inexistente"):
        selected_providers(config, ["no-existe"])


def test_configured_output_is_relative_to_process_cwd_and_cli_wins(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[output]\ndirectory="generated"\n'
        '[[providers]]\ncode="a"\nname="A"\nplans_filename="plans-a.csv"\n',
        encoding="utf-8",
    )
    config = load_config(config_path)
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.chdir(working)

    configured = resolve_output_file(
        config,
        provider_codes=["a"],
        kind="plans",
        output_format="csv",
        cli_value=None,
    )
    explicit = resolve_output_file(
        config,
        provider_codes=["a"],
        kind="plans",
        output_format="csv",
        cli_value="override.csv",
    )

    assert Path(configured) == working / "generated" / "plans-a.csv"
    assert Path(explicit) == working / "override.csv"


@pytest.mark.parametrize("filename", ["nested/plans.csv", r"nested\plans.csv", "../plans.csv"])
def test_provider_output_filename_rejects_directories(tmp_path, filename):
    path = tmp_path / "config.toml"
    path.write_text(
        f'[[providers]]\ncode="a"\nname="A"\nplans_filename=\'{filename}\'\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="solo un nombre de archivo"):
        load_config(path)


def test_configured_filename_requires_one_provider_and_matching_format():
    config = load_config(ROOT / "config.example.toml")

    with pytest.raises(ConfigError, match="más de un proveedor"):
        resolve_output_file(
            config,
            provider_codes=None,
            kind="plans",
            output_format="csv",
            cli_value=None,
        )
    with pytest.raises(ConfigError, match="debe terminar en .json"):
        resolve_output_file(
            config,
            provider_codes=["siigo_ec"],
            kind="plans",
            output_format="json",
            cli_value=None,
        )


def test_invalid_output_parent_reports_the_blocking_path(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[output]\ndirectory="blocked/generated"\n'
        '[[providers]]\ncode="a"\nname="A"\nreviews_filename="reviews.csv"\n',
        encoding="utf-8",
    )
    config = load_config(config_path)
    working = tmp_path / "working"
    working.mkdir()
    blocker = working / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.chdir(working)

    with pytest.raises(ConfigError, match=r"blocked.*no es un directorio"):
        resolve_output_file(
            config,
            provider_codes=["a"],
            kind="reviews",
            output_format="csv",
            cli_value=None,
        )
