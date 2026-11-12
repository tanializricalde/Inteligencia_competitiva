import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.db import migrations

DATASET_CODE = "anfibius_recovery_v1"
PROFILE_CODE = "anfibius-recovery"
PROVIDER_CODE = "anfibius"
RUN_ID = uuid.uuid5(uuid.NAMESPACE_URL, DATASET_CODE)


def _fixture():
    path = Path(__file__).with_name("fixtures") / "anfibius_recovery_v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _datetime(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _content_hash(payload):
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def seed_anfibius_recovery(apps, schema_editor):
    Provider = apps.get_model("market", "Provider")
    PipelineProfile = apps.get_model("pipeline", "PipelineProfile")
    PipelineProfileVersion = apps.get_model("pipeline", "PipelineProfileVersion")
    PipelineRun = apps.get_model("pipeline", "PipelineRun")
    ProviderRun = apps.get_model("pipeline", "ProviderRun")
    StageRun = apps.get_model("pipeline", "StageRun")
    MarketPlan = apps.get_model("pipeline", "MarketPlan")
    PlanSnapshot = apps.get_model("pipeline", "PlanSnapshot")
    PlanFeatureSource = apps.get_model("pipeline", "PlanFeatureSource")
    FeatureDefinition = apps.get_model("pipeline", "FeatureDefinition")
    PlanFeatureValue = apps.get_model("pipeline", "PlanFeatureValue")
    PlanFeatureValueSource = apps.get_model("pipeline", "PlanFeatureValueSource")
    MarketReview = apps.get_model("pipeline", "MarketReview")
    ReviewSnapshot = apps.get_model("pipeline", "ReviewSnapshot")

    payload = _fixture()
    if payload["_meta"]["provider_code"] != PROVIDER_CODE:
        raise RuntimeError("El fixture de recuperación no pertenece exclusivamente a Anfibius")
    expected = payload["_meta"]["counts"]
    actual = {
        "plans": len(payload["plans"]),
        "feature_sources": len(payload["feature_sources"]),
        "feature_values": len(payload["feature_values"]),
        "reviews": len(payload["reviews"]),
    }
    if actual != expected:
        raise RuntimeError(f"El fixture de recuperación está incompleto: {actual!r}")

    observed_times = [_datetime(item["observed_at"]) for item in payload["plans"]]
    review_times = [_datetime(item["ingested_at"]) for item in payload["reviews"]]
    started_at = min([*observed_times, *review_times])
    published_at = max([*observed_times, *review_times])

    provider, _ = Provider.objects.get_or_create(
        code=PROVIDER_CODE,
        defaults={
            "name": "Anfibius",
            "data_scope": "real",
            "is_active": True,
            "execution_order": 3,
        },
    )
    provider_updates = []
    if provider.data_scope != "real":
        provider.data_scope = "real"
        provider_updates.append("data_scope")
    if not provider.is_active:
        provider.is_active = True
        provider_updates.append("is_active")
    if provider_updates:
        provider.save(update_fields=provider_updates)

    profile, profile_created = PipelineProfile.objects.get_or_create(
        code=PROFILE_CODE,
        defaults={
            "name": "Recuperación histórica de Anfibius",
            "description": "Snapshot estático; no ejecuta scrapers.",
            "is_active": False,
        },
    )
    profile_version, _ = PipelineProfileVersion.objects.update_or_create(
        profile=profile,
        version=1,
        defaults={
            "status": "published",
            "description": "Captura normalizada histórica de Anfibius.",
            "published_at": published_at,
        },
    )
    if profile.active_version_id != profile_version.id:
        profile.active_version_id = profile_version.id
        profile.save(update_fields=("active_version",))

    existing_run = PipelineRun.objects.filter(id=RUN_ID).first()
    if existing_run and existing_run.metadata_json.get("recovery_dataset") != DATASET_CODE:
        raise RuntimeError("El UUID reservado para Anfibius pertenece a otra ejecución")

    previous_metadata = existing_run.metadata_json if existing_run else {}
    created_plan_keys = list(previous_metadata.get("created_plan_keys", []))
    created_review_ids = list(previous_metadata.get("created_review_ids", []))
    created_definitions = list(previous_metadata.get("created_feature_definitions", []))
    profile_created_for_migration = previous_metadata.get("profile_created", profile_created)
    run, _ = PipelineRun.objects.update_or_create(
        id=RUN_ID,
        defaults={
            "profile_version": profile_version,
            "trigger_type": "reprocess",
            "status": "published",
            "started_at": started_at,
            "finished_at": published_at,
            "published_at": published_at,
            "metadata_json": {
                "recovery_dataset": DATASET_CODE,
                "source": "data/normalized",
                "source_sha256": payload["_meta"]["source_files"],
                "privacy": payload["_meta"]["privacy"],
                "profile_created": profile_created_for_migration,
            },
        },
    )
    provider_run, _ = ProviderRun.objects.update_or_create(
        pipeline_run=run,
        provider=provider,
        defaults={
            "sequence": 1,
            "status": "published",
            "started_at": started_at,
            "finished_at": published_at,
            "is_complete": True,
            "published_at": published_at,
            "error_summary": "",
        },
    )
    for sequence, (stage, output_count) in enumerate(
        (("plans", 3), ("features", 15), ("reviews", 50)), start=1
    ):
        StageRun.objects.update_or_create(
            provider_run=provider_run,
            stage=stage,
            defaults={
                "sequence": sequence,
                "status": "succeeded",
                "attempt_count": 0,
                "started_at": started_at,
                "finished_at": published_at,
                "output_row_count": output_count,
                "diagnostics_json": {"recovery_dataset": DATASET_CODE},
            },
        )

    snapshots = {}
    sources_by_plan = {}
    sources_by_normalized = {}
    for row in payload["plans"]:
        observed_at = _datetime(row["observed_at"])
        market_plan, created = MarketPlan.objects.get_or_create(
            provider=provider,
            external_key=row["external_key"],
            defaults={
                "first_seen_at": observed_at,
                "last_seen_at": observed_at,
                "is_active": True,
            },
        )
        if created and row["external_key"] not in created_plan_keys:
            created_plan_keys.append(row["external_key"])
        elif market_plan.last_seen_at < observed_at:
            market_plan.last_seen_at = observed_at
            market_plan.is_active = True
            market_plan.save(update_fields=("last_seen_at", "is_active"))
        snapshot, _ = PlanSnapshot.objects.update_or_create(
            provider_run=provider_run,
            market_plan=market_plan,
            defaults={
                "observed_at": observed_at,
                "plan_name": row["name"],
                "normalized_name": row["normalized_name"],
                "product_code": row["product_code"],
                "source_url": row["source_url"],
                "promotion_text": None,
                "is_offer_active": row["is_offer_active"],
                "metadata_json": {
                    "recovery_dataset": DATASET_CODE,
                    "currency_code": row["currency_code"],
                    "prices_observed": False,
                },
            },
        )
        snapshots[row["external_key"]] = snapshot

    for row in payload["feature_sources"]:
        snapshot = snapshots[row["plan_id"]]
        key_payload = {
            "plan_id": row["plan_id"],
            "category": row["category"],
            "raw_name": row["raw_name"],
            "normalized_name": row["normalized_name"],
            "included": row["included"],
        }
        source, _ = PlanFeatureSource.objects.update_or_create(
            plan_snapshot=snapshot,
            source_row_key=_content_hash(key_payload),
            defaults={
                "category": row["category"],
                "raw_name": row["raw_name"],
                "normalized_name": row["normalized_name"],
                "included": row["included"],
                "position": row["position"],
                "metadata_json": {"recovery_dataset": DATASET_CODE},
            },
        )
        sources_by_plan.setdefault(row["plan_id"], []).append(source)
        sources_by_normalized.setdefault((row["plan_id"], row["normalized_name"]), []).append(
            source
        )

    definitions = {}
    for row in payload["feature_values"]:
        scope = "provider" if row["origin"] == "fallback" else "canonical"
        definition_key = (scope, row["code"])
        definition = definitions.get(definition_key)
        if definition is None:
            lookup = {"code": row["code"], "scope": scope}
            if scope == "provider":
                lookup["provider"] = provider
            else:
                lookup["provider"] = None
            definition, created = FeatureDefinition.objects.get_or_create(
                **lookup,
                defaults={
                    "display_name": row["code"].replace("_", " ").capitalize(),
                    "data_type": row["data_type"],
                    "origin": "fallback" if scope == "provider" else "configured",
                    "is_active": True,
                },
            )
            if definition.data_type != row["data_type"]:
                raise RuntimeError(f"La característica {row['code']!r} ya existe con otro tipo")
            definition_marker = {"scope": scope, "code": row["code"]}
            if created and definition_marker not in created_definitions:
                created_definitions.append(definition_marker)
            definitions[definition_key] = definition
        snapshot = snapshots[row["plan_id"]]
        value, _ = PlanFeatureValue.objects.update_or_create(
            plan_snapshot=snapshot,
            feature_definition=definition,
            defaults={
                "value_boolean": row["value_boolean"],
                "value_integer": row["value_integer"],
                "value_decimal": (
                    Decimal(row["value_decimal"]) if row["value_decimal"] is not None else None
                ),
                "value_text": row["value_text"],
                "value_json": row["value_json"],
                "availability": row["availability"],
                "origin": row["origin"],
                "source_rule_id": row["rule_id"],
                "is_derived": row["is_derived"],
                "metadata_json": {"recovery_dataset": DATASET_CODE},
            },
        )
        PlanFeatureValueSource.objects.filter(plan_feature_value=value).delete()
        candidates = (
            sources_by_normalized.get((row["plan_id"], row["code"]), [])
            if row["origin"] == "fallback"
            else sources_by_plan.get(row["plan_id"], [])
        )
        if row["origin"] != "default":
            PlanFeatureValueSource.objects.bulk_create(
                [
                    PlanFeatureValueSource(
                        plan_feature_value=value,
                        plan_feature_source=source,
                    )
                    for source in candidates
                ],
                ignore_conflicts=True,
            )

    for row in payload["reviews"]:
        ingested_at = _datetime(row["ingested_at"])
        review, created = MarketReview.objects.get_or_create(
            provider=provider,
            platform_code=row["platform_code"],
            external_review_id=row["external_id"],
            defaults={
                "first_seen_at": ingested_at,
                "last_seen_at": ingested_at,
                "is_active": True,
            },
        )
        if created and row["external_id"] not in created_review_ids:
            created_review_ids.append(row["external_id"])
        content = {
            "country_code": row["country_code"],
            "rating_stars": row["rating_stars"],
            "has_developer_response": row["has_developer_response"],
            "sentiment_from_rating": row["sentiment_from_rating"],
        }
        ReviewSnapshot.objects.update_or_create(
            provider_run=provider_run,
            market_review=review,
            defaults={
                **content,
                "user_name": None,
                "customer_comment": None,
                "developer_response": None,
                "ingested_at": ingested_at,
                "review_published_at": None,
                "content_sha256": _content_hash(content),
                "metadata_json": {
                    "recovery_dataset": DATASET_CODE,
                    "personal_data_redacted": True,
                },
            },
        )

    run.metadata_json.update(
        {
            "created_plan_keys": created_plan_keys,
            "created_review_ids": created_review_ids,
            "created_feature_definitions": created_definitions,
        }
    )
    run.save(update_fields=("metadata_json",))


