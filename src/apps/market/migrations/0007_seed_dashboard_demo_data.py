import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import migrations
from django.utils import timezone

DATASET_CODE = "dashboard_demo_v1"
PROFILE_CODE = "demo_dashboard"
PROVIDERS = (
    (
        "demo_product",
        "Producto Demo",
        (("Inicial", 9), ("Pyme", 15), ("Pro", 29), ("Empresarial", 55)),
        11,
    ),
    (
        "demo_competitor_alpha",
        "Competidor Demo Alfa",
        (("Emprendedor", 19), ("Pyme", 35), ("Pro", 59), ("Empresarial", 99)),
        26,
    ),
    (
        "demo_competitor_beta",
        "Competidor Demo Beta",
        (("Básico", 12), ("Estándar", 22), ("Avanzado", 38), ("Empresarial", 65)),
        13,
    ),
    (
        "demo_competitor_gamma",
        "Competidor Demo Gamma",
        (("Esencial", 15), ("Profesional", 28), ("Premium", 48)),
        9,
    ),
)
FEATURES = (
    ("demo_dashboard_facturacion", "Facturación electrónica", (2, 2, 2, 2)),
    ("demo_dashboard_retenciones", "Retenciones y anexos", (2, 2, 1, 1)),
    ("demo_dashboard_nomina", "Nómina", (2, 2, 2, 0)),
    ("demo_dashboard_inventario", "Inventario", (2, 2, 1, 2)),
    ("demo_dashboard_contabilidad", "Contabilidad y balances", (2, 2, 2, 1)),
    ("demo_dashboard_activos", "Activos fijos", (1, 2, 0, 0)),
)


def _run_uuid(month_index):
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{DATASET_CODE}:run:{month_index}")


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _rating_rows(count):
    distributions = {
        11: (9, 1, 1, 5),
        26: (18, 5, 3, 5),
        13: (8, 3, 2, 4),
        9: (6, 2, 1, 4),
    }
    positive, neutral, negative, positive_stars = distributions[count]
    rows = [(positive_stars, "positive")] * positive
    rows += [(3, "neutral")] * neutral
    rows += [(2 if count != 11 else 1, "negative")] * negative
    return rows


