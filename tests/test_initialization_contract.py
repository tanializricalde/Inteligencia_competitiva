from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_supported_initialization_paths_seed_pipeline_after_migrations():
    for relative_path in (
        "Makefile",
        "Makefile.ps1",
        "scripts/dev-bootstrap.sh",
        "scripts/dev-bootstrap.ps1",
        "scripts/deploy-production.sh",
        "scripts/deploy-production.ps1",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert source.index("manage.py migrate") < source.index("manage.py seed_market_pipeline")


def test_runtime_image_contains_seed_inputs():
    source = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY config.example.toml ./" in source
    assert "COPY feature_rules/ ./feature_rules/" in source
