import json
import tomllib
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import slugify

from apps.market.models import Provider
from apps.pipeline.models import (
    MarketSource,
    PipelineConfig,
    PipelineConfigVersion,
    PipelineProfile,
    PipelineProfileStage,
    PipelineProfileVersion,
    ScheduledJob,
)

NON_OPERATIONAL_PROVIDER_CODES = frozenset({"competidor_demo"})


class Command(BaseCommand):
    help = "Siembra providers, fuentes y versiones no sensibles de forma idempotente"

    def add_arguments(self, parser):
        parser.add_argument("--config", type=Path, default=Path("config.example.toml"))
        parser.add_argument(
            "--feature-rules",
            type=Path,
            default=Path("feature_rules/feature-equivalence.example.json"),
        )
        parser.add_argument("--profile", default="nightly-market")

    def handle(self, *args, **options):
        try:
            config_payload = tomllib.loads(options["config"].read_text(encoding="utf-8"))
            feature_payload = json.loads(options["feature_rules"].read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError, json.JSONDecodeError) as exc:
            raise CommandError(f"No se pudo leer la configuración inicial: {exc}") from exc
        providers_payload = config_payload.get("providers")
        if not isinstance(providers_payload, list):
            raise CommandError("config.toml requiere [[providers]]")

        self._seed_sources(providers_payload)
        versions = {
            PipelineConfig.Stage.EXTRACTION: self._config_version(
                "extraction-default", PipelineConfig.Stage.EXTRACTION, config_payload
            ),
            PipelineConfig.Stage.CLEANING: self._config_version(
                "cleaning-default",
                PipelineConfig.Stage.CLEANING,
                {"schema_version": 1, "profile": "conservative"},
            ),
            PipelineConfig.Stage.NORMALIZATION: self._config_version(
                "normalization-default",
                PipelineConfig.Stage.NORMALIZATION,
                {"schema_version": 1, "profile": "canonical-v2"},
            ),
            PipelineConfig.Stage.FEATURE_EQUIVALENCE: self._config_version(
                "feature-equivalence", PipelineConfig.Stage.FEATURE_EQUIVALENCE, feature_payload
            ),
        }
        profile, _ = PipelineProfile.objects.get_or_create(
            code=options["profile"],
            defaults={"name": "Pipeline nocturno de mercado"},
        )
        profile_version = self._profile_version(profile, versions)
        if profile_version.status == PipelineProfileVersion.Status.DRAFT:
            for order, stage in enumerate(
                (
                    PipelineConfig.Stage.EXTRACTION,
                    PipelineConfig.Stage.CLEANING,
                    PipelineConfig.Stage.NORMALIZATION,
                    PipelineConfig.Stage.FEATURE_EQUIVALENCE,
                ),
                start=1,
            ):
                PipelineProfileStage.objects.get_or_create(
                    profile_version=profile_version,
                    stage=stage,
                    defaults={"config_version": versions[stage], "execution_order": order},
                )
            profile_version.status = PipelineProfileVersion.Status.PUBLISHED
            profile_version.save()
        profile.active_version = profile_version
        profile.full_clean()
        profile.save(update_fields=("active_version",))
        ScheduledJob.objects.update_or_create(
            code="nightly-market",
            defaults={
                "name": "Pipeline nocturno de mercado",
                "profile": profile,
                "cron_expression": "0 2 * * *",
                "timezone": "America/Lima",
                "is_active": True,
                "retry_policy_json": {"source_retries_owned_by_market_source": True},
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Pipeline inicial listo: {profile.code}@{profile_version.version}"
            )
        )

    def _seed_sources(self, providers_payload):
        for provider_order, raw_provider in enumerate(providers_payload, start=1):
            if raw_provider.get("code") in NON_OPERATIONAL_PROVIDER_CODES:
                continue
            provider, _ = Provider.objects.update_or_create(
                code=raw_provider["code"],
                defaults={
                    "name": raw_provider["name"],
                    "execution_order": provider_order,
                    "is_active": True,
                    "data_scope": Provider.DataScope.REAL,
                },
            )
            plan_sources = raw_provider.get("plan_sources", [])
            review_sources = raw_provider.get("review_sources", [])
            for data_type, sources in (
                (MarketSource.DataType.PLANS, plan_sources),
                (MarketSource.DataType.REVIEWS, review_sources),
            ):
                for source_order, raw_source in enumerate(sources, start=1):
                    code = slugify(raw_source["name"])[:100]
                    settings = {
                        key: raw_source[key]
                        for key in (
                            "timeout_seconds",
                            "retry_limit",
                            "request_delay_seconds",
                            "max_pages",
                        )
                        if key in raw_source
                    }
                    settings["adapter_config"] = raw_source.get("config", {})
                    MarketSource.objects.update_or_create(
                        provider=provider,
                        code=code,
                        defaults={
                            "name": raw_source["name"],
                            "data_type": data_type,
                            "adapter_key": raw_source["adapter_key"],
                            "url": raw_source["url"],
                            "platform_code": raw_source.get("platform"),
                            "country_code": raw_source.get("country_code"),
                            "execution_order": source_order,
                            "is_active": bool(raw_source.get("enabled", True)),
                            "settings_json": settings,
                        },
                    )
            base_url = next(
                (source["url"] for source in (*plan_sources, *review_sources) if source.get("url")),
                "https://example.test/pipeline-features",
            )
            MarketSource.objects.update_or_create(
                provider=provider,
                code="pipeline-features",
                defaults={
                    "name": "Limpieza y equivalencia de características",
                    "data_type": MarketSource.DataType.FEATURES,
                    "adapter_key": "pipeline_features",
                    "url": base_url,
                    "execution_order": 1,
                    "is_active": any(source.get("enabled", True) for source in plan_sources),
                    "settings_json": {},
                },
            )

    @staticmethod
    def _config_version(code, stage, payload):
        config, _ = PipelineConfig.objects.get_or_create(code=code, defaults={"stage": stage})
        if config.stage != stage:
            raise CommandError(f"PipelineConfig {code} pertenece a otra etapa")
        latest = config.versions.order_by("-version").first()
        matching = (
            config.versions.filter(status=PipelineConfigVersion.Status.PUBLISHED)
            .order_by("-version")
            .first()
        )
        if matching is not None and matching.content_json == payload:
            return matching
        return PipelineConfigVersion.objects.create(
            pipeline_config=config,
            version=1 if latest is None else latest.version + 1,
            content_json=payload,
            status=PipelineConfigVersion.Status.PUBLISHED,
        )

    @staticmethod
    def _profile_version(profile, versions):
        active = profile.active_version
        if active is not None:
            active_versions = {
                item.stage: item.config_version_id for item in active.stages.all()
            }
            if active_versions == {stage: version.id for stage, version in versions.items()}:
                return active
        latest_number = (
            profile.versions.order_by("-version").values_list("version", flat=True).first()
        )
        return PipelineProfileVersion.objects.create(
            profile=profile,
            version=(latest_number or 0) + 1,
            description="Perfil inicial actualizado desde la configuración versionada",
        )
