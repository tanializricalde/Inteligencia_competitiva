import json
from pathlib import Path

import pytest

from apps.market.models import Provider
from apps.pipeline.application.orchestrator import PipelineOrchestrator
from apps.pipeline.infrastructure.artifacts import PipelineArtifactStore
from apps.pipeline.infrastructure.core_executor import DjangoCorePipelineExecutor
from apps.pipeline.models import (
    MarketSource,
    PipelineConfig,
    PipelineConfigVersion,
    PipelineProfile,
    PipelineProfileStage,
    PipelineProfileVersion,
    PipelineRun,
    PlanFeatureValue,
    PlanSnapshot,
    ReviewSnapshot,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.django_db
def test_core_executor_runs_fixture_cores_and_imports_without_cli_or_shell(tmp_path):
    provider = Provider.objects.create(name="Fixture", code="fixture-provider")
    profile_version = _profile_version()
    MarketSource.objects.create(
        provider=provider,
        code="fixture-plans",
        name="Planes fixture",
        data_type=MarketSource.DataType.PLANS,
        adapter_key="fixture_plans",
        url="https://example.test/plans",
        settings_json={
            "adapter_config": {
                "fixture_plans": [
                    {
                        "external_id": "plan-1",
                        "name": "Plan Uno",
                        "product": "contabilidad",
                        "monthly_price": "10.50",
                        "currency": "USD",
                        "periodicity": "monthly",
                        "features": {"soporte": {"state": "offered", "original": "Soporte"}},
                    }
                ]
            }
        },
    )
    MarketSource.objects.create(
        provider=provider,
        code="pipeline-features",
        name="Equivalencias",
        data_type=MarketSource.DataType.FEATURES,
        adapter_key=DjangoCorePipelineExecutor.FEATURE_ADAPTER_KEY,
        url="https://example.test/features",
    )
    MarketSource.objects.create(
        provider=provider,
        code="fixture-reviews",
        name="Reseñas fixture",
        data_type=MarketSource.DataType.REVIEWS,
        adapter_key="fixture_location_reviews",
        platform_code="google_maps",
        country_code="EC",
        url="https://example.test/reviews",
        settings_json={
            "adapter_config": {
                "fixture_reviews": [
                    {
                        "external_review_id": "review-1",
                        "author_name": "Cliente",
                        "rating": 5,
                        "review_text": "Excelente",
                        "published_at": "2026-10-01T00:00:00Z",
                    }
                ]
            }
        },
    )
    executor = DjangoCorePipelineExecutor(PipelineArtifactStore(tmp_path))

    run = PipelineOrchestrator(executor).execute(
        profile_version=profile_version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        providers=(provider,),
    )

    assert run.status == PipelineRun.Status.PUBLISHED
    assert PlanSnapshot.objects.filter(provider_run__pipeline_run=run).count() == 1
    assert (
        PlanFeatureValue.objects.filter(
            plan_snapshot__provider_run__pipeline_run=run,
            origin="fallback",
        ).count()
        == 1
    )
    assert ReviewSnapshot.objects.filter(provider_run__pipeline_run=run).count() == 1


def _profile_version() -> PipelineProfileVersion:
    config = PipelineConfig.objects.create(
        code="feature-rules-fixture",
        stage=PipelineConfig.Stage.FEATURE_EQUIVALENCE,
    )
    config_version = PipelineConfigVersion.objects.create(
        pipeline_config=config,
        version=1,
        content_json=json.loads(
            (ROOT / "feature_rules/feature-equivalence.example.json").read_text(encoding="utf-8")
        ),
        status=PipelineConfigVersion.Status.PUBLISHED,
    )
    profile = PipelineProfile.objects.create(code="fixture-profile", name="Fixture")
    profile_version = PipelineProfileVersion.objects.create(profile=profile, version=1)
    PipelineProfileStage.objects.create(
        profile_version=profile_version,
        stage=PipelineConfig.Stage.FEATURE_EQUIVALENCE,
        config_version=config_version,
        execution_order=1,
    )
    profile_version.status = PipelineProfileVersion.Status.PUBLISHED
    profile_version.save()
    profile.active_version = profile_version
    profile.full_clean()
    profile.save(update_fields=("active_version",))
    return profile_version
