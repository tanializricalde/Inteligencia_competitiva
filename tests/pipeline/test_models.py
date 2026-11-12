import json
from pathlib import Path

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.market.models import Provider
from apps.pipeline.models import (
    FeatureDefinition,
    MarketPlan,
    PipelineConfig,
    PipelineConfigVersion,
    PipelineProfile,
    PipelineProfileStage,
    PipelineProfileVersion,
    PipelineRun,
    PlanFeatureValue,
    PlanSnapshot,
    ProviderRun,
    RunArtifact,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.django_db
def test_feature_rules_config_is_validated_hashed_and_immutable():
    content = json.loads(
        (ROOT / "feature_rules/feature-equivalence.example.json").read_text(encoding="utf-8")
    )
    config = PipelineConfig.objects.create(
        code="feature-equivalence",
        stage=PipelineConfig.Stage.FEATURE_EQUIVALENCE,
    )
    version = PipelineConfigVersion.objects.create(
        pipeline_config=config,
        version=1,
        content_json=content,
        status=PipelineConfigVersion.Status.PUBLISHED,
    )

    assert len(version.content_sha256) == 64
    assert version.published_at is not None

    changed_content = json.loads(json.dumps(content))
    changed_content["behavior"]["unmatched"]["prefix"] = "dinamica_"
    version.content_json = changed_content
    with pytest.raises(ValidationError, match="inmutable"):
        version.save()


@pytest.mark.django_db
def test_config_rejects_secrets_recursively():
    config = PipelineConfig.objects.create(code="extraction", stage=PipelineConfig.Stage.EXTRACTION)
    version = PipelineConfigVersion(
        pipeline_config=config,
        version=1,
        content_json={"provider": {"token": "not-allowed"}},
    )

    with pytest.raises(ValidationError, match="secretos"):
        version.save()


@pytest.mark.django_db
def test_published_profile_cannot_gain_or_change_stages():
    config = PipelineConfig.objects.create(code="cleaning", stage=PipelineConfig.Stage.CLEANING)
    config_version = PipelineConfigVersion.objects.create(
        pipeline_config=config,
        version=1,
        content_json={"schema_version": 1},
        status=PipelineConfigVersion.Status.PUBLISHED,
    )
    profile = PipelineProfile.objects.create(code="nightly", name="Nocturno")
    profile_version = PipelineProfileVersion.objects.create(
        profile=profile,
        version=1,
        status=PipelineProfileVersion.Status.PUBLISHED,
    )

    stage = PipelineProfileStage(
        profile_version=profile_version,
        stage=PipelineConfig.Stage.CLEANING,
        config_version=config_version,
        execution_order=1,
    )
    with pytest.raises(ValidationError, match="inmutables"):
        stage.save()


@pytest.mark.django_db
def test_feature_scope_and_typed_value_are_enforced():
    provider = Provider.objects.create(name="Proveedor", code="provider")
    invalid_definition = FeatureDefinition(
        code="usuarios",
        display_name="Usuarios",
        data_type=FeatureDefinition.DataType.INTEGER,
        scope=FeatureDefinition.Scope.PROVIDER,
        origin=FeatureDefinition.Origin.FALLBACK,
    )
    with pytest.raises(ValidationError, match="requiere proveedor"):
        invalid_definition.full_clean()

    definition = FeatureDefinition.objects.create(
        code="usuarios",
        display_name="Usuarios",
        data_type=FeatureDefinition.DataType.INTEGER,
        scope=FeatureDefinition.Scope.CANONICAL,
        origin=FeatureDefinition.Origin.CONFIGURED,
    )
    snapshot = _plan_snapshot(provider)
    invalid_value = PlanFeatureValue(
        plan_snapshot=snapshot,
        feature_definition=definition,
        value_integer=2,
        value_text="dos",
        availability=PlanFeatureValue.Availability.PRESENT,
        origin=PlanFeatureValue.Origin.RULE,
    )
    with pytest.raises(ValidationError, match="Sólo una columna"):
        invalid_value.full_clean()

    with pytest.raises(IntegrityError), transaction.atomic():
        PlanFeatureValue.objects.create(
            plan_snapshot=snapshot,
            feature_definition=definition,
            value_integer=2,
            value_text="dos",
            availability=PlanFeatureValue.Availability.PRESENT,
            origin=PlanFeatureValue.Origin.RULE,
        )


@pytest.mark.django_db
def test_artifact_path_rejects_absolute_and_traversal_paths():
    provider = Provider.objects.create(name="Proveedor", code="artifact-provider")
    run = _plan_snapshot(provider).provider_run.pipeline_run

    for path in ("/tmp/data.csv", "../outside.csv", r"windows\outside.csv"):
        artifact = RunArtifact(
            pipeline_run=run,
            artifact_type=RunArtifact.ArtifactType.NORMALIZED,
            relative_path=path,
            content_sha256="a" * 64,
            size_bytes=1,
        )
        with pytest.raises(ValidationError):
            artifact.full_clean()


@pytest.mark.django_db
def test_catalog_objects_have_readable_labels_without_n_plus_one(django_assert_num_queries):
    provider = Provider.objects.create(name="Competidor legible", code="readable")
    MarketPlan.objects.bulk_create(
        [
            MarketPlan(
                provider=provider,
                external_key=f"plan-{index}",
                first_seen_at=timezone.now(),
                last_seen_at=timezone.now(),
            )
            for index in range(3)
        ]
    )

    with django_assert_num_queries(1):
        labels = [
            str(plan)
            for plan in MarketPlan.objects.filter(provider=provider).select_related("provider")
        ]

    assert labels == [
        "Competidor legible · plan-0",
        "Competidor legible · plan-1",
        "Competidor legible · plan-2",
    ]
    project_apps = {"market", "pipeline", "scraping", "reviews", "notifications"}
    missing = [
        model._meta.label
        for model in apps.get_models()
        if model._meta.app_label in project_apps and model.__str__ is models.Model.__str__
    ]
    assert missing == []


def _plan_snapshot(provider: Provider) -> PlanSnapshot:
    profile = PipelineProfile.objects.create(
        code=f"profile-{provider.code}", name="Perfil de prueba"
    )
    profile_version = PipelineProfileVersion.objects.create(profile=profile, version=1)
    pipeline_run = PipelineRun.objects.create(
        profile_version=profile_version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
    )
    provider_run = ProviderRun.objects.create(
        pipeline_run=pipeline_run,
        provider=provider,
        sequence=1,
    )
    plan = MarketPlan.objects.create(
        provider=provider,
        external_key="plan-1",
        first_seen_at=timezone.now(),
        last_seen_at=timezone.now(),
    )
    return PlanSnapshot.objects.create(
        market_plan=plan,
        provider_run=provider_run,
        observed_at=timezone.now(),
        plan_name="Plan 1",
    )
