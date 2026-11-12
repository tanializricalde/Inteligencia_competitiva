from __future__ import annotations

from datetime import datetime

import pandas as pd
from django.db.models import Avg, Count, OuterRef, QuerySet, Subquery

from apps.pipeline.models import (
    PipelineRun,
    PlanFeatureValue,
    PlanPriceSnapshot,
    PlanSnapshot,
    ProviderRun,
    ReviewSnapshot,
)


def latest_published_provider_runs(
    *, at: datetime | None = None, data_scope: str = "real"
) -> QuerySet[ProviderRun]:
    candidates = ProviderRun.objects.filter(
        provider=OuterRef("provider"),
        provider__data_scope=data_scope,
        status="published",
        published_at__isnull=False,
    )
    if at is not None:
        candidates = candidates.filter(published_at__lte=at)
    latest_id = candidates.order_by("-published_at", "-id").values("id")[:1]
    queryset = ProviderRun.objects.filter(
        id=Subquery(latest_id), status="published", provider__data_scope=data_scope
    )
    return queryset.select_related("provider", "pipeline_run")


def latest_plan_snapshots(*, at: datetime | None = None) -> QuerySet[PlanSnapshot]:
    return (
        PlanSnapshot.objects.filter(provider_run__in=latest_published_provider_runs(at=at))
        .select_related("market_plan", "provider_run__provider")
        .prefetch_related("prices")
        .order_by("provider_run__provider__execution_order", "plan_name")
    )


def latest_review_snapshots(*, at: datetime | None = None) -> QuerySet[ReviewSnapshot]:
    return (
        ReviewSnapshot.objects.filter(provider_run__in=latest_published_provider_runs(at=at))
        .select_related("market_review", "provider_run__provider")
        .order_by("provider_run__provider__execution_order", "-ingested_at")
    )


def latest_feature_matrix(*, at: datetime | None = None) -> pd.DataFrame:
    values = (
        PlanFeatureValue.objects.filter(
            plan_snapshot__provider_run__in=latest_published_provider_runs(at=at)
        )
        .select_related(
            "feature_definition",
            "plan_snapshot__market_plan",
            "plan_snapshot__provider_run__provider",
        )
        .order_by(
            "plan_snapshot__provider_run__provider__execution_order",
            "plan_snapshot__market_plan__external_key",
            "feature_definition__code",
        )
    )
    typed_fields = {
        "boolean": "value_boolean",
        "integer": "value_integer",
        "decimal": "value_decimal",
        "string": "value_text",
        "string_list": "value_json",
    }
    records: dict[tuple[str, str], dict] = {}
    feature_order: list[str] = []
    for value in values:
        provider_code = value.plan_snapshot.provider_run.provider.code
        plan_id = value.plan_snapshot.market_plan.external_key
        key = (provider_code, plan_id)
        record = records.setdefault(
            key,
            {"competidor_id": provider_code, "plan_id": plan_id},
        )
        code = value.feature_definition.code
        if value.feature_definition.scope == "provider":
            code = f"{provider_code}__{code}"
        if code not in feature_order:
            feature_order.append(code)
        record[code] = getattr(value, typed_fields[value.feature_definition.data_type])
    return pd.DataFrame(records.values(), columns=["competidor_id", "plan_id", *feature_order])


def price_history(
    *, provider_codes: tuple[str, ...] = (), plan_ids: tuple[str, ...] = ()
) -> QuerySet[PlanPriceSnapshot]:
    queryset = PlanPriceSnapshot.objects.select_related(
        "plan_snapshot__market_plan",
        "plan_snapshot__provider_run__provider",
    ).order_by("plan_snapshot__observed_at", "id")
    if provider_codes:
        queryset = queryset.filter(plan_snapshot__provider_run__provider__code__in=provider_codes)
    if plan_ids:
        queryset = queryset.filter(plan_snapshot__market_plan__external_key__in=plan_ids)
    return queryset


def comparable_feature_values(
    *, plan_ids: tuple[str, ...], at: datetime | None = None
) -> QuerySet[PlanFeatureValue]:
    return (
        PlanFeatureValue.objects.filter(
            plan_snapshot__provider_run__in=latest_published_provider_runs(at=at),
            plan_snapshot__market_plan__external_key__in=plan_ids,
        )
        .select_related(
            "feature_definition",
            "plan_snapshot__market_plan",
            "plan_snapshot__provider_run__provider",
        )
        .order_by("feature_definition__code", "plan_snapshot__market_plan__external_key")
    )


def review_statistics(*, at: datetime | None = None):
    return (
        latest_review_snapshots(at=at)
        .values(
            "provider_run__provider__code",
            "market_review__platform_code",
            "sentiment_from_rating",
        )
        .annotate(review_count=Count("id"), average_rating=Avg("rating_stars"))
        .order_by(
            "provider_run__provider__code",
            "market_review__platform_code",
            "sentiment_from_rating",
        )
    )


def pipeline_run_statuses() -> QuerySet[PipelineRun]:
    return PipelineRun.objects.prefetch_related("provider_runs__stage_runs__source_runs").order_by(
        "-started_at", "-id"
    )