def seed_demo(apps, schema_editor):
    Provider = apps.get_model("market", "Provider")
    DashboardPreset = apps.get_model("market", "DashboardPreset")
    PipelineProfile = apps.get_model("pipeline", "PipelineProfile")
    PipelineProfileVersion = apps.get_model("pipeline", "PipelineProfileVersion")
    PipelineRun = apps.get_model("pipeline", "PipelineRun")
    ProviderRun = apps.get_model("pipeline", "ProviderRun")
    MarketPlan = apps.get_model("pipeline", "MarketPlan")
    PlanSnapshot = apps.get_model("pipeline", "PlanSnapshot")
    PlanPriceSnapshot = apps.get_model("pipeline", "PlanPriceSnapshot")
    FeatureDefinition = apps.get_model("pipeline", "FeatureDefinition")
    PlanFeatureSource = apps.get_model("pipeline", "PlanFeatureSource")
    PlanFeatureValue = apps.get_model("pipeline", "PlanFeatureValue")
    PlanFeatureValueSource = apps.get_model("pipeline", "PlanFeatureValueSource")
    MarketReview = apps.get_model("pipeline", "MarketReview")
    ReviewSnapshot = apps.get_model("pipeline", "ReviewSnapshot")

    now = timezone.now()
    profile, _ = PipelineProfile.objects.update_or_create(
        code=PROFILE_CODE,
        defaults={
            "name": "Perfil sintético del dashboard",
            "description": "Datos demostrativos; no ejecuta scrapers.",
            "is_active": False,
        },
    )
    profile_version, _ = PipelineProfileVersion.objects.update_or_create(
        profile=profile,
        version=1,
        defaults={
            "status": "published",
            "description": "Snapshot sintético aislado para el dashboard.",
            "published_at": now,
        },
    )
    profile.active_version_id = profile_version.id
    profile.save(update_fields=("active_version",))

    providers = []
    plans_by_provider = {}
    oldest = now - timedelta(days=150)
    for order, (code, name, plan_rows, _review_count) in enumerate(PROVIDERS, start=1):
        provider, _ = Provider.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "data_scope": "demo",
                "is_active": True,
                "execution_order": 1000 + order,
                "notes": "Datos sintéticos del dashboard; no representan el mercado real.",
            },
        )
        providers.append(provider)
        plans_by_provider[provider.id] = []
        for plan_order, (plan_name, _price) in enumerate(plan_rows, start=1):
            external_key = f"{code}-plan-{plan_order}"
            plan, _ = MarketPlan.objects.update_or_create(
                provider=provider,
                external_key=external_key,
                defaults={"first_seen_at": oldest, "last_seen_at": now, "is_active": True},
            )
            plans_by_provider[provider.id].append((plan, plan_name, Decimal(str(_price))))

    definitions = []
    for code, name, _states in FEATURES:
        definition, _ = FeatureDefinition.objects.update_or_create(
            code=code,
            scope="canonical",
            defaults={
                "display_name": name,
                "data_type": "boolean",
                "category": "Demo",
                "origin": "configured",
                "is_active": True,
                "provider": None,
            },
        )
        definitions.append(definition)

    latest_provider_runs = {}
    for month_index in range(6):
        observed_at = now - timedelta(days=30 * (5 - month_index))
        run, _ = PipelineRun.objects.update_or_create(
            id=_run_uuid(month_index),
            defaults={
                "profile_version": profile_version,
                "trigger_type": "reprocess",
                "status": "published",
                "started_at": observed_at,
                "finished_at": observed_at,
                "published_at": observed_at,
                "metadata_json": {"synthetic_dataset": DATASET_CODE},
            },
        )
        for sequence, provider in enumerate(providers, start=1):
            provider_run, _ = ProviderRun.objects.update_or_create(
                pipeline_run=run,
                provider=provider,
                defaults={
                    "sequence": sequence,
                    "status": "published",
                    "started_at": observed_at,
                    "finished_at": observed_at,
                    "is_complete": True,
                    "published_at": observed_at,
                },
            )
            if month_index == 5:
                latest_provider_runs[provider.id] = provider_run
            for plan, plan_name, base_price in plans_by_provider[provider.id]:
                growth = Decimal("1") + Decimal(month_index) * Decimal("0.01")
                monthly = (base_price * growth).quantize(Decimal("0.01"))
                snapshot, _ = PlanSnapshot.objects.update_or_create(
                    provider_run=provider_run,
                    market_plan=plan,
                    defaults={
                        "observed_at": observed_at,
                        "plan_name": plan_name,
                        "normalized_name": plan_name.casefold(),
                        "product_code": "software-contable-demo",
                        "promotion_text": None,
                        "is_offer_active": False,
                        "metadata_json": {"synthetic_dataset": DATASET_CODE},
                    },
                )
                PlanPriceSnapshot.objects.update_or_create(
                    plan_snapshot=snapshot,
                    billing_period="monthly",
                    source_kind="scraped",
                    defaults={
                        "currency_code": "USD",
                        "amount": monthly,
                        "effective_monthly_amount": monthly,
                        "is_promotional": False,
                        "metadata_json": {"synthetic_dataset": DATASET_CODE},
                    },
                )
                PlanPriceSnapshot.objects.update_or_create(
                    plan_snapshot=snapshot,
                    billing_period="annual",
                    source_kind="scraped",
                    defaults={
                        "currency_code": "USD",
                        "amount": (monthly * Decimal("10.20")).quantize(Decimal("0.01")),
                        "effective_monthly_amount": (monthly * Decimal("0.85")).quantize(
                            Decimal("0.01")
                        ),
                        "is_promotional": False,
                        "metadata_json": {"synthetic_dataset": DATASET_CODE},
                    },
                )

    for provider_index, provider in enumerate(providers):
        provider_run = latest_provider_runs[provider.id]
        plan_rows = plans_by_provider[provider.id]
        for feature_index, (definition, feature_spec) in enumerate(
            zip(definitions, FEATURES, strict=True)
        ):
            state = feature_spec[2][provider_index]
            for plan_index, (plan, _name, _price) in enumerate(plan_rows):
                snapshot = PlanSnapshot.objects.get(
                    provider_run=provider_run, market_plan=plan
                )
                included = state == 2 or (state == 1 and plan_index == 0)
                availability = "present" if included else "excluded"
                source, _ = PlanFeatureSource.objects.update_or_create(
                    plan_snapshot=snapshot,
                    source_row_key=f"demo-feature-{feature_index}",
                    defaults={
                        "category": "Demo",
                        "raw_name": definition.display_name,
                        "normalized_name": definition.code,
                        "included": included,
                        "position": feature_index,
                        "metadata_json": {"synthetic_dataset": DATASET_CODE},
                    },
                )
                value, _ = PlanFeatureValue.objects.update_or_create(
                    plan_snapshot=snapshot,
                    feature_definition=definition,
                    defaults={
                        "value_boolean": included,
                        "availability": availability,
                        "origin": "rule",
                        "source_rule_id": DATASET_CODE,
                        "metadata_json": {"synthetic_dataset": DATASET_CODE},
                    },
                )
                PlanFeatureValueSource.objects.get_or_create(
                    plan_feature_value=value, plan_feature_source=source
                )

        review_count = PROVIDERS[provider_index][3]
        for review_index, (rating, sentiment) in enumerate(_rating_rows(review_count), start=1):
            external_id = f"{provider.code}-review-{review_index}"
            review, _ = MarketReview.objects.update_or_create(
                provider=provider,
                platform_code="demo",
                external_review_id=external_id,
                defaults={"first_seen_at": now, "last_seen_at": now, "is_active": True},
            )
            content = f"{DATASET_CODE}:{external_id}:{rating}:{sentiment}"
            ReviewSnapshot.objects.update_or_create(
                provider_run=provider_run,
                market_review=review,
                defaults={
                    "country_code": "EC",
                    "user_name": f"Usuario sintético {review_index}",
                    "rating_stars": rating,
                    "customer_comment": None,
                    "has_developer_response": False,
                    "developer_response": None,
                    "ingested_at": now,
                    "review_published_at": now - timedelta(days=review_index),
                    "sentiment_from_rating": sentiment,
                    "content_sha256": _hash(content),
                    "metadata_json": {"synthetic_dataset": DATASET_CODE},
                },
            )

    DashboardPreset.objects.filter(slug="demo").update(
        name="DEMO",
        description="Datos demostrativos; no representan el mercado real.",
        data_scope="demo",
        plan_selection="all_current",
        is_active=True,
        is_system=True,
    )


