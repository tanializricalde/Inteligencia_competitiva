import csv
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from io import StringIO

from apps.pipeline.models import ReviewSnapshot

REVIEW_EXPORT_COLUMNS = (
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


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def review_export_row(review: ReviewSnapshot) -> dict[str, object]:
    return {
        "review_id": review.market_review.external_review_id,
        "competidor_id": review.provider_run.provider.code,
        "app_id": None,
        "plataforma": review.market_review.platform_code,
        "pais_codigo": review.country_code,
        "fecha_comentario": _iso(review.review_published_at),
        "usuario_nombre": review.user_name,
        "calificacion_estrellas": review.rating_stars,
        "comentario_cliente": review.customer_comment,
        "version_app": None,
        "likes_comentario": None,
        "categoria_tema": None,
        "sentimiento": review.sentiment_from_rating,
        "tiene_respuesta": (
            "TRUE"
            if review.has_developer_response is True
            else "FALSE"
            if review.has_developer_response is False
            else None
        ),
        "fecha_respuesta": _iso(review.response_published_at),
        "respuesta_desarrollador": review.developer_response,
        "dias_para_responder": _decimal(review.days_to_respond),
        "timestamp_ingesta": _iso(review.ingested_at),
    }


def export_reviews_csv(reviews: Iterable[ReviewSnapshot]) -> str:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=REVIEW_EXPORT_COLUMNS, extrasaction="raise")
    writer.writeheader()
    for review in reviews:
        row = {
            key: "" if value is None else value for key, value in review_export_row(review).items()
        }
        writer.writerow(row)
    return output.getvalue()


def export_reviews_json(reviews: Iterable[ReviewSnapshot]) -> str:
    rows = [review_export_row(review) for review in reviews]
    return json.dumps(rows, ensure_ascii=False, indent=2)
