import base64
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.core.files.storage import default_storage
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.market.models import (
    DashboardPreset,
    DashboardSettings,
    Provider,
)
from apps.pipeline.models import (
    FeatureDefinition,
    MarketPlan,
    PipelineProfile,
    PipelineProfileVersion,
    PipelineRun,
    PlanFeatureValue,
    PlanPriceSnapshot,
    PlanSnapshot,
    ProviderRun,
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
SVG_WITH_EVENT = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">
<rect width="16" height="16" fill="#2563eb" onclick="alert(1)"/></svg>"""


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("dashboard@example.test", "password")


@pytest.mark.django_db
def test_dashboard_renders_demo_warning_accessible_panels_and_safe_json(client, user):
    client.force_login(user)

    response = client.get(reverse("dashboard"), {"preset": "demo", "period": "6"})

    content = response.content.decode()
    assert response.status_code == 200
    assert "Datos demostrativos" in content
    assert 'aria-labelledby="heatmap-title"' in content
    assert 'class="card dashboard-panel dashboard-panel-wide"' in content
    assert "dashboard-disclosure" in content
    assert "data-sidebar-toggle" in content
    assert 'id="dashboard-data" type="application/json"' in content
    assert "SIIGO CONTIFICO" not in content
    assert "iDrix Contable" not in content


@pytest.mark.django_db
def test_applied_filters_collapse_controls_and_target_results(client, user):
    client.force_login(user)

    content = client.get(reverse("dashboard"), {"preset": "demo", "period": "6"}).content.decode()

    assert '<details class="card dashboard-disclosure mb-3">' in content
    assert 'action="/#dashboard-results"' in content
    assert 'id="dashboard-results" tabindex="-1"' in content


@pytest.mark.django_db
def test_dashboard_escapes_provider_names_inside_json_script(client, user):
    provider, _plan = _published_plan("safe-json")
    provider.name = "</script><script>alert(1)</script>"
    provider.save(update_fields=("name",))
    client.force_login(user)

    content = client.get(reverse("dashboard")).content.decode()

    assert "</script><script>alert(1)</script>" not in content
    assert "\\u003C/script\\u003E" in content


@pytest.mark.django_db
def test_dashboard_normalizes_invalid_or_cross_scope_url_parameters(client, user):
    client.force_login(user)
    demo_plan = MarketPlan.objects.filter(provider__data_scope=Provider.DataScope.DEMO).first()

    for params in (
        {"period": "999"},
        {"preset": "missing"},
        {"plan": demo_plan.id},
    ):
        response = client.get(reverse("dashboard"), params)

        assert response.status_code == 302
        assert response.url.startswith("/?preset=all&period=6")
        normalized = client.get(response.url)
        assert normalized.status_code == 200
        assert (
            "descart" in normalized.content.decode()
            or "no existe" in normalized.content.decode()
            or "periodo" in normalized.content.decode()
        )


@pytest.mark.django_db
def test_switching_all_demo_all_does_not_reuse_stale_plan_filters(client, user):
    provider, real_plan = _published_plan("filter-real")
    demo_plan = MarketPlan.objects.filter(provider__data_scope=Provider.DataScope.DEMO).first()
    client.force_login(user)

    demo_response = client.get(
        reverse("dashboard"),
        {"preset": "demo", "period": "6", "provider": provider.code, "plan": real_plan.id},
    )
    assert demo_response.status_code == 302
    assert demo_response.url == "/?preset=demo&period=6#dashboard-results"
    demo_page = client.get(demo_response.url)
    assert demo_page.status_code == 200
    assert str(demo_plan.id) in demo_page.content.decode()

    all_response = client.get(
        reverse("dashboard"),
        {"preset": "all", "period": "6", "plan": demo_plan.id},
    )
    assert all_response.status_code == 302
    assert all_response.url == "/?preset=all&period=6#dashboard-results"
    assert client.get(all_response.url).status_code == 200


@pytest.mark.django_db
def test_preset_management_requires_permission_csrf_and_preserves_relations(client, user):
    provider, plan = _published_plan("preset-provider")
    client.force_login(user)
    payload = {
        "name": "Competidor directo",
        "slug": "competidor-directo",
        "description": "Básico e intermedio",
        "plan_selection": DashboardPreset.PlanSelection.EXPLICIT,
        "is_active": "on",
        "providers": [provider.id],
        "plans": [plan.id],
    }

    assert client.post(reverse("dashboard_preset_save"), payload).status_code == 403
    user.user_permissions.add(Permission.objects.get(codename="add_dashboardpreset"))
    response = client.post(reverse("dashboard_preset_save"), payload)

    assert response.status_code == 302
    preset = DashboardPreset.objects.get(slug="competidor-directo")
    assert list(preset.providers.all()) == [provider]
    assert list(preset.plans.all()) == [plan]
    dashboard = client.get(reverse("dashboard")).content.decode()
    assert "Guardar una nueva vista" in dashboard
    assert "Actualizar" not in dashboard

    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(user)
    assert csrf_client.post(reverse("dashboard_preset_save"), payload).status_code == 403


@pytest.mark.django_db
def test_preset_saves_explicit_canonical_features_atomically(client, user):
    provider, plan = _published_plan("feature-preset-provider")
    definition = FeatureDefinition.objects.create(
        code="feature-preset-users",
        display_name="Usuarios",
        data_type=FeatureDefinition.DataType.INTEGER,
        scope=FeatureDefinition.Scope.CANONICAL,
        origin=FeatureDefinition.Origin.CONFIGURED,
    )
    PlanFeatureValue.objects.create(
        plan_snapshot=plan.snapshots.get(),
        feature_definition=definition,
        value_integer=5,
        availability="present",
        origin="rule",
    )
    user.user_permissions.add(Permission.objects.get(codename="add_dashboardpreset"))
    client.force_login(user)

    response = client.post(
        reverse("dashboard_preset_save"),
        {
            "name": "Funciones elegidas",
            "slug": "funciones-elegidas",
            "plan_selection": DashboardPreset.PlanSelection.EXPLICIT,
            "feature_selection": DashboardPreset.FeatureSelection.EXPLICIT,
            "is_active": "on",
            "providers": [provider.id],
            "plans": [plan.id],
            "features": [definition.id],
        },
    )

    assert response.status_code == 302
    preset = DashboardPreset.objects.get(slug="funciones-elegidas")
    assert list(preset.providers.all()) == [provider]
    assert list(preset.plans.all()) == [plan]
    assert list(preset.features.all()) == [definition]


@pytest.mark.django_db
def test_system_presets_cannot_be_edited_or_deleted_from_dashboard(client, user):
    user.user_permissions.add(
        Permission.objects.get(codename="change_dashboardpreset"),
        Permission.objects.get(codename="delete_dashboardpreset"),
    )
    client.force_login(user)
    system = DashboardPreset.objects.get(slug="all")

    assert client.post(reverse("dashboard_preset_delete", args=(system.id,))).status_code == 404


@pytest.mark.django_db
def test_branding_upload_is_stored_replaced_and_served_authenticated(
    client,
    user,
    settings,
    tmp_path,
    django_capture_on_commit_callbacks,
):
    settings.MEDIA_ROOT = tmp_path
    user.user_permissions.add(Permission.objects.get(codename="change_dashboardsettings"))
    client.force_login(user)
    all_preset = DashboardPreset.objects.get(slug="all")
    payload = {
        "application_name": "Radar de mercado",
        "header_title": "Radar competitivo",
        "header_image_alt": "Marca Radar",
        "default_preset": all_preset.id,
    }

    response = client.post(
        reverse("dashboard_settings"),
        {**payload, "header_image": _upload("first.png")},
    )
    configured = DashboardSettings.objects.get(pk=1)
    first_name = configured.header_image.name

    assert response.status_code == 302
    assert first_name.startswith("dashboard/branding/")
    assert "base64" not in first_name
    assert default_storage.exists(first_name)
    assert client.get(reverse("dashboard_brand_image")).status_code == 200

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("dashboard_settings"),
            {**payload, "header_image": _upload("second.png")},
        )

    configured.refresh_from_db()
    assert response.status_code == 302
    assert configured.header_image.name != first_name
    assert not default_storage.exists(first_name)
    anonymous = Client()
    assert anonymous.get(reverse("dashboard_brand_image")).status_code == 302


@pytest.mark.django_db
def test_application_branding_applies_to_login_navigation_dashboard_and_assets(
    client, user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    all_preset = DashboardPreset.objects.get(slug="all")
    user.user_permissions.add(Permission.objects.get(codename="change_dashboardsettings"))
    client.force_login(user)

    response = client.post(
        reverse("application_settings"),
        {
            "application_name": "Radar comercial",
            "application_logo": _upload("application.png"),
            "application_logo_alt": "Logo de Radar comercial",
            "header_title": "Panorama competitivo",
            "default_preset": all_preset.id,
        },
    )

    assert response.status_code == 302
    dashboard = client.get(reverse("dashboard")).content.decode()
    assert "Panorama competitivo · Radar comercial" in dashboard
    assert 'class="sidebar-brand-full"' in dashboard
    assert 'class="sidebar-brand-name">Radar comercial</span>' in dashboard
    assert "application/branding/application_logo/" in dashboard
    assert "Configuración de la aplicación" in dashboard
    assert " object (" not in dashboard
    client.logout()
    login = client.get(reverse("login")).content.decode()
    assert "Ingresar · Radar comercial" in login
    assert "application/branding/application_logo/" in login

    asset = client.get(reverse("application_brand_asset", args=("application_logo",)))
    assert asset.status_code == 200
    assert asset.headers["Content-Type"] == "image/png"
    assert asset.headers["X-Content-Type-Options"] == "nosniff"
    assert asset.headers["Cross-Origin-Resource-Policy"] == "same-origin"


@pytest.mark.django_db
def test_application_settings_menu_and_view_require_permission(client, user):
    client.force_login(user)

    assert client.get(reverse("application_settings")).status_code == 403
    assert "Configuración de la aplicación" not in client.get(reverse("dashboard")).content.decode()

    user.user_permissions.add(Permission.objects.get(codename="change_dashboardsettings"))
    assert client.get(reverse("application_settings")).status_code == 200
    assert "Configuración de la aplicación" in client.get(reverse("dashboard")).content.decode()


@pytest.mark.django_db
def test_application_name_is_used_by_django_admin(client, django_user_model):
    administrator = django_user_model.objects.create_superuser(
        "admin-brand@example.test", "password"
    )
    settings = DashboardSettings.load()
    settings.application_name = "Radar administrable"
    settings.save()
    client.force_login(administrator)

    content = client.get(reverse("admin:index")).content.decode()

    assert "Radar administrable" in content
    assert "Market Watch" not in content


@pytest.mark.django_db
def test_sanitized_svg_asset_is_stored_and_served_with_restrictive_headers(
    client, user, settings, tmp_path
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.MEDIA_ROOT = tmp_path
    user.user_permissions.add(Permission.objects.get(codename="change_dashboardsettings"))
    client.force_login(user)
    response = client.post(
        reverse("application_settings"),
        {
            "application_name": "Radar SVG",
            "application_logo": SimpleUploadedFile(
                "marca.svg", SVG_WITH_EVENT, content_type="image/svg+xml"
            ),
            "application_logo_alt": "Logo Radar SVG",
            "header_title": "Panel SVG",
        },
    )

    assert response.status_code == 302
    configured = DashboardSettings.objects.get(pk=1)
    with configured.application_logo.open("rb") as stored:
        assert b"onclick" not in stored.read()
    asset = client.get(reverse("application_brand_asset", args=("application_logo",)))
    assert asset.headers["Content-Type"] == "image/svg+xml"
    assert asset.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
    dashboard = client.get(reverse("dashboard")).content.decode()
    assert 'class="sidebar-brand-name">Radar SVG</span>' in dashboard
    assert 'alt="Logo Radar SVG"' in dashboard


@pytest.mark.django_db
def test_sidebar_uses_default_or_long_name_without_branding_edit_permission(client, user):
    client.force_login(user)
    default_page = client.get(reverse("dashboard")).content.decode()
    assert 'class="sidebar-brand-name">Market Watch</span>' in default_page

    configured = DashboardSettings.load()
    configured.application_name = "Observatorio competitivo regional de productos digitales"
    configured.save(update_fields=("application_name",))
    long_name_page = client.get(reverse("dashboard")).content.decode()

    assert "Observatorio competitivo regional de productos digitales" in long_name_page
    assert "Configuración de la aplicación" not in long_name_page


@pytest.mark.django_db
def test_ordinary_preset_rejects_demo_provider_even_with_forged_post(client, user):
    provider, plan = _published_plan("real-only")
    demo_provider = Provider.objects.filter(data_scope=Provider.DataScope.DEMO).first()
    user.user_permissions.add(Permission.objects.get(codename="add_dashboardpreset"))
    client.force_login(user)

    response = client.post(
        reverse("dashboard_preset_save"),
        {
            "name": "Mezcla inválida",
            "slug": "mixed-invalid",
            "plan_selection": DashboardPreset.PlanSelection.EXPLICIT,
            "is_active": "on",
            "providers": [provider.id, demo_provider.id],
            "plans": [plan.id],
        },
    )

    assert response.status_code == 400
    assert not DashboardPreset.objects.filter(slug="mixed-invalid").exists()


def _upload(name):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, PNG_1X1, content_type="image/png")


def _published_plan(code: str) -> tuple[Provider, MarketPlan]:
    provider = Provider.objects.create(name=f"Proveedor {code}", code=code)
    plan = MarketPlan.objects.create(
        provider=provider,
        external_key=f"{code}-basic",
        first_seen_at=timezone.now(),
        last_seen_at=timezone.now(),
    )
    profile = PipelineProfile.objects.create(code=f"profile-{uuid4()}", name="Perfil")
    version = PipelineProfileVersion.objects.create(profile=profile, version=1)
    run = PipelineRun.objects.create(
        profile_version=version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        status=PipelineRun.Status.PUBLISHED,
        started_at=timezone.now(),
        finished_at=timezone.now(),
        published_at=timezone.now(),
    )
    provider_run = ProviderRun.objects.create(
        pipeline_run=run,
        provider=provider,
        sequence=1,
        status=PipelineRun.Status.PUBLISHED,
        started_at=timezone.now(),
        finished_at=timezone.now(),
        published_at=timezone.now(),
        is_complete=True,
    )
    snapshot = PlanSnapshot.objects.create(
        market_plan=plan,
        provider_run=provider_run,
        observed_at=timezone.now(),
        plan_name="Plan básico",
    )
    PlanPriceSnapshot.objects.create(
        plan_snapshot=snapshot,
        billing_period="monthly",
        currency_code="USD",
        amount=Decimal("10.00"),
        effective_monthly_amount=Decimal("10.00"),
        source_kind="scraped",
    )
    return provider, plan
