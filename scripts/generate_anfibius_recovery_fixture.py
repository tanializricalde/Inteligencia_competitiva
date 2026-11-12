#!/usr/bin/env python3
"""Build the immutable, privacy-safe Anfibius recovery migration fixture."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NORMALIZED = ROOT / "data" / "normalized"
DEFAULT_OUTPUT = (
    ROOT / "src" / "apps" / "pipeline" / "migrations" / "fixtures" / "anfibius_recovery_v1.json"
)
EXPECTED_COUNTS = {"plans": 3, "feature_sources": 15, "feature_values": 186, "reviews": 50}


def _rows(filename: str) -> list[dict[str, str]]:
    with (NORMALIZED / filename).open(encoding="utf-8", newline="") as stream:
        return [row for row in csv.DictReader(stream) if row.get("competidor_id") == "anfibius"]


def _optional(value: str | None):
    return value if value not in (None, "") else None


def _boolean(value: str | None) -> bool | None:
    value = _optional(value)
    if value is None:
        return None
    normalized = value.casefold()
    if normalized in {"1", "true"}:
        return True
    if normalized in {"0", "false"}:
        return False
    raise ValueError(f"Booleano inesperado en dataset normalizado: {value!r}")


def _integer(value: str | None) -> int | None:
    value = _optional(value)
    return None if value is None else int(value)


def _source_hash(filename: str) -> str:
    return hashlib.sha256((NORMALIZED / filename).read_bytes()).hexdigest()


def build_fixture() -> dict:
    plan_rows = _rows("plans.csv")
    feature_rows = _rows("features.csv")
    value_rows = _rows("feature-values.csv")
    review_rows = _rows("reviews.csv")

    plans = [
        {
            "external_key": row["plan_id"],
            "name": row["plan_nombre"],
            "normalized_name": row["plan_nombre_normalizado"],
            "product_code": row["producto"],
            "source_url": row["url_fuente"],
            "observed_at": row["timestamp_utc"],
            "currency_code": row["moneda_codigo"],
            "monthly_price": _optional(row["precio_mensual"]),
            "annual_price": _optional(row["precio_anual_total"]),
            "is_offer_active": _boolean(row["es_oferta_activa"]),
        }
        for row in plan_rows
    ]
    feature_sources = [
        {
            "plan_id": row["plan_id"],
            "category": _optional(row["categoria_modulo"]),
            "raw_name": row["nombre_modulo"],
            "normalized_name": row["nombre_modulo_normalizado"],
            "included": _boolean(row["incluido"]),
            "position": index,
        }
        for index, row in enumerate(feature_rows)
    ]
    feature_values = []
    for row in value_rows:
        raw_json = _optional(row["value_json"])
        feature_values.append(
            {
                "plan_id": row["plan_id"],
                "code": row["feature_code"],
                "data_type": row["value_type"],
                "value_boolean": _boolean(row["value_boolean"]),
                "value_integer": _integer(row["value_integer"]),
                "value_decimal": _optional(row["value_decimal"]),
                "value_text": _optional(row["value_text"]),
                "value_json": json.loads(raw_json) if raw_json is not None else None,
                "availability": row["availability"],
                "origin": row["origin"],
                "rule_id": _optional(row["rule_id"]),
                "is_derived": _boolean(row["is_derived"]) or False,
            }
        )

    # Review authors, text, replies and upstream IDs are intentionally excluded.
    reviews = [
        {
            "external_id": f"anfibius-recovery-review-{index:03d}",
            "platform_code": row["plataforma_codigo"],
            "country_code": _optional(row["pais_codigo"]),
            "rating_stars": _integer(row["calificacion_estrellas"]),
            "has_developer_response": _boolean(row["tiene_respuesta"]),
            "ingested_at": row["timestamp_ingesta"],
            "sentiment_from_rating": _optional(row["sentimiento_por_calificacion"]),
        }
        for index, row in enumerate(review_rows, start=1)
    ]
    payload = {
        "_meta": {
            "dataset_code": "anfibius_recovery_v1",
            "provider_code": "anfibius",
            "privacy": "review identity and free text removed",
            "source_files": {
                filename: _source_hash(filename)
                for filename in ("plans.csv", "features.csv", "feature-values.csv", "reviews.csv")
            },
            "counts": EXPECTED_COUNTS,
        },
        "plans": plans,
        "feature_sources": feature_sources,
        "feature_values": feature_values,
        "reviews": reviews,
    }
    actual = {key: len(payload[key]) for key in EXPECTED_COUNTS}
    if actual != EXPECTED_COUNTS:
        raise ValueError(f"Conteos inesperados para Anfibius: {actual!r}")
    if any(plan["monthly_price"] or plan["annual_price"] for plan in plans):
        raise ValueError("El snapshot de origen no debe adquirir precios implícitos")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_fixture()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Fixture Anfibius generado: {args.output}")


if __name__ == "__main__":
    main()
