import csv
import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from scraper_cli.exporters import OutputError, export_rows
from scraper_cli.schemas import PLAN_FIELDS, REVIEW_FIELDS, map_plan, map_review
from scraping_core.plans import Periodicity, ScrapedPlanDTO
from scraping_core.reviews import ScrapedReviewDTO

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _plan():
    return ScrapedPlanDTO(
        external_id="p1",
        original_name="Pro",
        normalized_name="Pro",
        price=Decimal("100"),
        currency="PEN",
        periodicity=Periodicity.YEARLY,
        price_text="S/ 100",
        original_features=["Soporte"],
        normalized_features={
            "support": {
                "state": "not_offered",
                "original": "Soporte",
                "category": "Ayuda",
                "additional_cost": "0",
            }
        },
        source_url="https://example.com/plans",
        raw_payload={},
        discount_percentage=Decimal("20"),
        price_after_discount=Decimal("80"),
        is_offer_active=False,
        product="contabilidad",
    )


def test_plan_mapping_matches_authoritative_order_and_discount_fields():
    row, features = map_plan(
        _plan(), provider_code="competidor", provider_name="Competidor", ingested_at=NOW
    )

    assert tuple(row) == PLAN_FIELDS
    assert row["precio_anual_total"] == Decimal("80")
    assert row["precio_mensual_efectivo"] == Decimal("80") / 12
    assert row["descuento_anual_pct"] == Decimal("20")
    assert row["es_oferta_activa"] is False
    assert row["producto"] == "contabilidad"
    assert features[0]["incluido"] is False
    assert features[0]["costo_adicional"] == "0"


def test_review_mapping_preserves_zero_false_unicode_and_pending_enrichment(tmp_path):
    review = ScrapedReviewDTO(
        external_review_id="r1",
        app_id="app",
        platform="store",
        country_code="PE",
        published_at=NOW,
        author_name="Ángela",
        rating=0,
        review_text='Línea 1, "bien"\nLínea 2 🚀',
        app_version=None,
        helpful_votes=0,
        developer_response_text=None,
        developer_response_at=None,
        source_url="https://example.com/reviews",
        response_known=True,
    )
    row = map_review(review, provider_code="comp", source_name="source", ingested_at=NOW)

    assert tuple(row) == REVIEW_FIELDS
    assert row["likes_comentario"] == 0
    assert row["tiene_respuesta"] is False
    assert row["categoria_tema"] is None
    assert row["sentimiento"] is None

    csv_path = tmp_path / "reviews.csv"
    json_path = tmp_path / "reviews.json"
    export_rows([row], REVIEW_FIELDS, output_format="csv", output=csv_path)
    export_rows([row], REVIEW_FIELDS, output_format="json", output=json_path)
    with csv_path.open(encoding="utf-8", newline="") as stream:
        parsed = next(csv.DictReader(stream))
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert parsed["comentario_cliente"] == review.review_text
    assert parsed["likes_comentario"] == "0"
    assert parsed["tiene_respuesta"] == "FALSE"
    assert parsed["sentimiento"] == ""
    assert payload[0]["comentario_cliente"] == review.review_text
    assert payload[0]["likes_comentario"] == 0
    assert payload[0]["tiene_respuesta"] is False
    assert payload[0]["sentimiento"] is None


def test_export_is_no_clobber_and_rejects_wrong_contract(tmp_path):
    target = tmp_path / "data.json"
    target.write_text("original", encoding="utf-8")

    with pytest.raises(OutputError, match="--overwrite"):
        export_rows([], REVIEW_FIELDS, output_format="json", output=target)
    assert target.read_text(encoding="utf-8") == "original"
    with pytest.raises(OutputError, match="faltan"):
        export_rows([{"review_id": "x"}], REVIEW_FIELDS, output_format="json", output="-")


def test_plan_presentation_values_are_not_cleaned_by_mapping_or_export(tmp_path):
    plan = replace(
        _plan(),
        original_name="  Plan  Pró\nEspecial  ",
        currency="usd ",
        product=" Accounting-Suscripción ",
        promotion_text="  10%\npor lanzamiento  ",
    )
    row, _ = map_plan(plan, provider_code="comp", provider_name="Comp", ingested_at=NOW)
    target = tmp_path / "plans.json"
    export_rows([row], PLAN_FIELDS, output_format="json", output=target)
    exported = json.loads(target.read_text(encoding="utf-8"))[0]

    assert exported["plan_nombre"] == plan.original_name
    assert exported["moneda"] == plan.currency
    assert exported["producto"] == plan.product
    assert exported["promocion_texto"] == plan.promotion_text
