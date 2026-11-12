import pytest

from apps.scraping.infrastructure.builtin import register_builtin_adapters
from apps.scraping.infrastructure.registry import adapter_keys, get_adapter


def test_builtin_registry_is_explicit_and_idempotent():
    register_builtin_adapters()
    register_builtin_adapters()

    assert adapter_keys() == (
        "anfibius_plans",
        "example_httpx",
        "example_playwright",
        "idrixcontable_plans",
        "perseo_plans",
        "siigo_plans",
    )
    assert get_adapter("anfibius_plans").adapter_key == "anfibius_plans"
    assert get_adapter("example_httpx").adapter_key == "example_httpx"
    assert get_adapter("idrixcontable_plans").adapter_key == "idrixcontable_plans"
    assert get_adapter("perseo_plans").adapter_key == "perseo_plans"
    assert get_adapter("siigo_plans").adapter_key == "siigo_plans"


def test_unknown_adapter_cannot_import_arbitrary_code():
    with pytest.raises(ValueError, match="no registrado"):
        get_adapter("os.system")
