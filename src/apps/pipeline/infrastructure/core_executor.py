from __future__ import annotations

import json
import time
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pandas as pd
from django.utils import timezone

from apps.pipeline.application.importers import import_provider_datasets
from apps.pipeline.application.orchestrator import SourceExecutionResult
from apps.pipeline.infrastructure.artifacts import PipelineArtifactStore
from apps.pipeline.models import (
    MarketSource,
    PipelineConfig,
    PipelineRun,
    ProviderRun,
    RunArtifact,
    SourceRun,
    StageRun,
)
from data_cleaning import clean_dataset
from data_pipeline.scraping_schemas import PLAN_FEATURE_FIELDS, map_plan, map_review
from data_transformation import parse_feature_rules, transform_dataset
from scraping_core.plans import PlanSourceDTO
from scraping_core.registry import get_plan_adapter, get_review_adapter
from scraping_core.reviews import ReviewSourceDTO


def _json_scalar(value: Any):
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "item"):
        return value.item()
    return value


def _frame_bytes(frame: pd.DataFrame) -> bytes:
    records = [
        {str(key): _json_scalar(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]
    return (json.dumps(records, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def _report_payload(report) -> dict:
    return report.as_dict() if hasattr(report, "as_dict") else dict(report)


class DjangoCorePipelineExecutor:
    """Runs pure cores and persists only their files and final validated outputs."""

    FEATURE_ADAPTER_KEY = "pipeline_features"

    def __init__(self, artifact_store: PipelineArtifactStore | None = None) -> None:
        self.artifacts = artifact_store or PipelineArtifactStore()

    def execute(self, source: MarketSource, *, pipeline_run: PipelineRun) -> SourceExecutionResult:
        provider_run, stage_run = self._current_runs(source, pipeline_run)
        if source.data_type == MarketSource.DataType.PLANS:
            return self._plans(source, pipeline_run, provider_run, stage_run)
        if source.data_type == MarketSource.DataType.FEATURES:
            if source.adapter_key != self.FEATURE_ADAPTER_KEY:
                raise ValueError(f"Adapter de características no soportado: {source.adapter_key!r}")
            return self._features(source, pipeline_run, provider_run, stage_run)
        return self._reviews(source, pipeline_run, provider_run, stage_run)

    def _plans(self, source, pipeline_run, provider_run, stage_run):
        settings = source.settings_json
        adapter = get_plan_adapter(source.adapter_key)
        scraped = adapter.scrape(
            PlanSourceDTO(
                id=source.id,
                url=source.url,
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
                retry_limit=int(settings.get("retry_limit", 2)),
                config=settings.get("adapter_config", {}),
            )
        )[: int(settings.get("max_items", 1000))]
        plan_rows = []
        feature_rows = []
        ingested_at = timezone.now()
        for plan in scraped:
            row, rows = map_plan(
                plan,
                provider_code=source.provider.code,
                provider_name=source.provider.name,
                ingested_at=ingested_at,
            )
            plan_rows.append(row)
            feature_rows.extend(rows)
        plans = transform_dataset(clean_dataset(pd.DataFrame(plan_rows), "plan").data, "plan")
        prefix = self._prefix(pipeline_run, source, "plans")
        artifact = self._store_frame(
            pipeline_run,
            provider_run,
            stage_run,
            f"{prefix}/{source.code}-plans.json",
            plans.data,
        )
        self._store_frame(
            pipeline_run,
            provider_run,
            stage_run,
            f"{prefix}/{source.code}-raw-features.json",
            pd.DataFrame(feature_rows, columns=PLAN_FEATURE_FIELDS),
        )
        return SourceExecutionResult(
            rows_scraped=len(scraped),
            rows_cleaned=plans.input_rows,
            rows_normalized=plans.output_rows,
            content_sha256=artifact.content_sha256,
        )

    def _features(self, source, pipeline_run, provider_run, stage_run):
        frames = self._artifact_frames(
            pipeline_run,
            source.provider.code,
            suffix="-raw-features.json",
        )
        raw = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=PLAN_FEATURE_FIELDS)
        )
        cleaned = clean_dataset(raw, "feature")
        rules = self._feature_rules(pipeline_run)
        transformed = transform_dataset(
            cleaned.data,
            "feature",
            feature_rules=rules,
            run_id=str(pipeline_run.id),
        )
        prefix = self._prefix(pipeline_run, source, "features")
        artifact = self._store_frame(
            pipeline_run,
            provider_run,
            stage_run,
            f"{prefix}/features.json",
            transformed.data,
        )
        self._store_frame(
            pipeline_run,
            provider_run,
            stage_run,
            f"{prefix}/feature-values.json",
            transformed.feature_values,
        )
        self._store_json(
            pipeline_run,
            provider_run,
            stage_run,
            f"{prefix}/quality-report.json",
            transformed.report.as_dict(),
            RunArtifact.ArtifactType.QUALITY_REPORT,
        )
        self._store_json(
            pipeline_run,
            provider_run,
            stage_run,
            f"{prefix}/feature-rules-report.json",
            transformed.feature_rules_report.as_dict(),
            RunArtifact.ArtifactType.FEATURE_RULES_REPORT,
        )
        return SourceExecutionResult(
            rows_scraped=len(raw),
            rows_cleaned=cleaned.output_rows,
            rows_normalized=transformed.output_rows,
            content_sha256=artifact.content_sha256,
        )

    def _reviews(self, source, pipeline_run, provider_run, stage_run):
        settings = source.settings_json
        maximum = int(settings.get("max_items", 1000))
        max_pages = int(settings.get("max_pages", 100))
        delay = float(settings.get("request_delay_seconds", 0))
        dto = ReviewSourceDTO(
            id=source.id,
            provider_code=source.provider.code,
            platform=source.platform_code or settings.get("platform", "unknown"),
            source_url=source.url,
            external_entity_id=settings.get("external_entity_id"),
            country_code=source.country_code,
            timeout_seconds=int(settings.get("timeout_seconds", 60)),
            retry_limit=int(settings.get("retry_limit", 2)),
            request_delay_seconds=delay,
            max_items=maximum,
            adapter_config=settings.get("adapter_config", {}),
        )
        adapter = get_review_adapter(source.adapter_key)
        adapter.validate_config(dto)
        checkpoint = None
        reviews = []
        warnings = []
        ingested_at = timezone.now()
        for _page in range(max_pages):
            batch = adapter.scrape(dto, checkpoint)
            warnings.extend(batch.warnings)
            for review in batch.reviews:
                if len(reviews) >= maximum:
                    break
                if review.app_id is None and dto.external_entity_id is not None:
                    review = replace(review, app_id=dto.external_entity_id)
                reviews.append(
                    map_review(
                        review,
                        provider_code=source.provider.code,
                        source_name=source.code,
                        ingested_at=ingested_at,
                    )
                )
            if len(reviews) >= maximum or not batch.has_more:
                break
            if batch.next_checkpoint is None:
                raise RuntimeError("El adapter indicó más páginas sin checkpoint")
            checkpoint = batch.next_checkpoint
            if delay:
                time.sleep(delay)
        else:
            raise RuntimeError(f"Se alcanzó max_pages={max_pages}")
        transformed = transform_dataset(
            clean_dataset(pd.DataFrame(reviews), "review").data,
            "review",
        )
        prefix = self._prefix(pipeline_run, source, "reviews")
        artifact = self._store_frame(
            pipeline_run,
            provider_run,
            stage_run,
            f"{prefix}/{source.code}-reviews.json",
            transformed.data,
        )
        return SourceExecutionResult(
            rows_scraped=len(reviews),
            rows_cleaned=transformed.input_rows,
            rows_normalized=transformed.output_rows,
            content_sha256=artifact.content_sha256,
            metadata={"warnings": warnings},
        )

    def finalize_provider(self, provider_run: ProviderRun) -> None:
        run = provider_run.pipeline_run
        provider_code = provider_run.provider.code
        plans = self._concat_artifacts(run, provider_code, suffix="-plans.json")
        features = self._concat_artifacts(run, provider_code, suffix="/features.json")
        feature_values = self._concat_artifacts(run, provider_code, suffix="/feature-values.json")
        reviews = self._concat_artifacts(run, provider_code, suffix="-reviews.json")
        reports = self._json_artifacts(run, provider_code, suffix="/quality-report.json")
        source_runs = {
            item.market_source.data_type: item
            for stage in provider_run.stage_runs.all()
            for item in stage.source_runs.filter(status=StageRun.Status.SUCCEEDED)
        }
        import_provider_datasets(
            provider_run=provider_run,
            plans=plans,
            features=features,
            feature_values=feature_values,
            reviews=reviews,
            quality_reports=reports,
            plan_source_run=source_runs.get(MarketSource.DataType.PLANS),
            feature_source_run=source_runs.get(MarketSource.DataType.FEATURES),
            review_source_run=source_runs.get(MarketSource.DataType.REVIEWS),
        )

    def _feature_rules(self, pipeline_run):
        stage = pipeline_run.profile_version.stages.select_related(
            "config_version__pipeline_config"
        ).get(config_version__pipeline_config__stage=PipelineConfig.Stage.FEATURE_EQUIVALENCE)
        return parse_feature_rules(stage.config_version.content_json)

    def _current_runs(self, source, pipeline_run):
        provider_run = ProviderRun.objects.get(
            pipeline_run=pipeline_run,
            provider=source.provider,
        )
        source_run = SourceRun.objects.select_related("stage_run").get(
            stage_run__provider_run=provider_run,
            market_source=source,
        )
        return provider_run, source_run.stage_run

    @staticmethod
    def _prefix(pipeline_run, source, stage):
        return f"{pipeline_run.id}/{source.provider.code}/{stage}"

    def _store_frame(self, run, provider_run, stage_run, path, frame):
        return self.artifacts.store_bytes(
            pipeline_run=run,
            provider_run=provider_run,
            stage_run=stage_run,
            artifact_type=RunArtifact.ArtifactType.NORMALIZED,
            relative_path=path,
            content=_frame_bytes(frame),
        )

    def _store_json(self, run, provider_run, stage_run, path, payload, artifact_type):
        content = (json.dumps(payload, ensure_ascii=False, default=str) + "\n").encode()
        return self.artifacts.store_bytes(
            pipeline_run=run,
            provider_run=provider_run,
            stage_run=stage_run,
            artifact_type=artifact_type,
            relative_path=path,
            content=content,
        )

    def _artifact_frames(self, run, provider_code, *, suffix):
        return [
            pd.DataFrame(json.loads(self.artifacts.resolve(path).read_text(encoding="utf-8")))
            for path in RunArtifact.objects.filter(
                pipeline_run=run,
                relative_path__startswith=f"{run.id}/{provider_code}/",
                relative_path__endswith=suffix,
            ).values_list("relative_path", flat=True)
        ]

    def _concat_artifacts(self, run, provider_code, *, suffix):
        frames = self._artifact_frames(run, provider_code, suffix=suffix)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _json_artifacts(self, run, provider_code, *, suffix):
        payloads = []
        for path in RunArtifact.objects.filter(
            pipeline_run=run,
            relative_path__startswith=f"{run.id}/{provider_code}/",
            relative_path__endswith=suffix,
        ).values_list("relative_path", flat=True):
            payload = json.loads(self.artifacts.resolve(path).read_text(encoding="utf-8"))
            payloads.extend(payload if isinstance(payload, list) else [payload])
        return payloads
