import csv
import io
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.db import connection
from django.http import QueryDict
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.market.dashboard_service import resolve_dashboard_selection
from apps.market.models import Provider
from apps.pipeline.models import (
    MarketReview as PipelineMarketReview,
)
from apps.pipeline.models import (
    PipelineProfile,
    PipelineProfileVersion,
    PipelineRun,
    ProviderRun,
    ReviewSnapshot,
)
from apps.reviews.application.export import (
    REVIEW_EXPORT_COLUMNS,
    export_reviews_csv,
)
from apps.reviews.application.published import published_reviews
from apps.reviews.models import ManualReviewRequest, ReviewSource


@pytest.fixture
def review_data(db):
    provider = Provider.objects.create(name="Contífico", code="siigo_contifico")
    source = ReviewSource.objects.create(
        provider=provider,
        name="Google Play Ecuador",
        platform=ReviewSource.Platform.GOOGLE_PLAY,
        adapter_key="fixture_app_reviews",
        source_url="https://example.test/app",
        country_code="EC",
        enabled=True,
        adapter_config={"fixture_reviews": []},
    )
    profile = PipelineProfile.objects.create(code=f"reviews-{uuid4()}", name="Reseñas")
    version = PipelineProfileVersion.objects.create(profile=profile, version=1)
    now = timezone.now()
    run = PipelineRun.objects.create(
        profile_version=version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        status=PipelineRun.Status.PUBLISHED,
        started_at=now,
        finished_at=now,
        published_at=now,
    )
    provider_run = ProviderRun.objects.create(
        pipeline_run=run,
        provider=provider,
        sequence=1,
        status=PipelineRun.Status.PUBLISHED,
        started_at=now,
        finished_at=now,
        published_at=now,
        is_complete=True,
    )
    market_review = PipelineMarketReview.objects.create(
        provider=provider,
        platform_code="google_play",
        external_review_id="review-1",
        first_seen_at=now,
        last_seen_at=now,
    )
    review = ReviewSnapshot.objects.create(
        market_review=market_review,
        provider_run=provider_run,
        country_code="EC",
        user_name="Ana",
        rating_stars=5,
        customer_comment='Texto con, coma, "comillas"\ny salto 🚀',
        has_developer_response=True,
        developer_response="Gracias, Ana",
        ingested_at=now,
        review_published_at=now,
        response_published_at=now,
        sentiment_from_rating="positive",
        days_to_respond=Decimal("0.78125"),
        content_sha256="a" * 64,
    )
    return provider, source, review


@pytest.mark.django_db
def test_csv_has_exact_columns_round_trips_and_uses_provider_code(review_data):
    selection = resolve_dashboard_selection(QueryDict("provider=siigo_contifico"))
    text = export_reviews_csv(published_reviews(selection))
    rows = list(csv.DictReader(io.StringIO(text)))
    assert tuple(rows[0]) == REVIEW_EXPORT_COLUMNS
    assert len(rows[0]) == 18
    assert rows[0]["competidor_id"] == "siigo_contifico"
    assert rows[0]["comentario_cliente"] == 'Texto con, coma, "comillas"\ny salto 🚀'
    assert rows[0]["tiene_respuesta"] == "TRUE"
    assert rows[0]["dias_para_responder"] == "0.78"
    assert rows[0]["categoria_tema"] == ""
    assert rows[0]["sentimiento"] == "positive"


@pytest.mark.django_db
def test_export_filters_and_json_equivalent(client, django_user_model, review_data):
    user = django_user_model.objects.create_user("analyst@example.test", "password")
    user.user_permissions.add(Permission.objects.get(codename="export_reviews"))
    client.force_login(user)
    response = client.get(reverse("reviews:export_json"), {"competidor": "siigo_contifico"})
    assert response.status_code == 200
    data = json.loads(response.content)
    row = next(item for item in data if item["competidor_id"] == "siigo_contifico")
    assert len(row) == 18


@pytest.mark.django_db
def test_export_queryset_excludes_demo_reviews(review_data):
    selection = resolve_dashboard_selection(QueryDict("preset=all"))
    assert (
        not published_reviews(selection)
        .filter(market_review__provider__data_scope=Provider.DataScope.DEMO)
        .exists()
    )


@pytest.mark.django_db
def test_list_requires_login_and_permission(client, django_user_model, review_data):
    url = reverse("reviews:list")
    assert client.get(url).status_code == 302
    user = django_user_model.objects.create_user("reader@example.test", "password")
    client.force_login(user)
    assert client.get(url).status_code == 403
    user.user_permissions.add(Permission.objects.get(codename="view_marketreview"))
    response = client.get(url)
    assert response.status_code == 200
    assert "Texto con, coma" in response.content.decode()
    assert "Contífico" in response.content.decode()


@pytest.mark.django_db
def test_review_pages_use_only_current_pipeline_tables_and_support_detail(
    client, django_user_model, review_data
):
    _provider, _source, review = review_data
    user = django_user_model.objects.create_user("pipeline-reader@example.test", "password")
    user.user_permissions.add(Permission.objects.get(codename="view_marketreview"))
    client.force_login(user)

    with CaptureQueriesContext(connection) as captured:
        response = client.get(reverse("reviews:list"), {"provider": "siigo_contifico"})
    sql = "\n".join(item["sql"] for item in captured.captured_queries).lower()

    assert response.status_code == 200
    assert "reviews_marketreview" not in sql
    assert "reviews_reviewobservation" not in sql
    detail = client.get(reverse("reviews:detail", args=(review.id,)))
    assert detail.status_code == 200
    assert "Gracias, Ana" in detail.content.decode()
    assert "Positivo" in detail.content.decode()


@pytest.mark.django_db
def test_review_filters_normalize_forged_provider_without_server_error(
    client, django_user_model, review_data
):
    user = django_user_model.objects.create_user("filter-reader@example.test", "password")
    user.user_permissions.add(Permission.objects.get(codename="view_marketreview"))
    client.force_login(user)

    response = client.get(reverse("reviews:list"), {"provider": "forged"})

    assert response.status_code == 302
    assert response.url.startswith("/reviews/?preset=all&period=6")


@pytest.mark.django_db
def test_legacy_manual_action_is_hidden(client, django_user_model, review_data):
    _, source, _review = review_data
    user = django_user_model.objects.create_user("operator@example.test", "password")
    user.user_permissions.add(Permission.objects.get(codename="run_reviews"))
    client.force_login(user)
    response = client.post(reverse("reviews:request_source", args=(source.id,)))
    assert response.status_code == 404
    assert not ManualReviewRequest.objects.exists()
