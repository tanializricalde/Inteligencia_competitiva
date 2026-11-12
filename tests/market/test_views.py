import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from apps.market.models import Provider
from apps.notifications.models import NotificationRecipient
from apps.pipeline.models import (
    MarketSource,
    PipelineProfile,
    PipelineProfileVersion,
    PipelineRun,
    ProviderRun,
    SourceRun,
    StageRun,
)
from apps.reviews.models import ManualReviewRequest, ReviewRun, ReviewScheduleConfig, ReviewSource
from apps.scraping.models import (
    ManualScrapeRequest,
    ScheduleConfig,
    ScrapeRun,
    ScrapeSource,
    ScrapeSourceResult,
)


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("analyst@example.test", "password")


@pytest.mark.django_db
def test_dashboard_requires_login(client):
    response = client.get(reverse("dashboard"))

    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_authenticated_dashboard_renders(client, user):
    client.force_login(user)

    response = client.get(reverse("dashboard"))

    assert response.status_code == 200
    assert "Dashboard de inteligencia competitiva" in response.content.decode()


@pytest.mark.django_db
def test_legacy_sources_are_hidden_server_side(client, user):
    client.force_login(user)

    assert client.get(reverse("sources")).status_code == 404


@pytest.mark.django_db
def test_legacy_ingestion_is_absent_from_navigation_and_admin(client, django_user_model):
    administrator = django_user_model.objects.create_superuser("legacy-admin@example.test", "pass")
    client.force_login(administrator)

    content = client.get(reverse("dashboard")).content.decode()
    assert "Fuentes heredadas" not in content
    assert "Ejecuciones heredadas" not in content
    assert "Fuentes de reseñas" not in content
    assert "Pipeline de mercado" in content

    hidden_models = {
        ScrapeSource,
        ScrapeRun,
        ScrapeSourceResult,
        ManualScrapeRequest,
        ScheduleConfig,
        ReviewSource,
        ReviewRun,
        ManualReviewRequest,
        ReviewScheduleConfig,
    }
    assert hidden_models.isdisjoint(admin.site._registry)


@pytest.mark.django_db
def test_legacy_manual_request_is_not_available(client, user):
    user.user_permissions.add(Permission.objects.get(codename="run_scrape"))
    user.user_permissions.add(Permission.objects.get(codename="view_scrapesource"))
    provider = Provider.objects.create(name="Provider", code="provider")
    source = ScrapeSource.objects.create(
        provider=provider,
        name="Plans",
        target_url="https://example.test/plans",
        adapter_key="example_httpx",
    )
    client.force_login(user)

    response = client.post(reverse("request_scrape", args=(source.id,)))

    assert response.status_code == 404
    assert not ManualScrapeRequest.objects.exists()


@pytest.mark.django_db
def test_manual_pipeline_request_is_queued_without_running(client, user):
    profile = PipelineProfile.objects.create(code="nightly-market", name="Nocturno")
    version = PipelineProfileVersion.objects.create(
        profile=profile,
        version=1,
        status=PipelineProfileVersion.Status.PUBLISHED,
    )
    profile.active_version = version
    profile.save(update_fields=("active_version",))
    user.user_permissions.add(
        Permission.objects.get(codename="add_pipelinerun"),
        Permission.objects.get(codename="view_pipelinerun"),
    )
    client.force_login(user)

    response = client.post(reverse("request_pipeline_run"))

    assert response.status_code == 302
    run = PipelineRun.objects.get(requested_by=user)
    assert run.status == PipelineRun.Status.PENDING
    assert run.requested_by == user
    page = client.get(reverse("pipeline_runs"))
    assert page.status_code == 200
    assert str(run.id) in page.content.decode()


@pytest.mark.django_db
def test_pipeline_run_shows_expandable_full_provider_error(client, user):
    profile = PipelineProfile.objects.create(code="diagnostic", name="Diagnóstico")
    version = PipelineProfileVersion.objects.create(profile=profile, version=1)
    run = PipelineRun.objects.create(
        profile_version=version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        status=PipelineRun.Status.FAILED,
        started_at=timezone.now(),
    )
    provider = Provider.objects.create(name="Anfibius", code="anfibius-diagnostic")
    provider_run = ProviderRun.objects.create(
        pipeline_run=run,
        provider=provider,
        sequence=1,
        status=PipelineRun.Status.FAILED,
    )
    stage_run = StageRun.objects.create(
        provider_run=provider_run,
        stage=StageRun.Stage.PLANS,
        sequence=1,
        status=StageRun.Status.FAILED,
    )
    source = MarketSource.objects.create(
        provider=provider,
        code="anfibius-plans",
        name="Planes Anfibius",
        data_type=MarketSource.DataType.PLANS,
        adapter_key="anfibius_plans",
        url="https://example.test/plans",
    )
    SourceRun.objects.create(
        stage_run=stage_run,
        market_source=source,
        sequence=1,
        status=StageRun.Status.FAILED,
        error_type="StructureChangedError",
        error_message="detalle específico de la fuente",
    )
    detail = "plans/anfibius-plans: StructureChangedError: detalle específico de la fuente"
    user.user_permissions.add(Permission.objects.get(codename="view_pipelinerun"))
    client.force_login(user)

    response = client.get(reverse("pipeline_runs"))

    content = response.content.decode()
    assert response.status_code == 200
    assert "<details" in content
    assert detail in content


@pytest.mark.django_db
def test_recipient_configuration_requires_permissions(client, user):
    user.user_permissions.add(Permission.objects.get(codename="view_notificationrecipient"))
    user.user_permissions.add(Permission.objects.get(codename="add_notificationrecipient"))
    client.force_login(user)

    response = client.post(
        reverse("functional_settings"),
        {
            "kind": "recipient",
            "recipient-name": "Ops",
            "recipient-email": "ops@example.test",
            "recipient-is_active": "on",
            "recipient-notify_errors": "on",
            "recipient-notify_changes": "on",
            "recipient-notify_recovery": "on",
        },
    )

    assert response.status_code == 302
    assert NotificationRecipient.objects.filter(email="ops@example.test").exists()


@pytest.mark.django_db
def test_health_and_readiness_are_public_and_sanitized(client):
    assert client.get(reverse("health")).json() == {"status": "ok"}
    response = client.get(reverse("ready"))

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
