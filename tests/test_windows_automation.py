from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_task_runner_exposes_safe_core_workflows():
    source = (ROOT / "Makefile.ps1").read_text(encoding="utf-8")

    for task in (
        "'dev'",
        "'scheduler'",
        "'assets'",
        "'migrate'",
        "'test'",
        "'docs-check'",
        "'deploy-check'",
        "'deploy'",
        "'nginx-check'",
        "'docker-up'",
        "'docker-down'",
    ):
        assert task in source
    assert "docker compose down -v" not in source
    assert "Remove-Item" not in source
    assert ".venv\\Scripts\\python.exe" in source
    assert 'deploy-production.ps1" -Check' in source
    assert 'deploy-production.ps1" -Apply' in source


def test_windows_bootstrap_preserves_existing_environment_and_builds_assets():
    source = (ROOT / "scripts/dev-bootstrap.ps1").read_text(encoding="utf-8")

    assert "if (-not (Test-Path '.env'))" in source
    assert "Copy-Item '.env.example' '.env'" in source
    assert "--frozen-lockfile" in source
    assert "manage.py migrate" in source
    assert "manage.py seed_market_pipeline" in source
    assert "manage.py check" in source
    assert "Remove-Item" not in source


def test_windows_production_deploy_preserves_data_and_matches_release_sequence():
    source = (ROOT / "scripts/deploy-production.ps1").read_text(encoding="utf-8")

    for contract in (
        "Test-ProductionEnvironment",
        "[switch]$LocalHttp",
        "ALLOW_INSECURE_LOCAL_HTTP",
        "Test-ProductionEnvironment -Path $ValidationEnv -Profile $Profile",
        "Configuración local HTTP válida",
        "ALLOWED_HOSTS sólo puede contener localhost",
        "SECRET_KEY debe ser aleatoria",
        "docker compose --env-file",
        "backup_sqlite",
        "docker compose build",
        "manage.py migrate",
        "manage.py seed_market_pipeline",
        "docker compose up -d web scheduler",
        "$ActiveServices -contains 'scheduler'",
        "/public/ready",
        "Release $($env:IMAGE_TAG) saludable",
    ):
        assert contract in source
    assert "docker compose down -v" not in source
    assert "Remove-Item" not in source
    assert "SCRAPER_ALLOW_PRIVATE_HOSTS = 'false'" in source
