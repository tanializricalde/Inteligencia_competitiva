import base64
import importlib

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from apps.market.models import (
    DashboardPreset,
    DashboardPresetPlan,
    DashboardPresetProvider,
    DashboardSettings,
    Provider,
)
from apps.pipeline.models import (
    MarketPlan,
    PipelineRun,
    PlanFeatureValue,
    PlanSnapshot,
    ReviewSnapshot,
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
SVG_VALID = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 32">
<title>Logo</title><rect width="64" height="32" fill="#2563eb"/></svg>"""


@pytest.mark.django_db
def test_dashboard_settings_are_singleton_and_default_requires_active_real_preset():
    real = DashboardPreset.objects.create(name="Real", slug="real-preset")
    demo = DashboardPreset.objects.get(slug=DashboardPreset.SYSTEM_DEMO_SLUG)
    settings = DashboardSettings.load()
    settings.default_preset = real
    settings.save()

    assert settings.pk == 1
    assert DashboardSettings.objects.count() == 1
    assert DashboardSettings.load().default_preset == real

    settings.default_preset = demo
    with pytest.raises(ValidationError, match="datos reales"):
        settings.save()


@pytest.mark.django_db
def test_system_preset_is_protected_and_database_enforces_scope():
    preset = DashboardPreset.objects.get(slug=DashboardPreset.SYSTEM_ALL_SLUG)
    preset.name = "Alterado"
    with pytest.raises(ValidationError, match="no se pueden modificar"):
        preset.save()
    with pytest.raises(ValidationError, match="no se pueden eliminar"):
        preset.delete()

    with pytest.raises(IntegrityError), transaction.atomic():
        DashboardPreset.objects.filter(pk=preset.pk).update(data_scope=Provider.DataScope.DEMO)


@pytest.mark.django_db
def test_explicit_preset_rejects_plan_outside_selected_providers():
    selected = Provider.objects.create(name="Seleccionado", code="selected")
    outside = Provider.objects.create(name="Fuera", code="outside")
    plan = MarketPlan.objects.create(
        provider=outside,
        external_key="outside-plan",
        first_seen_at="2026-01-01T00:00:00Z",
        last_seen_at="2026-01-01T00:00:00Z",
    )
    preset = DashboardPreset.objects.create(
        name="Directo",
        slug="directo",
        plan_selection=DashboardPreset.PlanSelection.EXPLICIT,
    )
    DashboardPresetProvider.objects.create(preset=preset, provider=selected)

    with pytest.raises(ValidationError, match="competidor incluido"):
        DashboardPresetPlan.objects.create(preset=preset, plan=plan)


@pytest.mark.django_db
def test_brand_image_validates_content_mime_dimensions_and_alt_text():
    valid = SimpleUploadedFile("brand.png", PNG_1X1, content_type="image/png")
    settings = DashboardSettings(header_image=valid, header_image_alt="Marca de prueba")
    settings.full_clean()

    invalid = SimpleUploadedFile("brand.png", b"<script>alert(1)</script>", "image/png")
    settings.header_image = invalid
    with pytest.raises(ValidationError, match="PNG, JPEG, WebP o SVG"):
        settings.full_clean()

    settings.header_image = SimpleUploadedFile("brand.png", PNG_1X1, content_type="image/png")
    settings.header_image_alt = ""
    with pytest.raises(ValidationError, match="tecnologías de asistencia"):
        settings.full_clean()


@pytest.mark.parametrize(
    ("name", "content_type", "content"),
    (
        ("marca.png", "image/png", PNG_1X1),
        (
            "marca.jpg",
            "image/jpeg",
            b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00",
        ),
        (
            "marca.webp",
            "image/webp",
            b"RIFF\x16\x00\x00\x00WEBPVP8X\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
        ),
        ("marca.svg", "image/svg+xml", SVG_VALID),
    ),
)
def test_brand_image_accepts_supported_raster_and_svg(name, content_type, content):
    from apps.market.validators import validate_brand_image

    upload = SimpleUploadedFile(name, content, content_type=content_type)
    validate_brand_image(upload)


def test_svg_is_sanitized_before_storage():
    from apps.market.validators import validate_brand_image

    unsafe = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 32">
    <script>alert(1)</script><a href="javascript:alert(1)"><text>Enlace</text></a>
    <image href="https://invalid.example/logo.png"/>
    <rect width="64" height="32" onclick="alert(1)"
    fill="url(https://invalid.example/fill)"/></svg>"""
    upload = SimpleUploadedFile("marca.svg", unsafe, content_type="image/svg+xml")

    validate_brand_image(upload)

    sanitized = upload.read().decode()
    assert "script" not in sanitized
    assert "onclick" not in sanitized
    assert "javascript:" not in sanitized
    assert "https://" not in sanitized
    assert "<ns0:image" not in sanitized
    assert "url(" not in sanitized


@pytest.mark.parametrize(
    "payload",
    (
        b"""<!DOCTYPE svg [<!ENTITY ext SYSTEM "file:///etc/passwd">]>
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">
        <text>&ext;</text></svg>""",
        b"""<svg xmlns="http://www.w3.org/2000/svg"><rect></svg>""",
    ),
)
def test_svg_rejects_entities_and_invalid_xml(payload):
    from apps.market.validators import validate_brand_image

    upload = SimpleUploadedFile("marca.svg", payload, content_type="image/svg+xml")
    with pytest.raises(ValidationError):
        validate_brand_image(upload)


@pytest.mark.django_db(transaction=True)
def test_demo_data_seed_is_idempotent_anonymous_and_safely_reversible():
    migration = importlib.import_module("apps.market.migrations.0007_seed_dashboard_demo_data")
    real = Provider.objects.create(name="Mercado real", code="real-preserved")

    migration.remove_demo(apps, None)

    assert Provider.objects.filter(pk=real.pk, data_scope=Provider.DataScope.REAL).exists()
    assert not Provider.objects.filter(data_scope=Provider.DataScope.DEMO).exists()

    migration.seed_demo(apps, None)
    migration.seed_demo(apps, None)

    demo_providers = Provider.objects.filter(data_scope=Provider.DataScope.DEMO)
    assert demo_providers.count() == 4
    assert set(demo_providers.values_list("name", flat=True)) == {
        "Producto Demo",
        "Competidor Demo Alfa",
        "Competidor Demo Beta",
        "Competidor Demo Gamma",
    }
    assert all(code.startswith("demo_") for code in demo_providers.values_list("code", flat=True))
    assert MarketPlan.objects.filter(provider__data_scope=Provider.DataScope.DEMO).count() == 15
    assert PlanSnapshot.objects.filter(market_plan__provider__data_scope="demo").count() == 90
    assert (
        PlanFeatureValue.objects.filter(
            plan_snapshot__market_plan__provider__data_scope="demo"
        ).count()
        == 90
    )
    assert ReviewSnapshot.objects.filter(market_review__provider__data_scope="demo").count() == 59
    assert (
        PipelineRun.objects.filter(metadata_json__synthetic_dataset="dashboard_demo_v1").count()
        == 6
    )
