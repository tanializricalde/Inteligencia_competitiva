from pathlib import Path

import pytest

from data_pipeline import DatasetDetectionError, DatasetType, detect_dataset_type


def test_detects_reviews_from_path_and_from_columns():
    assert (
        detect_dataset_type(Path("data/raw/reviews/input.csv"), ["unknown"]) == DatasetType.REVIEW
    )
    assert (
        detect_dataset_type(Path("data/input.csv"), ["review_id", "comentario_cliente"])
        == DatasetType.REVIEW
    )


def test_detects_plans_and_features_from_canonical_signatures():
    assert detect_dataset_type("input.csv", ["plan_id", "plan_nombre"]) == DatasetType.PLAN
    assert (
        detect_dataset_type("plan_features.csv", ["plan_id", "nombre_modulo"])
        == DatasetType.FEATURE
    )


def test_unknown_input_explains_columns_and_explicit_type():
    with pytest.raises(DatasetDetectionError, match=r"Columnas encontradas: foo.*--type"):
        detect_dataset_type("input.csv", ["foo"])


def test_ambiguous_signatures_are_not_chosen_arbitrarily():
    with pytest.raises(DatasetDetectionError, match=r"Tipo ambiguo.*feature.*plan"):
        detect_dataset_type("input.csv", ["plan_id", "plan_nombre", "nombre_modulo"])


def test_contradictory_path_and_columns_are_rejected():
    with pytest.raises(DatasetDetectionError, match="Señales contradictorias"):
        detect_dataset_type("reviews.csv", ["plan_id", "plan_nombre"])
