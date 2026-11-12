import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.market.models import Provider
from apps.pipeline.application.importers import DatasetImportError, import_provider_datasets
from apps.pipeline.application.publication import PublicationError, publish_provider_run
from apps.pipeline.management.support import resolve_profile_version
from apps.pipeline.models import PipelineConfig, PipelineRun, ProviderRun, StageRun
from data_pipeline.files import DatasetIOError, read_dataset
from data_transformation import parse_feature_rules, transform_dataset


class Command(BaseCommand):
    help = "Importa planes/features/reviews normalizados sin persistir features-wide"

    def add_arguments(self, parser):
        parser.add_argument("input", type=Path)
        parser.add_argument("--profile", required=True)
        parser.add_argument("--provider", action="append", default=[])
        parser.add_argument("--publish", action="store_true")

    def handle(self, *args, **options):
        root = options["input"]
        required = {name: root / f"{name}.csv" for name in ("plans", "features", "reviews")}
        missing = [str(path) for path in required.values() if not path.is_file()]
        if missing:
            raise CommandError(f"Faltan entradas normalizadas: {', '.join(missing)}")
        profile_version, _ = resolve_profile_version(profile_code=options["profile"])
        run = PipelineRun.objects.create(
            profile_version=profile_version,
            trigger_type=PipelineRun.TriggerType.REPROCESS,
            status=PipelineRun.Status.RUNNING,
            started_at=timezone.now(),
        )
        try:
            plans = read_dataset(required["plans"])
            features = read_dataset(required["features"])
            reviews = read_dataset(required["reviews"])
            rules_stage = profile_version.stages.select_related(
                "config_version__pipeline_config"
            ).get(config_version__pipeline_config__stage=PipelineConfig.Stage.FEATURE_EQUIVALENCE)
            transformed_features = transform_dataset(
                features,
                "feature",
                feature_rules=parse_feature_rules(rules_stage.config_version.content_json),
                run_id=str(run.id),
            )
            quality_path = root / "quality-report.json"
            reports = (
                json.loads(quality_path.read_text(encoding="utf-8"))
                if quality_path.is_file()
                else []
            )
            codes = set(plans["competidor_id"].astype(str))
            if options["provider"]:
                codes &= set(options["provider"])
            providers = list(
                Provider.objects.filter(
                    code__in=codes,
                    is_active=True,
                    data_scope=Provider.DataScope.REAL,
                ).order_by("execution_order", "id")
            )
            missing_providers = sorted(codes - {item.code for item in providers})
            if missing_providers:
                raise CommandError(
                    f"Proveedores activos inexistentes: {', '.join(missing_providers)}"
                )
            for sequence, provider in enumerate(providers, start=1):
                provider_run = ProviderRun.objects.create(
                    pipeline_run=run,
                    provider=provider,
                    sequence=sequence,
                    status=PipelineRun.Status.RUNNING,
                    started_at=timezone.now(),
                )
                for stage_sequence, stage in enumerate(
                    (StageRun.Stage.PLANS, StageRun.Stage.FEATURES, StageRun.Stage.REVIEWS),
                    start=1,
                ):
                    StageRun.objects.create(
                        provider_run=provider_run,
                        stage=stage,
                        sequence=stage_sequence,
                        status=StageRun.Status.SUCCEEDED,
                        finished_at=timezone.now(),
                    )
                import_provider_datasets(
                    provider_run=provider_run,
                    plans=plans,
                    features=transformed_features.data,
                    feature_values=transformed_features.feature_values,
                    reviews=reviews,
                    quality_reports=reports,
                )
                if options["publish"]:
                    publish_provider_run(provider_run)
                else:
                    provider_run.status = PipelineRun.Status.COMPLETED
                    provider_run.is_complete = True
                    provider_run.finished_at = timezone.now()
                    provider_run.save(update_fields=("status", "is_complete", "finished_at"))
        except (DatasetIOError, DatasetImportError, PublicationError, ValueError) as exc:
            run.status = PipelineRun.Status.FAILED
            run.finished_at = timezone.now()
            run.error_summary = f"{type(exc).__name__}: {exc}"[:2000]
            run.save(update_fields=("status", "finished_at", "error_summary"))
            raise CommandError(str(exc)) from exc
        if not options["publish"]:
            run.status = PipelineRun.Status.COMPLETED
            run.finished_at = timezone.now()
            run.save(update_fields=("status", "finished_at"))
        else:
            run.refresh_from_db(fields=("status", "published_at", "finished_at"))
        self.stdout.write(self.style.SUCCESS(f"{run.id} status={run.status}"))
