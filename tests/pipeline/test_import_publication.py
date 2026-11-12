import json
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest
from django.utils import timezone

from apps.market.models import Provider
from apps.pipeline.application.importers import DatasetImportError, import_provider_datasets
from apps.pipeline.application.publication import PublicationError, publish_provider_run
from apps.pipeline.application.queries import (
    latest_feature_matrix,
    latest_plan_snapshots,
    latest_review_snapshots,
)
from apps.pipeline.infrastructure.artifacts import ArtifactStorageError, PipelineArtifactStore
from apps.pipeline.models import (
    FeatureDefinition,
    MarketPlan,
    MarketReview,
    PipelineProfile,
    PipelineProfileVersion,
    PipelineRun,
    PlanFeatureSource,
    PlanFeatureValue,
    PlanSnapshot,
    ProviderRun,
    ReviewSnapshot,
    RunArtifact,
    StageRun,
)
from data_pipeline.files import read_dataset
from data_transformation import transform_dataset
from data_transformation.feature_rules import load_feature_rules

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.django_db
def test_import_is_idempotent_and_preserves_new_observations():
    provider = Provider.objects.create(name="Proveedor", code="provider")
    first_run = _provider_run(provider)
    frames = _frames(first_run)

    first = import_provider_datasets(provider_run=first_run, **frames)
    second = import_provider_datasets(provider_run=first_run, **frames)

    assert first == second
    assert first.plans == 1
    assert first.feature_sources == 2
    assert first.feature_values == 2
    assert first.reviews == 1
    assert first.quality_issues == 1
    assert MarketPlan.objects.filter(provider=provider).count() == 1
    assert PlanSnapshot.objects.filter(provider_run=first_run).count() == 1
    assert PlanFeatureSource.objects.filter(plan_snapshot__provider_run=first_run).count() == 2
    assert PlanFeatureValue.objects.filter(plan_snapshot__provider_run=first_run).count() == 2
    assert MarketReview.objects.filter(provider=provider).count() == 1
    assert ReviewSnapshot.objects.filter(provider_run=first_run).count() == 1

    later_run = _provider_run(provider)
    import_provider_datasets(provider_run=later_run, **_frames(later_run))

    assert MarketPlan.objects.filter(provider=provider).count() == 1
    assert PlanSnapshot.objects.filter(market_plan__provider=provider).count() == 2
    assert MarketReview.objects.filter(provider=provider).count() == 1
    assert ReviewSnapshot.objects.filter(market_review__provider=provider).count() == 2


@pytest.mark.django_db
def test_import_accepts_binary_float_booleans_created_by_nullable_json_columns():
    provider = Provider.objects.create(name="Proveedor", code="float-booleans")
    provider_run = _provider_run(provider)
    frames = _frames(provider_run)
    frames["plans"]["es_oferta_activa"] = [1.0]
    frames["plans"]["precio_inconsistente_bandera"] = [0.0]
    frames["features"]["incluido"] = [1.0, 0.0]
    frames["feature_values"]["value_boolean"] = [pd.NA, 1.0]
    frames["feature_values"]["is_derived"] = [0.0, 1.0]
    frames["reviews"]["tiene_respuesta"] = [0.0]

    import_provider_datasets(provider_run=provider_run, **frames)

    snapshot = PlanSnapshot.objects.get(provider_run=provider_run)
    assert snapshot.is_offer_active is True
    assert snapshot.metadata_json["price_inconsistent"] is False
    assert list(
        PlanFeatureSource.objects.filter(plan_snapshot=snapshot)
        .order_by("raw_name")
        .values_list("included", flat=True)
    ) == [True, False]
    support = PlanFeatureValue.objects.get(
        plan_snapshot=snapshot,
        feature_definition__code="soporte",
    )
    assert support.value_boolean is True
    assert support.is_derived is True
    assert ReviewSnapshot.objects.get(provider_run=provider_run).has_developer_response is False


@pytest.mark.django_db
def test_import_rejects_non_binary_numeric_booleans():
    provider = Provider.objects.create(name="Proveedor", code="invalid-boolean")
    provider_run = _provider_run(provider)
    frames = _frames(provider_run)
    frames["reviews"]["tiene_respuesta"] = [0.5]

    with pytest.raises(DatasetImportError, match=r"Booleano inválido: 0\.5"):
        import_provider_datasets(provider_run=provider_run, **frames)


