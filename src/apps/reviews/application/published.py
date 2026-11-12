from __future__ import annotations

from datetime import timedelta

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.market.dashboard_service import PERIOD_DAYS, DashboardSelection
from apps.pipeline.application.queries import latest_published_provider_runs
from apps.pipeline.models import ReviewSnapshot


def published_reviews(
    selection: DashboardSelection, filters: dict | None = None
) -> QuerySet[ReviewSnapshot]:
    filters = filters or {}
    provider_ids = [provider.id for provider in selection.providers]
    current_runs = latest_published_provider_runs(data_scope=selection.scope).filter(
        provider_id__in=provider_ids
    )
    cutoff = timezone.now() - timedelta(days=PERIOD_DAYS[selection.period_months])
    queryset = (
        ReviewSnapshot.objects.filter(
            provider_run_id__in=current_runs.values("id"),
            market_review__provider_id__in=provider_ids,
            market_review__is_active=True,
        )
        .filter(
            Q(review_published_at__gte=cutoff)
            | Q(review_published_at__isnull=True, ingested_at__gte=cutoff)
        )
        .select_related(
            "market_review",
            "market_review__provider",
            "provider_run__provider",
            "source_run__market_source",
        )
        .order_by("-review_published_at", "-ingested_at", "-id")
    )
    if value := filters.get("plataforma"):
        queryset = queryset.filter(market_review__platform_code=value)
    if value := filters.get("pais"):
        queryset = queryset.filter(country_code=value.upper())
    if value := filters.get("estrellas"):
        queryset = queryset.filter(rating_stars=value)
    if value := filters.get("desde"):
        queryset = queryset.filter(
            Q(review_published_at__date__gte=value)
            | Q(review_published_at__isnull=True, ingested_at__date__gte=value)
        )
    if value := filters.get("hasta"):
        queryset = queryset.filter(
            Q(review_published_at__date__lte=value)
            | Q(review_published_at__isnull=True, ingested_at__date__lte=value)
        )
    if value := filters.get("respuesta"):
        queryset = queryset.filter(has_developer_response=value == "true")
    if value := filters.get("sentimiento"):
        queryset = queryset.filter(sentiment_from_rating=value)
    if value := filters.get("q"):
        queryset = queryset.filter(
            Q(user_name__icontains=value)
            | Q(customer_comment__icontains=value)
            | Q(developer_response__icontains=value)
        )
    return queryset


def review_source_label(snapshot: ReviewSnapshot) -> str:
    if snapshot.source_run_id and snapshot.source_run.market_source_id:
        return snapshot.source_run.market_source.name
    return snapshot.market_review.platform_code.replace("_", " ").title()


def sentiment_label(value: str | None) -> str:
    return {
        "positive": "Positivo",
        "neutral": "Neutral",
        "negative": "Negativo",
    }.get(value, "Sin clasificar")
