from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from numbers import Real
from typing import Any

import pandas as pd
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.pipeline.models import (
    FeatureDefinition,
    MarketPlan,
    MarketReview,
    PlanFeatureSource,
    PlanFeatureValue,
    PlanFeatureValueSource,
    PlanPriceSnapshot,
    PlanSnapshot,
    ProviderRun,
    QualityIssue,
    ReviewSnapshot,
    SourceRun,
    canonical_json_hash,
)


class DatasetImportError(ValueError):
    """Raised before publishing when a normalized dataset is inconsistent."""


@dataclass(frozen=True, slots=True)
class ProviderImportResult:
    plans: int
    feature_sources: int
    feature_values: int
    reviews: int
    quality_issues: int


def _missing(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _value(value: Any, default=None):
    return default if _missing(value) or value == "" else value


def _text(value: Any, default: str = "") -> str:
    return str(_value(value, default))


def _first(*values: Any, default=None):
    for value in values:
        resolved = _value(value)
        if resolved is not None:
            return resolved
    return default


def _bool(value: Any) -> bool | None:
    value = _value(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    # JSON/Pandas promote nullable integer/boolean columns to floats. Accept
    # only the two exact binary values; arbitrary truthy numbers remain data
    # errors instead of being silently coerced.
    if isinstance(value, (Real, Decimal)):
        if value == 1:
            return True
        if value == 0:
            return False
        raise DatasetImportError(f"Booleano inválido: {value!r}")
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "si", "sí"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise DatasetImportError(f"Booleano inválido: {value!r}")


def _decimal(value: Any) -> Decimal | None:
    value = _value(value)
    return None if value is None else Decimal(str(value))


def _datetime(value: Any, *, default: datetime | None = None) -> datetime:
    value = _value(value)
    if value is None:
        return default or timezone.now()
    parsed = value if isinstance(value, datetime) else parse_datetime(str(value))
    if parsed is None or timezone.is_naive(parsed):
        raise DatasetImportError(f"Timestamp ISO-8601 con zona requerido: {value!r}")
    return parsed


def _rows(frame: pd.DataFrame | None, provider_code: str):
    if frame is None or frame.empty:
        return []
    if "competidor_id" not in frame:
        raise DatasetImportError("El dataset requiere la columna competidor_id")
    return frame.loc[frame["competidor_id"].astype(str) == provider_code].to_dict(orient="records")


def _source_row_key(row: dict[str, Any]) -> str:
    payload = {
        "plan_id": _text(row.get("plan_id")),
        "categoria_modulo": _value(row.get("categoria_modulo")),
        "nombre_modulo": _text(row.get("nombre_modulo")),
        "nombre_modulo_normalizado": _text(row.get("nombre_modulo_normalizado")),
        "incluido": _bool(row.get("incluido")),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


@transaction.atomic
def import_provider_datasets(
    *,
    provider_run: ProviderRun,
    plans: pd.DataFrame,
    features: pd.DataFrame | None = None,
    feature_values: pd.DataFrame | None = None,
    reviews: pd.DataFrame | None = None,
    quality_reports: list[dict[str, Any]] | None = None,
    plan_source_run: SourceRun | None = None,
    feature_source_run: SourceRun | None = None,
    review_source_run: SourceRun | None = None,
) -> ProviderImportResult:
    provider = provider_run.provider
    if provider.data_scope != "real":
        raise DatasetImportError("El pipeline operativo sólo puede importar proveedores REAL")
    plan_rows = _rows(plans, provider.code)
    feature_rows = _rows(features, provider.code)
    value_rows = _rows(feature_values, provider.code)
    review_rows = _rows(reviews, provider.code)
    observed_at = provider_run.started_at or timezone.now()

    snapshots: dict[str, PlanSnapshot] = {}
    for row in plan_rows:
        external_key = _text(row.get("plan_id"))
        if not external_key:
            raise DatasetImportError("plan_id no puede estar vacío")
        row_observed_at = _datetime(row.get("timestamp_utc"), default=observed_at)
        market_plan, _ = MarketPlan.objects.get_or_create(
            provider=provider,
            external_key=external_key,
            defaults={"first_seen_at": row_observed_at, "last_seen_at": row_observed_at},
        )
        if market_plan.last_seen_at < row_observed_at:
            market_plan.last_seen_at = row_observed_at
            market_plan.is_active = True
            market_plan.save(update_fields=("last_seen_at", "is_active"))
        snapshot, _ = PlanSnapshot.objects.update_or_create(
            provider_run=provider_run,
            market_plan=market_plan,
            defaults={
                "source_run": plan_source_run,
                "observed_at": row_observed_at,
                "plan_name": _text(row.get("plan_nombre")),
                "normalized_name": _text(row.get("plan_nombre_normalizado")),
                "product_code": _text(row.get("producto")),
                "source_url": _text(row.get("url_fuente")),
                "promotion_text": _value(row.get("promocion_texto")),
                "is_offer_active": _bool(row.get("es_oferta_activa")),
                "metadata_json": {
                    "price_inconsistent": _bool(row.get("precio_inconsistente_bandera")),
                    "monthly_difference": _value(row.get("diferencia_mensual")),
                    "monthly_difference_percentage": _value(
                        row.get("diferencia_mensual_porcentaje")
                    ),
                },
            },
        )
        snapshots[external_key] = snapshot
        PlanPriceSnapshot.objects.filter(plan_snapshot=snapshot).delete()
        currency = _text(_first(row.get("moneda_codigo"), row.get("moneda"), default="USD"))
        monthly = _decimal(row.get("precio_mensual"))
        annual = _decimal(row.get("precio_anual_total"))
        calculated = _decimal(row.get("precio_mensual_calculado"))
        if monthly is not None:
            PlanPriceSnapshot.objects.create(
                plan_snapshot=snapshot,
                billing_period=PlanPriceSnapshot.BillingPeriod.MONTHLY,
                currency_code=currency,
                amount=monthly,
                effective_monthly_amount=monthly,
                discount_percentage=_decimal(row.get("descuento_anual_pct")),
                is_promotional=_bool(row.get("es_oferta_activa")) or False,
                source_kind=PlanPriceSnapshot.SourceKind.SCRAPED,
            )
        if annual is not None:
            PlanPriceSnapshot.objects.create(
                plan_snapshot=snapshot,
                billing_period=PlanPriceSnapshot.BillingPeriod.ANNUAL,
                currency_code=currency,
                amount=annual,
                effective_monthly_amount=_decimal(row.get("precio_mensual_efectivo")),
                discount_percentage=_decimal(row.get("descuento_anual_pct")),
                is_promotional=_bool(row.get("es_oferta_activa")) or False,
                source_kind=PlanPriceSnapshot.SourceKind.SCRAPED,
            )
        if calculated is not None and calculated != monthly:
            PlanPriceSnapshot.objects.create(
                plan_snapshot=snapshot,
                billing_period=PlanPriceSnapshot.BillingPeriod.MONTHLY,
                currency_code=currency,
                amount=calculated,
                effective_monthly_amount=calculated,
                source_kind=PlanPriceSnapshot.SourceKind.CALCULATED,
            )

    source_by_plan: dict[str, list[PlanFeatureSource]] = {}
    source_by_normalized: dict[tuple[str, str], list[PlanFeatureSource]] = {}
    for row in feature_rows:
        plan_id = _text(row.get("plan_id"))
        snapshot = snapshots.get(plan_id)
        if snapshot is None:
            raise DatasetImportError(f"Característica huérfana para plan_id={plan_id!r}")
        source, _ = PlanFeatureSource.objects.update_or_create(
            plan_snapshot=snapshot,
            source_row_key=_source_row_key(row),
            defaults={
                "source_run": feature_source_run,
                "category": _value(row.get("categoria_modulo")),
                "raw_name": _text(row.get("nombre_modulo")),
                "normalized_name": _text(row.get("nombre_modulo_normalizado")),
                "included": _bool(row.get("incluido")),
            },
        )
        source_by_plan.setdefault(plan_id, []).append(source)
        source_by_normalized.setdefault((plan_id, source.normalized_name), []).append(source)

    definitions: dict[tuple[str, str], FeatureDefinition] = {}
    for row in value_rows:
        plan_id = _text(row.get("plan_id"))
        snapshot = snapshots.get(plan_id)
        if snapshot is None:
            raise DatasetImportError(f"Valor de característica huérfano: {plan_id!r}")
        run_id = _value(row.get("run_id"))
        if run_id is not None and str(run_id) != str(provider_run.pipeline_run_id):
            raise DatasetImportError("feature-values pertenece a otro pipeline_run")
        code = _text(row.get("feature_code"))
        origin = _text(row.get("origin"))
        scope = (
            FeatureDefinition.Scope.PROVIDER
            if origin == PlanFeatureValue.Origin.FALLBACK
            else FeatureDefinition.Scope.CANONICAL
        )
        definition_key = (scope, code)
        definition = definitions.get(definition_key)
        if definition is None:
            definition, created = FeatureDefinition.objects.get_or_create(
                code=code,
                scope=scope,
                provider=provider if scope == FeatureDefinition.Scope.PROVIDER else None,
                defaults={
                    "display_name": code.replace("_", " ").capitalize(),
                    "data_type": _text(row.get("value_type")),
                    "origin": (
                        FeatureDefinition.Origin.FALLBACK
                        if scope == FeatureDefinition.Scope.PROVIDER
                        else FeatureDefinition.Origin.CONFIGURED
                    ),
                    "is_active": True,
                },
            )
            if not created and definition.data_type != _text(row.get("value_type")):
                raise DatasetImportError(
                    f"FeatureDefinition {code!r} cambió de tipo "
                    f"{definition.data_type!r} a {_text(row.get('value_type'))!r}"
                )
            definitions[definition_key] = definition
        raw_json = _value(row.get("value_json"))
        typed_values = {
            "value_boolean": _bool(row.get("value_boolean")),
            "value_integer": _value(row.get("value_integer")),
            "value_decimal": _decimal(row.get("value_decimal")),
            "value_text": _value(row.get("value_text")),
            "value_json": json.loads(raw_json) if isinstance(raw_json, str) else raw_json,
        }
        value, _ = PlanFeatureValue.objects.update_or_create(
            plan_snapshot=snapshot,
            feature_definition=definition,
            defaults={
                **typed_values,
                "availability": _text(row.get("availability")),
                "origin": origin,
                "source_rule_id": _value(row.get("rule_id")),
                "is_derived": _bool(row.get("is_derived")) or False,
                "metadata_json": {},
            },
        )
        PlanFeatureValueSource.objects.filter(plan_feature_value=value).delete()
        candidates = (
            source_by_normalized.get((plan_id, code), [])
            if origin == PlanFeatureValue.Origin.FALLBACK
            else source_by_plan.get(plan_id, [])
        )
        if candidates and origin != PlanFeatureValue.Origin.DEFAULT:
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
            if origin != PlanFeatureValue.Origin.FALLBACK:
                value.metadata_json = {"trace_scope": "plan_candidate_rows"}
                value.save(update_fields=("metadata_json",))

    for row in review_rows:
        external_id = _text(row.get("review_id"))
        if not external_id:
            raise DatasetImportError("review_id no puede estar vacío")
        ingested_at = _datetime(row.get("timestamp_ingesta"), default=observed_at)
        platform = _text(
            _first(row.get("plataforma_codigo"), row.get("plataforma"), default="unknown")
        )
        review, _ = MarketReview.objects.get_or_create(
            provider=provider,
            platform_code=platform,
            external_review_id=external_id,
            defaults={"first_seen_at": ingested_at, "last_seen_at": ingested_at},
        )
        if review.last_seen_at < ingested_at:
            review.last_seen_at = ingested_at
            review.is_active = True
            review.save(update_fields=("last_seen_at", "is_active"))
        content = {
            "country_code": _value(row.get("pais_codigo")),
            "user_name": _value(row.get("usuario_nombre")),
            "rating_stars": _value(row.get("calificacion_estrellas")),
            "customer_comment": _value(row.get("comentario_cliente")),
            "has_developer_response": _bool(row.get("tiene_respuesta")),
            "developer_response": _value(row.get("respuesta_desarrollador")),
            "sentiment_from_rating": _value(row.get("sentimiento_por_calificacion")),
            "days_to_respond": _decimal(row.get("dias_para_responder")),
        }
        ReviewSnapshot.objects.update_or_create(
            provider_run=provider_run,
            market_review=review,
            defaults={
                "source_run": review_source_run,
                **content,
                "ingested_at": ingested_at,
                "content_sha256": canonical_json_hash(content),
            },
        )

    imported_issues = import_quality_reports(
        provider_run=provider_run,
        reports=quality_reports or [],
    )
    return ProviderImportResult(
        plans=len(plan_rows),
        feature_sources=len(feature_rows),
        feature_values=len(value_rows),
        reviews=len(review_rows),
        quality_issues=imported_issues,
    )


def import_quality_reports(*, provider_run: ProviderRun, reports: list[dict[str, Any]]) -> int:
    QualityIssue.objects.filter(provider_run=provider_run).delete()
    issues: list[QualityIssue] = []
    for report in reports:
        dataset_type = _text(report.get("dataset_type"), "unknown")
        for raw_issue in report.get("issues", []):
            issues.append(
                QualityIssue(
                    pipeline_run=provider_run.pipeline_run,
                    provider_run=provider_run,
                    severity=QualityIssue.Severity.WARNING,
                    code=_text(raw_issue.get("code"), "pipeline-warning"),
                    message=_text(raw_issue.get("message")),
                    dataset_type=dataset_type,
                    column_name=_value(raw_issue.get("column")),
                    row_reference=(
                        None if _value(raw_issue.get("row")) is None else str(raw_issue.get("row"))
                    ),
                    value_json=raw_issue.get("value"),
                )
            )
    QualityIssue.objects.bulk_create(issues)
    return len(issues)
