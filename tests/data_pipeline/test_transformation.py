import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data_pipeline import PipelineValidationError
from data_pipeline.profiles import FEATURE_FIELDS, PLAN_FIELDS, REVIEW_FIELDS
from data_transformation import transform_dataset


def _complete_review(**overrides):
    row = {field: None for field in REVIEW_FIELDS}
    row.update(
        {
            "review_id": "0001",
            "competidor_id": "comp",
            "plataforma": "google_maps",
            "pais_codigo": "ec",
            "fecha_comentario": "2026-01-01T00:00:00-05:00",
            "calificacion_estrellas": "5",
            "likes_comentario": "0",
            "tiene_respuesta": "",
            "fecha_respuesta": "2026-01-02T05:00:00Z",
            "respuesta_desarrollador": "Gracias",
            "timestamp_ingesta": "2026-01-03T00:00:00Z",
        }
    )
    row.update(overrides)
    return row


def test_review_transformation_converts_types_and_derives_response_fields():
    result = transform_dataset(pd.DataFrame([_complete_review()]), "review")

    assert tuple(result.data.columns[: len(REVIEW_FIELDS)]) == REVIEW_FIELDS
    assert result.data.loc[0, "review_id"] == "0001"
    assert result.data.loc[0, "pais_codigo"] == "EC"
    assert result.data.loc[0, "fecha_comentario"] == "2026-01-01T05:00:00Z"
    assert result.data.loc[0, "calificacion_estrellas"] == 5
    assert result.data.loc[0, "likes_comentario"] == 0
    assert result.data.loc[0, "tiene_respuesta"] == 1
    assert result.data.loc[0, "dias_para_responder"] == 1
    assert result.data.loc[0, "sentimiento_por_calificacion"] == "positive"
    assert result.derived_values == 3
    assert not result.issues


def test_invalid_values_become_null_with_structured_issues_or_fail_in_strict_mode():
    frame = pd.DataFrame(
        [
            _complete_review(
                calificacion_estrellas="6",
                likes_comentario="muchos",
                pais_codigo="ecu",
            )
        ]
    )

    result = transform_dataset(frame, "review")

    assert result.invalid_values == 3
    assert pd.isna(result.data.loc[0, "calificacion_estrellas"])
    assert pd.isna(result.data.loc[0, "likes_comentario"])
    assert pd.isna(result.data.loc[0, "pais_codigo"])
    assert {issue.column for issue in result.issues} >= {
        "calificacion_estrellas",
        "likes_comentario",
        "pais_codigo",
    }
    with pytest.raises(PipelineValidationError, match="invalid-value"):
        transform_dataset(frame, "review", strict=True)


def test_plan_transformation_orders_columns_normalizes_values_and_is_idempotent():
    row = {field: None for field in PLAN_FIELDS}
    row.update(
        {
            "timestamp_utc": "2026-01-01T00:00:00-05:00",
            "competidor_id": "comp",
            "competidor_nombre": "Competidor",
            "plan_id": "0007",
            "plan_nombre": "Plan",
            "moneda": " usd ",
            "precio_anual_total": "1.200,00",
            "descuento_anual_pct": "20%",
            "es_oferta_activa": "sí",
        }
    )

    first = transform_dataset(pd.DataFrame([row]), "plan")
    second = transform_dataset(first.data, "plan")

    assert tuple(first.data[:0].columns[: len(PLAN_FIELDS)]) == PLAN_FIELDS
    assert first.data.loc[0, "plan_id"] == "0007"
    assert first.data.loc[0, "moneda"] == "USD"
    assert first.data.loc[0, "precio_anual_total"] == 1200
    assert pd.isna(first.data.loc[0, "precio_mensual_efectivo"])
    assert first.data.loc[0, "precio_mensual_calculado"] == 100
    assert first.data.loc[0, "descuento_anual_pct"] == 20
    assert bool(first.data.loc[0, "es_oferta_activa"]) is True
    assert_frame_equal(first.data, second.data)


def test_feature_transformation_and_provider_code_mapping_do_not_use_adapter_key():
    result = transform_dataset(
        pd.DataFrame(
            [
                {
                    "plan_id": "p1",
                    "provider_code": "provider",
                    "adapter_key": "shared_adapter",
                    "categoria_modulo": "Ventas",
                    "nombre_modulo": "Facturación",
                    "incluido": "FALSE",
                    "costo_adicional": "2,50",
                }
            ]
        ),
        "feature",
    )

    assert tuple(result.data.columns[: len(FEATURE_FIELDS)]) == FEATURE_FIELDS
    assert result.data.loc[0, "competidor_id"] == "provider"
    assert result.data.loc[0, "incluido"] == 0
    assert result.data.loc[0, "costo_adicional"] == 2.5
    assert "adapter_key" not in result.data
    assert {issue.code for issue in result.issues} == {
        "provider-code-mapped",
        "extra-columns",
    }
    assert result.data.loc[0, "nombre_modulo_normalizado"] == "facturacion"
    assert result.wide_data.loc[0, "facturacion"] == 0


def test_plan_prices_are_compared_without_replacing_informed_values():
    result = transform_dataset(
        pd.DataFrame(
            [
                {
                    "timestamp_utc": "2026-01-01T00:00:00Z",
                    "competidor_id": "c",
                    "plan_id": "p",
                    "plan_nombre": "Peña Pro",
                    "precio_mensual": "90",
                    "precio_anual_total": "1200",
                }
            ]
        ),
        "plan",
    )

    assert result.data.loc[0, "precio_mensual"] == 90
    assert result.data.loc[0, "precio_mensual_calculado"] == 100
    assert result.data.loc[0, "diferencia_mensual"] == -10
    assert result.data.loc[0, "precio_inconsistente_bandera"] == 1
    assert result.data.loc[0, "plan_nombre"] == "Peña Pro"
    assert result.data.loc[0, "plan_nombre_normalizado"] == "pena_pro"
    assert result.report.price_discrepancies == 1


def test_feature_wide_view_uses_null_for_normalized_collisions():
    result = transform_dataset(
        pd.DataFrame(
            [
                {
                    "plan_id": "p",
                    "competidor_id": "c",
                    "nombre_modulo": "Módulo Ñ",
                    "incluido": "sí",
                },
                {
                    "plan_id": "p",
                    "competidor_id": "c",
                    "nombre_modulo": "Modulo N!",
                    "incluido": "no",
                },
            ]
        ),
        "feature",
    )

    assert result.output_rows == 2
    assert result.report.normalization_collisions == 1
    assert pd.isna(result.wide_data.loc[0, "modulo_n"])