def remove_anfibius_recovery(apps, schema_editor):
    PipelineProfile = apps.get_model("pipeline", "PipelineProfile")
    PipelineProfileVersion = apps.get_model("pipeline", "PipelineProfileVersion")
    PipelineRun = apps.get_model("pipeline", "PipelineRun")
    ProviderRun = apps.get_model("pipeline", "ProviderRun")
    StageRun = apps.get_model("pipeline", "StageRun")
    SourceRun = apps.get_model("pipeline", "SourceRun")
    RunArtifact = apps.get_model("pipeline", "RunArtifact")
    QualityIssue = apps.get_model("pipeline", "QualityIssue")
    PlanSnapshot = apps.get_model("pipeline", "PlanSnapshot")
    PlanFeatureSource = apps.get_model("pipeline", "PlanFeatureSource")
    PlanFeatureValue = apps.get_model("pipeline", "PlanFeatureValue")
    PlanFeatureValueSource = apps.get_model("pipeline", "PlanFeatureValueSource")
    ReviewSnapshot = apps.get_model("pipeline", "ReviewSnapshot")
    MarketPlan = apps.get_model("pipeline", "MarketPlan")
    MarketReview = apps.get_model("pipeline", "MarketReview")
    FeatureDefinition = apps.get_model("pipeline", "FeatureDefinition")

    run = PipelineRun.objects.filter(
        id=RUN_ID,
        metadata_json__recovery_dataset=DATASET_CODE,
    ).first()
    if run is None:
        return
    metadata = run.metadata_json
    provider_runs = ProviderRun.objects.filter(
        pipeline_run_id=run.pk,
        provider__code=PROVIDER_CODE,
    )
    provider_run_ids = list(provider_runs.values_list("id", flat=True))
    provider_id = provider_runs.values_list("provider_id", flat=True).first()
    snapshots = PlanSnapshot.objects.filter(provider_run_id__in=provider_run_ids)
    PlanFeatureValueSource.objects.filter(plan_feature_value__plan_snapshot__in=snapshots).delete()
    PlanFeatureValue.objects.filter(plan_snapshot__in=snapshots).delete()
    PlanFeatureSource.objects.filter(plan_snapshot__in=snapshots).delete()
    snapshots.delete()
    ReviewSnapshot.objects.filter(provider_run_id__in=provider_run_ids).delete()
    SourceRun.objects.filter(stage_run__provider_run_id__in=provider_run_ids).delete()
    StageRun.objects.filter(provider_run_id__in=provider_run_ids).delete()
    RunArtifact.objects.filter(pipeline_run_id=run.pk).delete()
    QualityIssue.objects.filter(pipeline_run_id=run.pk).delete()
    provider_runs.delete()
    # El colector de Django puede resolver relaciones con clases historicas de
    # otro estado cuando esta migracion se revierte como dependencia de
    # ``market``. Todos los hijos se eliminaron explicitamente arriba, por lo
    # que el borrado directo evita mezclar esas clases historicas incompatibles.
    PipelineRun.objects.filter(pk=run.pk)._raw_delete(using=schema_editor.connection.alias)

    if provider_id is not None:
        plans = MarketPlan.objects.filter(
            provider_id=provider_id,
            external_key__in=metadata.get("created_plan_keys", []),
        )
        for plan in plans:
            if not PlanSnapshot.objects.filter(market_plan_id=plan.pk).exists():
                MarketPlan.objects.filter(pk=plan.pk)._raw_delete(
                    using=schema_editor.connection.alias
                )
        reviews = MarketReview.objects.filter(
            provider_id=provider_id,
            external_review_id__in=metadata.get("created_review_ids", []),
        )
        for review in reviews:
            if not ReviewSnapshot.objects.filter(market_review_id=review.pk).exists():
                MarketReview.objects.filter(pk=review.pk)._raw_delete(
                    using=schema_editor.connection.alias
                )
        for item in metadata.get("created_feature_definitions", []):
            query = FeatureDefinition.objects.filter(
                code=item["code"],
                scope=item["scope"],
            )
            query = (
                query.filter(provider_id=provider_id)
                if item["scope"] == "provider"
                else query.filter(provider__isnull=True)
            )
            for definition in query:
                if not PlanFeatureValue.objects.filter(
                    feature_definition_id=definition.pk
                ).exists():
                    FeatureDefinition.objects.filter(pk=definition.pk)._raw_delete(
                        using=schema_editor.connection.alias
                    )

    if metadata.get("profile_created"):
        profile = PipelineProfile.objects.filter(code=PROFILE_CODE, is_active=False).first()
        if (
            profile is not None
            and not PipelineRun.objects.filter(profile_version__profile_id=profile.pk).exists()
        ):
            profile.active_version = None
            profile.save(update_fields=("active_version",))
            PipelineProfileVersion.objects.filter(profile_id=profile.pk)._raw_delete(
                using=schema_editor.connection.alias
            )
            PipelineProfile.objects.filter(pk=profile.pk)._raw_delete(
                using=schema_editor.connection.alias
            )


class Migration(migrations.Migration):
    dependencies = [
        ("market", "0008_application_branding"),
        ("pipeline", "0002_alter_marketreview_options_and_more"),
    ]

    operations = [migrations.RunPython(seed_anfibius_recovery, remove_anfibius_recovery)]
