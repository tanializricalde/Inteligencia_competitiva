"""Canonical profiles derived from the public scraper CLI schemas."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DatasetType(StrEnum):
    REVIEW = "review"
    PLAN = "plan"
    FEATURE = "feature"


@dataclass(frozen=True, slots=True)
class DatasetProfile:
    dataset_type: DatasetType
    fields: tuple[str, ...]
    required_columns: tuple[str, ...]
    signature: frozenset[str]
    identifier_columns: frozenset[str]
    text_columns: frozenset[str]
    integer_columns: frozenset[str]
    decimal_columns: frozenset[str]
    boolean_columns: frozenset[str]
    datetime_columns: frozenset[str]
    deduplication_key: tuple[str, ...]


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
FEATURE_FIELDS = (
    "plan_id",
    "competidor_id",
    "categoria_modulo",
    "nombre_modulo",
    "incluido",
    "costo_adicional",
)

PROFILES = {
    DatasetType.REVIEW: DatasetProfile(
        dataset_type=DatasetType.REVIEW,
        fields=REVIEW_FIELDS,
        required_columns=("review_id", "competidor_id"),
        signature=frozenset({"review_id", "comentario_cliente"}),
        identifier_columns=frozenset({"review_id", "competidor_id", "app_id"}),
        text_columns=frozenset(
            {
                "plataforma",
                "usuario_nombre",
                "comentario_cliente",
                "version_app",
                "categoria_tema",
                "sentimiento",
                "respuesta_desarrollador",
            }
        ),
        integer_columns=frozenset({"calificacion_estrellas", "likes_comentario"}),
        decimal_columns=frozenset({"dias_para_responder"}),
        boolean_columns=frozenset({"tiene_respuesta"}),
        datetime_columns=frozenset({"fecha_comentario", "fecha_respuesta", "timestamp_ingesta"}),
        deduplication_key=("review_id", "timestamp_ingesta"),
    ),
    DatasetType.PLAN: DatasetProfile(
        dataset_type=DatasetType.PLAN,
        fields=PLAN_FIELDS,
        required_columns=("timestamp_utc", "competidor_id", "plan_id", "plan_nombre"),
        signature=frozenset({"plan_id", "plan_nombre"}),
        identifier_columns=frozenset({"competidor_id", "plan_id"}),
        text_columns=frozenset(
            {
                "competidor_nombre",
                "plan_nombre",
                "producto",
                "promocion_texto",
                "url_fuente",
            }
        ),
        integer_columns=frozenset(),
        decimal_columns=frozenset(
            {
                "precio_mensual",
                "precio_anual_total",
                "precio_mensual_efectivo",
                "descuento_anual_pct",
            }
        ),
        boolean_columns=frozenset({"es_oferta_activa"}),
        datetime_columns=frozenset({"timestamp_utc"}),
        deduplication_key=("competidor_id", "plan_id", "timestamp_utc"),
    ),
    DatasetType.FEATURE: DatasetProfile(
        dataset_type=DatasetType.FEATURE,
        fields=FEATURE_FIELDS,
        required_columns=("plan_id", "competidor_id", "nombre_modulo"),
        signature=frozenset({"plan_id", "nombre_modulo"}),
        identifier_columns=frozenset({"plan_id", "competidor_id"}),
        text_columns=frozenset({"categoria_modulo", "nombre_modulo"}),
        integer_columns=frozenset(),
        decimal_columns=frozenset({"costo_adicional"}),
        boolean_columns=frozenset({"incluido"}),
        datetime_columns=frozenset(),
        deduplication_key=(
            "competidor_id",
            "plan_id",
            "categoria_modulo",
            "nombre_modulo",
        ),
    ),
}


def get_profile(dataset_type: DatasetType | str) -> DatasetProfile:
    try:
        resolved = DatasetType(dataset_type)
    except ValueError as exc:
        choices = ", ".join(item.value for item in DatasetType)
        raise ValueError(f"Tipo inválido {dataset_type!r}; opciones: {choices}") from exc
    return PROFILES[resolved]
