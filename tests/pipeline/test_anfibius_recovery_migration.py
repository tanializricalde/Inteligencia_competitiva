import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.pipeline.application.queries import latest_published_provider_runs

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    ROOT / "src" / "apps" / "pipeline" / "migrations" / "fixtures" / "anfibius_recovery_v1.json"
)
RUN_ID = uuid.uuid5(uuid.NAMESPACE_URL, "anfibius_recovery_v1")


def test_anfibius_recovery_fixture_is_traceable_scoped_and_sanitized():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert payload["_meta"]["provider_code"] == "anfibius"
    assert payload["_meta"]["counts"] == {
        "plans": 3,
        "feature_sources": 15,
        "feature_values": 186,
        "reviews": 50,
    }
    assert all(plan["monthly_price"] is None for plan in payload["plans"])
    assert all(plan["annual_price"] is None for plan in payload["plans"])
    safe_review_fields = {
        "external_id",
        "platform_code",
        "country_code",
        "rating_stars",
        "has_developer_response",
        "ingested_at",
        "sentiment_from_rating",
    }
    assert all(set(review) == safe_review_fields for review in payload["reviews"])
    assert [review["rating_stars"] for review in payload["reviews"]].count(5) == 43
    assert [review["rating_stars"] for review in payload["reviews"]].count(4) == 5
    assert [review["rating_stars"] for review in payload["reviews"]].count(3) == 2
    for filename, expected_hash in payload["_meta"]["source_files"].items():
        assert hashlib.sha256(
            (ROOT / "data" / "normalized" / filename).read_bytes()
        ).hexdigest() == (expected_hash)


@pytest.mark.django_db(transaction=True)
def test_anfibius_recovery_migration_is_real_reversible_and_does_not_replace_newer_data():
    previous_target = [
        ("market", "0008_application_branding"),
        ("pipeline", "0002_alter_marketreview_options_and_more"),
    ]
    current_target = [
        ("market", "0008_application_branding"),
        ("pipeline", "0003_seed_anfibius_recovery_snapshot"),
    ]
    executor = MigrationExecutor(connection)
    executor.migrate(previous_target)
    previous_apps = executor.loader.project_state(previous_target).apps
    Provider = previous_apps.get_model("market", "Provider")
    PipelineProfile = previous_apps.get_model("pipeline", "PipelineProfile")
    PipelineProfileVersion = previous_apps.get_model("pipeline", "PipelineProfileVersion")
    PipelineRun = previous_apps.get_model("pipeline", "PipelineRun")
    ProviderRun = previous_apps.get_model("pipeline", "ProviderRun")

    provider, _ = Provider.objects.update_or_create(
        code="anfibius",
        defaults={
            "name": "Nombre personalizado",
            "data_scope": "real",
            "is_active": False,
        },
    )
    profile = PipelineProfile.objects.create(code="newer-profile", name="Más reciente")
    version = PipelineProfileVersion.objects.create(
        profile=profile,
        version=1,
        status="published",
        published_at=datetime(2026, 10, 10, tzinfo=UTC),
    )
    newer_run = PipelineRun.objects.create(
        profile_version=version,
        trigger_type="reprocess",
        status="published",
        started_at=datetime(2026, 10, 10, tzinfo=UTC),
        finished_at=datetime(2026, 10, 10, tzinfo=UTC),
        published_at=datetime(2026, 10, 10, tzinfo=UTC),
    )
    ProviderRun.objects.create(
        pipeline_run=newer_run,
        provider=provider,
        sequence=1,
        status="published",
        is_complete=True,
        published_at=datetime(2026, 10, 10, tzinfo=UTC),
    )

    try:
        executor = MigrationExecutor(connection)
        executor.migrate(current_target)
        current_apps = executor.loader.project_state(current_target).apps
        CurrentProvider = current_apps.get_model("market", "Provider")
        CurrentPipelineRun = current_apps.get_model("pipeline", "PipelineRun")
        PlanSnapshot = current_apps.get_model("pipeline", "PlanSnapshot")
        PlanPriceSnapshot = current_apps.get_model("pipeline", "PlanPriceSnapshot")
        PlanFeatureSource = current_apps.get_model("pipeline", "PlanFeatureSource")
        PlanFeatureValue = current_apps.get_model("pipeline", "PlanFeatureValue")
        ReviewSnapshot = current_apps.get_model("pipeline", "ReviewSnapshot")
        recovery = CurrentPipelineRun.objects.get(id=RUN_ID)
        recovery_provider_run = recovery.provider_runs.get(provider__code="anfibius")
        migrated_provider = CurrentProvider.objects.get(code="anfibius")
        assert migrated_provider.name == "Nombre personalizado"
        assert migrated_provider.data_scope == "real"
        assert migrated_provider.is_active is True
        assert recovery.status == "published"
        assert recovery_provider_run.status == "published"
        assert list(recovery_provider_run.stage_runs.values_list("stage", "status")) == [
            ("plans", "succeeded"),
            ("features", "succeeded"),
            ("reviews", "succeeded"),
        ]
        assert PlanSnapshot.objects.filter(provider_run=recovery_provider_run).count() == 3
        assert (
            PlanPriceSnapshot.objects.filter(
                plan_snapshot__provider_run=recovery_provider_run
            ).count()
            == 0
        )
        assert (
            PlanFeatureSource.objects.filter(
                plan_snapshot__provider_run=recovery_provider_run
            ).count()
            == 15
        )
        assert (
            PlanFeatureValue.objects.filter(
                plan_snapshot__provider_run=recovery_provider_run
            ).count()
            == 186
        )
        reviews = ReviewSnapshot.objects.filter(provider_run=recovery_provider_run)
        assert reviews.count() == 50
        assert not reviews.exclude(
            user_name__isnull=True,
            customer_comment__isnull=True,
            developer_response__isnull=True,
        ).exists()
        assert (
            latest_published_provider_runs().get(provider__code="anfibius").pipeline_run_id
            == newer_run.id
        )

        executor = MigrationExecutor(connection)
        executor.migrate(previous_target)
        reverted_apps = executor.loader.project_state(previous_target).apps
        RevertedPipelineRun = reverted_apps.get_model("pipeline", "PipelineRun")
        RevertedMarketPlan = reverted_apps.get_model("pipeline", "MarketPlan")
        RevertedMarketReview = reverted_apps.get_model("pipeline", "MarketReview")
        assert not RevertedPipelineRun.objects.filter(id=RUN_ID).exists()
        assert RevertedPipelineRun.objects.filter(id=newer_run.id).exists()
        assert not RevertedMarketPlan.objects.filter(provider__code="anfibius").exists()
        assert not RevertedMarketReview.objects.filter(
            provider__code="anfibius",
            external_review_id__startswith="anfibius-recovery-review-",
        ).exists()
    finally:
        MigrationExecutor(connection).migrate(current_target)
