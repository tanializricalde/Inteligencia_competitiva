import os
import subprocess
import sys
from pathlib import Path

import pytest

from scraper_cli.config import (
    CliConfig,
    ConfigError,
    Defaults,
    PlanSourceConfig,
    ProviderConfig,
)
from scraper_cli.runner import RunResult, run_plans

ROOT = Path(__file__).resolve().parents[2]


def _config(sources):
    return CliConfig(Defaults(), (ProviderConfig("p", "Provider", tuple(sources)),))


def _source(name, **config):
    return PlanSourceConfig(name, "fixture_plans", "https://fixture.invalid/plans", config=config)


def test_partial_success_keeps_rows_and_fail_fast_stops():
    good = _source(
        "good",
        fixture_plans=[{"external_id": "x", "name": "X", "price": "0", "periodicity": "monthly"}],
    )
    bad = _source("bad", simulate_error="timeout", fixture_plans=[])

    partial = run_plans(_config([good, bad]))
    stopped = run_plans(_config([bad, good]), fail_fast=True)

    assert partial.exit_code == 4
    assert len(partial.rows) == 1
    assert partial.attempted == 2
    assert stopped.exit_code == 3
    assert stopped.attempted == 1
    assert stopped.rows == []


def test_warning_marks_export_as_partial_without_discarding_rows():
    result = RunResult(rows=[{"kept": True}], attempted=1, succeeded=1)
    result.warnings.append("La fuente se detuvo después de cargar datos")

    assert result.rows == [{"kept": True}]
    assert result.failed == 0
    assert result.exit_code == 4


def test_disabled_or_missing_selected_source_is_rejected():
    disabled = PlanSourceConfig(
        "off", "fixture_plans", "https://fixture.invalid/plans", enabled=False
    )
    with pytest.raises(ConfigError, match="fuente activa inexistente"):
        run_plans(_config([disabled]), source_names=["off"])


def test_help_validation_and_fixture_run_ignore_invalid_database(tmp_path):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["DATABASE_URL"] = "postgresql://invalid:invalid@127.0.0.1:1/invalid"
    commands = [
        ["--help"],
        ["validate-config", "--config", str(ROOT / "config.example.toml")],
        [
            "reviews",
            "--config",
            str(ROOT / "config.example.toml"),
            "--provider",
            "competidor_demo",
            "--format",
            "json",
            "--output",
            str(tmp_path / "reviews.json"),
        ],
        [
            "reviews",
            "--config",
            str(ROOT / "config.example.toml"),
            "--provider",
            "competidor_demo",
        ],
    ]
    for arguments in commands:
        completed = subprocess.run(
            [sys.executable, "-m", "scraper_cli", *arguments],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
    assert not list(tmp_path.glob("*.sqlite3"))
    assert (tmp_path / "cli_dist/csv/resenas_demo.csv").is_file()