@pytest.mark.django_db
def test_only_complete_provider_run_can_replace_published_data():
    provider = Provider.objects.create(name="Proveedor", code="publish-provider")
    successful = _provider_run(provider)
    import_provider_datasets(provider_run=successful, **_frames(successful))
    _stages(successful, status=StageRun.Status.SUCCEEDED)
    published = publish_provider_run(successful)

    assert published.status == PipelineRun.Status.PUBLISHED
    assert list(latest_plan_snapshots().filter(provider_run__provider=provider)) == list(
        successful.plan_snapshots.all()
    )
    assert latest_review_snapshots().filter(provider_run__provider=provider).count() == 1
    matrix = latest_feature_matrix()
    matrix = matrix.loc[matrix["competidor_id"] == provider.code].reset_index(drop=True)
    assert matrix.loc[0, "usuarios"] == 3
    assert bool(matrix.loc[0, "publish-provider__soporte"]) is True

    failed = _provider_run(provider)
    import_provider_datasets(provider_run=failed, **_frames(failed))
    _stages(failed, status=StageRun.Status.SUCCEEDED)
    failed.stage_runs.filter(stage=StageRun.Stage.REVIEWS).update(status=StageRun.Status.FAILED)
    with pytest.raises(PublicationError, match="no están completas"):
        publish_provider_run(failed)

    assert latest_plan_snapshots().first().provider_run == successful


@pytest.mark.django_db
def test_artifact_store_writes_atomically_and_rejects_traversal(tmp_path):
    provider = Provider.objects.create(name="Proveedor", code="artifact-provider-2")
    provider_run = _provider_run(provider)
    store = PipelineArtifactStore(tmp_path)

    artifact = store.store_bytes(
        pipeline_run=provider_run.pipeline_run,
        provider_run=provider_run,
        artifact_type=RunArtifact.ArtifactType.NORMALIZED,
        relative_path="runs/output.csv",
        content=b"a,b\n1,2\n",
    )

    assert (tmp_path / "runs/output.csv").read_bytes() == b"a,b\n1,2\n"
    assert artifact.size_bytes == 8
    assert len(artifact.content_sha256) == 64

    with pytest.raises((ArtifactStorageError, ValueError)):
        store.store_bytes(
            pipeline_run=provider_run.pipeline_run,
            artifact_type=RunArtifact.ArtifactType.RAW,
            relative_path="../outside.csv",
            content=b"unsafe",
        )


@pytest.mark.django_db
def test_feature_matrix_endpoint_uses_only_published_data(client, django_user_model):
    user = django_user_model.objects.create_user(email="analyst@example.test", password="secret")
    client.force_login(user)
    provider = Provider.objects.create(name="Proveedor", code="api-provider")
    provider_run = _provider_run(provider)
    import_provider_datasets(provider_run=provider_run, **_frames(provider_run))
    _stages(provider_run, status=StageRun.Status.SUCCEEDED)
    publish_provider_run(provider_run)

    response = client.get("/pipeline/api/features-wide/")

    assert response.status_code == 200
    assert response.json()["rows"][0]["plan_id"] == "plan-1"
    assert response.json()["rows"][0]["usuarios"] == 3
    assert client.get("/pipeline/api/features-wide/?at=invalid").status_code == 400


@pytest.mark.django_db
def test_real_normalized_sample_imports_expected_long_records():
    providers = {}
    for order, code in enumerate(("idrixcontable", "anfibius", "perseo", "siigo_ec"), start=1):
        provider, _ = Provider.objects.update_or_create(
            code=code,
            defaults={"name": code, "execution_order": order},
        )
        providers[code] = provider
    profile = PipelineProfile.objects.create(code="sample-profile", name="Muestra")
    profile_version = PipelineProfileVersion.objects.create(profile=profile, version=1)
    pipeline_run = PipelineRun.objects.create(
        profile_version=profile_version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        status=PipelineRun.Status.RUNNING,
        started_at=timezone.now(),
    )
    plans = read_dataset(ROOT / "data/normalized/plans.csv")
    features = read_dataset(ROOT / "data/normalized/features.csv")
    reviews = read_dataset(ROOT / "data/normalized/reviews.csv")
    rules = load_feature_rules(ROOT / "feature_rules/feature-equivalence.example.json")
    transformed = transform_dataset(
        features,
        "feature",
        feature_rules=rules,
        run_id=str(pipeline_run.id),
    )
    quality_reports = json.loads(
        (ROOT / "data/normalized/quality-report.json").read_text(encoding="utf-8")
    )

    for sequence, provider in enumerate(providers.values(), start=1):
        provider_run = ProviderRun.objects.create(
            pipeline_run=pipeline_run,
            provider=provider,
            sequence=sequence,
            status=PipelineRun.Status.RUNNING,
            started_at=timezone.now(),
        )
        import_provider_datasets(
            provider_run=provider_run,
            plans=plans,
            features=features,
            feature_values=transformed.feature_values,
            reviews=reviews,
            quality_reports=quality_reports,
        )

    assert PlanSnapshot.objects.filter(provider_run__pipeline_run=pipeline_run).count() == 27
    assert (
        PlanFeatureSource.objects.filter(
            plan_snapshot__provider_run__pipeline_run=pipeline_run
        ).count()
        == 367
    )
    assert (
        PlanFeatureValue.objects.filter(
            plan_snapshot__provider_run__pipeline_run=pipeline_run
        ).count()
        == 1674
    )
    assert ReviewSnapshot.objects.filter(provider_run__pipeline_run=pipeline_run).count() == 402
    cost_center = FeatureDefinition.objects.get(
        code="centro_de_costos",
        scope=FeatureDefinition.Scope.CANONICAL,
    )
    assert not FeatureDefinition.objects.filter(
        code="centro_de_costos",
        scope=FeatureDefinition.Scope.PROVIDER,
    ).exists()
    cost_center_values = PlanFeatureValue.objects.filter(
        plan_snapshot__provider_run__pipeline_run=pipeline_run,
        plan_snapshot__provider_run__provider__code="perseo",
        feature_definition=cost_center,
    )
    assert (
        cost_center_values.filter(
            availability=PlanFeatureValue.Availability.PRESENT,
            value_boolean=True,
            origin=PlanFeatureValue.Origin.RULE,
        ).count()
        == 3
    )
    assert (
        cost_center_values.filter(
            availability=PlanFeatureValue.Availability.UNKNOWN,
            origin=PlanFeatureValue.Origin.DEFAULT,
        ).count()
        == 9
    )