def remove_demo(apps, schema_editor):
    Provider = apps.get_model("market", "Provider")
    PipelineProfile = apps.get_model("pipeline", "PipelineProfile")
    PipelineRun = apps.get_model("pipeline", "PipelineRun")
    PlanSnapshot = apps.get_model("pipeline", "PlanSnapshot")
    PlanFeatureSource = apps.get_model("pipeline", "PlanFeatureSource")
    PlanFeatureValue = apps.get_model("pipeline", "PlanFeatureValue")
    PlanFeatureValueSource = apps.get_model("pipeline", "PlanFeatureValueSource")
    ReviewSnapshot = apps.get_model("pipeline", "ReviewSnapshot")
    MarketPlan = apps.get_model("pipeline", "MarketPlan")
    MarketReview = apps.get_model("pipeline", "MarketReview")
    FeatureDefinition = apps.get_model("pipeline", "FeatureDefinition")

    codes = [item[0] for item in PROVIDERS]
    providers = Provider.objects.filter(code__in=codes, data_scope="demo")
    runs = PipelineRun.objects.filter(id__in=[_run_uuid(index) for index in range(6)])
    demo_snapshots = PlanSnapshot.objects.filter(provider_run__pipeline_run__in=runs)
    PlanFeatureValueSource.objects.filter(
        plan_feature_value__plan_snapshot__in=demo_snapshots
    ).delete()
    PlanFeatureValue.objects.filter(plan_snapshot__in=demo_snapshots).delete()
    PlanFeatureSource.objects.filter(plan_snapshot__in=demo_snapshots).delete()
    demo_snapshots.delete()
    ReviewSnapshot.objects.filter(provider_run__pipeline_run__in=runs).delete()
    MarketPlan.objects.filter(provider__in=providers).delete()
    MarketReview.objects.filter(provider__in=providers).delete()
    runs.delete()
    FeatureDefinition.objects.filter(code__startswith="demo_dashboard_").delete()
    profiles = PipelineProfile.objects.filter(code=PROFILE_CODE, is_active=False)
    profiles.update(active_version=None)
    for profile in profiles:
        profile.versions.all().delete()
    profiles.delete()
    providers.delete()


class Migration(migrations.Migration):
    dependencies = [("market", "0006_seed_dashboard_system_presets")]

    operations = [migrations.RunPython(seed_demo, remove_demo)]
