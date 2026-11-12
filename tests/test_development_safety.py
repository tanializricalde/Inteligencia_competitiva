from pathlib import Path

from django.conf import settings


def test_pytest_database_is_isolated_from_development_data():
    database_name = str(settings.DATABASES["default"]["NAME"])

    assert database_name == ":memory:" or "mode=memory" in database_name
    assert "data/market-watch.sqlite3" not in database_name


def test_compose_uses_a_named_volume_instead_of_native_database():
    compose = (Path(__file__).parents[1] / "compose.yaml").read_text(encoding="utf-8")

    assert "sqlite-data:/app/data" in compose
    assert "./data:/app/data" not in compose
