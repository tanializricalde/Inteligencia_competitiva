import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data_cleaning import NumericPolicy, NumericStrategy, clean_dataset
from data_pipeline import DatasetType


def test_review_cleaning_normalizes_text_nulls_rows_and_exact_duplicates():
    frame = pd.DataFrame(
        [
            {
                "review_id": "0001",
                "competidor_id": "comp",
                "timestamp_ingesta": "2026-01-01T00:00:00Z",
                "usuario_nombre": "  Ａna  ",
                "comentario_cliente": " Línea 1\n  línea 2 ",
                "sentimiento": "   ",
            },
            {
                "review_id": "0001",
                "competidor_id": "comp",
                "timestamp_ingesta": "2026-01-01T00:00:00Z",
                "usuario_nombre": "  Ａna  ",
                "comentario_cliente": " Línea 1\n  línea 2 ",
                "sentimiento": "   ",
            },
            {"review_id": "", "competidor_id": "", "timestamp_ingesta": ""},
        ],
        dtype="string",
    )

    result = clean_dataset(frame, DatasetType.REVIEW)

    assert result.input_rows == 3
    assert result.output_rows == 1
    assert result.empty_rows_removed == 1
    assert result.duplicates_removed == 1
    assert result.data.loc[0, "review_id"] == "0001"
    assert result.data.loc[0, "usuario_nombre"] == "Ａna"
    assert result.data.loc[0, "comentario_cliente"] == "Línea 1 línea 2"
    assert "sentimiento" not in result.data
    assert result.empty_columns_removed == ("sentimiento",)
    assert not result.issues


def test_cleaning_is_idempotent_and_preserves_conflicting_key_rows():
    frame = pd.DataFrame(
        [
            {
                "plan_id": "01",
                "competidor_id": "c",
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "plan_nombre": " Plan  Uno ",
            },
            {
                "plan_id": "01",
                "competidor_id": "c",
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "plan_nombre": "Plan Dos",
            },
        ]
    )

    first = clean_dataset(frame, "plan")
    second = clean_dataset(first.data, "plan")

    assert first.output_rows == 2
    assert first.data.loc[0, "plan_id"] == "01"
    assert first.issues[0].code == "duplicate-key-conflict"
    assert_frame_equal(first.data, second.data)


def test_feature_cleaning_uses_its_own_text_columns():
    result = clean_dataset(
        pd.DataFrame(
            [
                {
                    "plan_id": "p",
                    "competidor_id": "c",
                    "categoria_modulo": "  Facturación\n electrónica ",
                    "nombre_modulo": "  Emisión  ",
                }
            ]
        ),
        "feature",
    )

    assert result.data.loc[0, "categoria_modulo"] == "Facturación electrónica"
    assert result.data.loc[0, "nombre_modulo"] == "Emisión"


def test_cleaning_drops_all_empty_and_absence_reason_columns_but_keeps_literal_text():
    result = clean_dataset(
        pd.DataFrame(
            [
                {
                    "review_id": "0001:A",
                    "competidor_id": "c",
                    "timestamp_ingesta": "2026-01-01T00:00:00Z",
                    "comentario_cliente": "no data",
                    "categoria_tema": " ",
                    "comentario_estado": "rating_only",
                }
            ]
        ),
        "review",
    )

    assert result.data.loc[0, "review_id"] == "0001:A"
    assert result.data.loc[0, "comentario_cliente"] == "no data"
    assert "categoria_tema" not in result.data
    assert "comentario_estado" not in result.data
    assert result.report.empty_columns_removed == ("categoria_tema",)


@pytest.mark.parametrize(
    ("strategy", "policy_value", "expected", "rows"),
    [
        (NumericStrategy.KEEP_NA, None, pd.NA, 2),
        (NumericStrategy.ZERO, None, 0, 2),
        (NumericStrategy.MEAN, None, 10, 2),
        (NumericStrategy.MEDIAN, None, 10, 2),
        (NumericStrategy.FIXED, 7, 7, 2),
        (NumericStrategy.REJECT, None, None, 1),
        (NumericStrategy.DROP_ROW, None, None, 1),
    ],
)
def test_each_numeric_missing_policy_is_explicit_and_reported(
    strategy, policy_value, expected, rows
):
    result = clean_dataset(
        pd.DataFrame(
            [
                {
                    "timestamp_utc": "2026-01-01T00:00:00Z",
                    "competidor_id": "c",
                    "plan_id": "p1",
                    "plan_nombre": "Uno",
                    "precio_mensual": "10",
                },
                {
                    "timestamp_utc": "2026-01-02T00:00:00Z",
                    "competidor_id": "c",
                    "plan_id": "p2",
                    "plan_nombre": "Dos",
                    "precio_mensual": pd.NA,
                },
            ]
        ),
        "plan",
        numeric_policies={"precio_mensual": NumericPolicy(strategy, "prueba", value=policy_value)},
    )

    assert result.output_rows == rows
    application = next(
        item for item in result.numeric_policies_applied if item.column == "precio_mensual"
    )
    assert application.strategy == strategy
    assert application.affected_rows == 1
    if rows == 2:
        actual = result.data.loc[1, "precio_mensual"]
        if expected is pd.NA:
            assert pd.isna(actual)
        else:
            assert actual == expected


def test_truncated_response_and_normalized_feature_collision_are_reported_not_removed():
    review = clean_dataset(
        pd.DataFrame(
            [
                {
                    "review_id": "r1",
                    "competidor_id": "c",
                    "timestamp_ingesta": "2026-01-01T00:00:00Z",
                    "respuesta_desarrollador": "Respuesta… Más",
                }
            ]
        ),
        "review",
    )
    feature = clean_dataset(
        pd.DataFrame(
            [
                {
                    "plan_id": "p",
                    "competidor_id": "c",
                    "nombre_modulo": "Consulta sobre módulos adicionales",
                },
                {
                    "plan_id": "p",
                    "competidor_id": "c",
                    "nombre_modulo": "Consulta sobre módulos adicionales!",
                },
            ]
        ),
        "feature",
    )

    assert review.report.possibly_truncated_responses == 1
    assert feature.report.normalization_collisions == 1
    assert feature.output_rows == 2


def test_unknown_numeric_column_is_not_imputed_and_strict_mode_fails():
    frame = pd.DataFrame(
        [
            {
                "plan_id": "p",
                "competidor_id": "c",
                "plan_nombre": "Plan",
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "metrica_desconocida": 0,
            }
        ]
    )

    result = clean_dataset(frame, "plan")

    assert result.data.loc[0, "metrica_desconocida"] == 0
    assert "numeric-policy-missing" in {issue.code for issue in result.issues}
    with pytest.raises(ValueError, match="numeric-policy-missing"):
        clean_dataset(frame, "plan", strict=True)
