"""Shared mappings from pure scraping DTOs to public tabular contracts."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from scraping_core.plans import FeatureState, Periodicity, ScrapedPlanDTO
from scraping_core.reviews import ScrapedReviewDTO, response_days, stable_review_id

PLANS_SCHEMA = "plans_v2"
PLAN_FEATURES_SCHEMA = "plan_features_v1"
REVIEWS_SCHEMA = "reviews_v1"

PLAN_FIELDS = (
    "timestamp_utc",
    "competidor_id",
    "competidor_nombre",
    "plan_id",
    "plan_nombre",
    "producto",
    "moneda",
    "precio_mensual",
    "precio_anual_total",
    "precio_mensual_efectivo",
    "descuento_anual_pct",
    "es_oferta_activa",
    "promocion_texto",
    "url_fuente",
)
PLAN_FEATURE_FIELDS = (
    "plan_id",
    "competidor_id",
    "categoria_modulo",
    "nombre_modulo",
    "incluido",
    "costo_adicional",
)
REVIEW_FIELDS = (
    "review_id",
    "competidor_id",
    "app_id",
    "plataforma",
    "pais_codigo",
    "fecha_comentario",
    "usuario_nombre",
    "calificacion_estrellas",
    "comentario_cliente",
    "version_app",
    "likes_comentario",
    "categoria_tema",
    "sentimiento",
    "tiene_respuesta",
    "fecha_respuesta",
    "respuesta_desarrollador",
    "dias_para_responder",
    "timestamp_ingesta",
)


def _utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Las fechas exportadas deben incluir zona horaria")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _plan_id(provider_code: str, plan: ScrapedPlanDTO) -> str:
    if plan.external_id and plan.external_id.strip():
        return plan.external_id.strip()
    product = plan.product
    seed = (
        f"{provider_code}\0{product}\0{plan.normalized_name}\0{plan.source_url}"
        if product
        else f"{provider_code}\0{plan.normalized_name}\0{plan.source_url}"
    )
    return "generated-" + hashlib.sha256(seed.encode()).hexdigest()[:20]


def map_plan(
    plan: ScrapedPlanDTO,
    *,
    provider_code: str,
    provider_name: str,
    ingested_at: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plan_id = _plan_id(provider_code, plan)
    monthly = plan.monthly_price
    annual = plan.annual_total_price
    if monthly is None and plan.periodicity == Periodicity.MONTHLY:
        monthly = plan.price_after_discount if plan.price_after_discount is not None else plan.price
    if annual is None and plan.periodicity == Periodicity.YEARLY:
        annual = plan.price_after_discount if plan.price_after_discount is not None else plan.price
    effective = plan.effective_monthly_price
    if effective is None and annual is not None:
        effective = annual / Decimal(12)
    elif effective is None:
        effective = plan.price_after_discount
    row = {
        "timestamp_utc": _utc(ingested_at),
        "competidor_id": provider_code,
        "competidor_nombre": provider_name,
        "plan_id": plan_id,
        "plan_nombre": plan.original_name,
        "producto": plan.product,
        "moneda": plan.currency,
        "precio_mensual": monthly,
        "precio_anual_total": annual,
        "precio_mensual_efectivo": effective,
        "descuento_anual_pct": plan.discount_percentage,
        "es_oferta_activa": plan.is_offer_active,
        "promocion_texto": plan.promotion_text,
        "url_fuente": plan.source_url,
    }
    features: list[dict[str, Any]] = []
    for key, value in plan.normalized_features.items():
        state = value.get("state")
        included = None
        if state in {FeatureState.OFFERED, FeatureState.OFFERED.value}:
            included = True
        elif state in {FeatureState.NOT_OFFERED, FeatureState.NOT_OFFERED.value}:
            included = False
        features.append(
            {
                "plan_id": plan_id,
                "competidor_id": provider_code,
                "categoria_modulo": value.get("category"),
                "nombre_modulo": value.get("original") or key,
                "incluido": included,
                "costo_adicional": value.get("additional_cost"),
            }
        )
    return row, features


def map_review(
    review: ScrapedReviewDTO,
    *,
    provider_code: str,
    source_name: str,
    ingested_at: datetime,
) -> dict[str, Any]:
    review_id, _ = stable_review_id(
        f"{provider_code}:{source_name}",
        review.external_review_id,
        {
            "author": review.author_name,
            "published_at": _utc(review.published_at),
            "text": review.review_text,
            "source_url": review.source_url,
        },
    )
    has_response = None
    if review.response_known is True:
        has_response = bool(review.developer_response_text or review.developer_response_at)
    return {
        "review_id": review_id,
        "competidor_id": provider_code,
        "app_id": review.app_id,
        "plataforma": review.platform,
        "pais_codigo": review.country_code,
        "fecha_comentario": _utc(review.published_at),
        "usuario_nombre": review.author_name,
        "calificacion_estrellas": review.rating,
        "comentario_cliente": review.review_text,
        "version_app": review.app_version,
        "likes_comentario": review.helpful_votes,
        "categoria_tema": None,
        "sentimiento": None,
        "tiene_respuesta": has_response,
        "fecha_respuesta": _utc(review.developer_response_at),
        "respuesta_desarrollador": review.developer_response_text,
        "dias_para_responder": response_days(review.published_at, review.developer_response_at),
        "timestamp_ingesta": _utc(ingested_at),
    }
