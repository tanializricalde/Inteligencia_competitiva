from __future__ import annotations

import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.pipeline.models import PipelineConfig, PipelineConfigVersion
from data_pipeline.files import write_json_report
from data_transformation.feature_rules import FeatureRulesConfigError, parse_feature_rules


def load_config_document(path: str | Path) -> dict:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"No se pudo leer la configuración {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("La configuración debe contener un objeto JSON raíz")
    return payload


def validate_config_document(*, stage: str, payload: dict) -> PipelineConfigVersion:
    if stage == PipelineConfig.Stage.FEATURE_EQUIVALENCE:
        try:
            parse_feature_rules(payload)
        except FeatureRulesConfigError as exc:
            raise ValidationError(str(exc)) from exc
    config = PipelineConfig(code="validation", stage=stage)
    version = PipelineConfigVersion(
        pipeline_config=config,
        version=1,
        content_json=payload,
    )
    version.clean()
    return version


@transaction.atomic
def import_config_version(
    *, code: str, stage: str, version: int, payload: dict
) -> PipelineConfigVersion:
    config, _ = PipelineConfig.objects.get_or_create(code=code, defaults={"stage": stage})
    if config.stage != stage:
        raise ValidationError(f"{code} ya existe para la etapa {config.stage}")
    item = PipelineConfigVersion(
        pipeline_config=config,
        version=version,
        content_json=payload,
        status=PipelineConfigVersion.Status.DRAFT,
    )
    item.save()
    return item


@transaction.atomic
def publish_config_version(*, code: str, version: int) -> PipelineConfigVersion:
    item = PipelineConfigVersion.objects.select_for_update().get(
        pipeline_config__code=code,
        version=version,
    )
    if item.status == PipelineConfigVersion.Status.PUBLISHED:
        return item
    if item.status != PipelineConfigVersion.Status.DRAFT:
        raise ValidationError("Sólo una configuración en borrador puede publicarse")
    item.status = PipelineConfigVersion.Status.PUBLISHED
    item.save()
    return item


def export_config_version(
    *, code: str, version: int, output: str | Path, overwrite: bool = False
) -> Path:
    item = PipelineConfigVersion.objects.get(
        pipeline_config__code=code,
        version=version,
    )
    return write_json_report(item.content_json, output, overwrite=overwrite)