def _provider_run(provider: Provider) -> ProviderRun:
    profile = PipelineProfile.objects.create(code=f"profile-{uuid4()}", name="Perfil")
    profile_version = PipelineProfileVersion.objects.create(profile=profile, version=1)
    run = PipelineRun.objects.create(
        profile_version=profile_version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        status=PipelineRun.Status.RUNNING,
        started_at=timezone.now(),
    )
    return ProviderRun.objects.create(
        pipeline_run=run,
        provider=provider,
        sequence=1,
        status=PipelineRun.Status.RUNNING,
        started_at=timezone.now(),
    )


def _stages(provider_run: ProviderRun, *, status: str) -> None:
    for sequence, stage in enumerate(
        (StageRun.Stage.PLANS, StageRun.Stage.FEATURES, StageRun.Stage.REVIEWS), start=1
    ):
        StageRun.objects.create(
            provider_run=provider_run,
            stage=stage,
            sequence=sequence,
            status=status,
        )


def _frames(provider_run: ProviderRun) -> dict:
    provider_code = provider_run.provider.code
    now = timezone.now().isoformat()
    return {
        "plans": pd.DataFrame(
            [
                {
                    "timestamp_utc": now,
                    "competidor_id": provider_code,
                    "plan_id": "plan-1",
                    "plan_nombre": "Plan Uno",
                    "producto": "contabilidad",
                    "precio_mensual": "10.50",
                    "precio_anual_total": "100",
                    "precio_mensual_efectivo": "8.3333",
                    "moneda_codigo": "USD",
                }
            ]
        ),
        "features": pd.DataFrame(
            [
                {
                    "competidor_id": provider_code,
                    "plan_id": "plan-1",
                    "categoria_modulo": "General",
                    "nombre_modulo": "3 usuarios",
                    "nombre_modulo_normalizado": "3_usuarios",
                    "incluido": 1,
                },
                {
                    "competidor_id": provider_code,
                    "plan_id": "plan-1",
                    "categoria_modulo": "General",
                    "nombre_modulo": "Soporte",
                    "nombre_modulo_normalizado": "soporte",
                    "incluido": 1,
                },
            ]
        ),
        "feature_values": pd.DataFrame(
            [
                {
                    "run_id": str(provider_run.pipeline_run_id),
                    "competidor_id": provider_code,
                    "plan_id": "plan-1",
                    "feature_code": "usuarios",
                    "value_type": "integer",
                    "value_integer": 3,
                    "availability": "present",
                    "origin": "rule",
                    "rule_id": "usuarios_rule",
                    "is_derived": False,
                },
                {
                    "run_id": str(provider_run.pipeline_run_id),
                    "competidor_id": provider_code,
                    "plan_id": "plan-1",
                    "feature_code": "soporte",
                    "value_type": "boolean",
                    "value_boolean": True,
                    "availability": "present",
                    "origin": "fallback",
                    "is_derived": False,
                },
            ]
        ),
        "reviews": pd.DataFrame(
            [
                {
                    "competidor_id": provider_code,
                    "review_id": "review-1",
                    "plataforma_codigo": "google_maps",
                    "calificacion_estrellas": 5,
                    "comentario_cliente": "Excelente",
                    "tiene_respuesta": 0,
                    "timestamp_ingesta": now,
                    "sentimiento_por_calificacion": "positive",
                }
            ]
        ),
        "quality_reports": [
            {
                "dataset_type": "feature",
                "issues": [
                    {
                        "code": "normalization-collision",
                        "message": "Colisión controlada",
                        "column": "nombre_modulo_normalizado",
                    }
                ],
            }
        ],
    }
