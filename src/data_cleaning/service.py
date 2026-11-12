"""Conservative cleaning rules for scraper datasets."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

import pandas as pd

from data_pipeline.errors import PipelineIssue, PipelineValidationError
from data_pipeline.normalization import normalized_key
from data_pipeline.policies import (
    NumericPolicy,
    NumericStrategy,
    PolicyApplication,
    get_numeric_policies,
)
from data_pipeline.profiles import DatasetType, get_profile
from data_pipeline.reporting import QualityReport

LINE_CONTROLS = re.compile(r" *[\t\r\n]+ *")
ABSENCE_REASON_COLUMNS = frozenset(
    {"comentario_estado", "not_found", "rating_only", "not_processed", "extraction_error"}
)


@dataclass(frozen=True, slots=True)
class CleaningResult:
    data: pd.DataFrame
    dataset_type: DatasetType
    issues: tuple[PipelineIssue, ...]
    input_rows: int
    output_rows: int
    empty_rows_removed: int
    duplicates_removed: int
    cleaned_cells: int
    empty_columns_removed: tuple[str, ...]
    rejected_rows: int
    numeric_policies_applied: tuple[PolicyApplication, ...]
    report: QualityReport


def _is_null(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _blank_to_null(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return pd.NA
    return value


def _clean_text(value: Any) -> Any:
    if _is_null(value):
        return pd.NA
    if not isinstance(value, str):
        return value
    without_controls = "".join(
        character
        for character in LINE_CONTROLS.sub(" ", value)
        if unicodedata.category(character) not in {"Cc", "Cf"}
    )
    return without_controls.strip()


def _values_equal(left: Any, right: Any) -> bool:
    if _is_null(left) and _is_null(right):
        return True
    try:
        return bool(left == right)
    except (TypeError, ValueError):
        return False


def _count_changes(before: pd.Series, after: pd.Series) -> int:
    return sum(
        not _values_equal(left, right)
        for left, right in zip(before.tolist(), after.tolist(), strict=True)
    )


def _numeric(value: Any) -> Decimal | None:
    if _is_null(value):
        return None
    if isinstance(value, bool):
        raise ValueError
    text = str(value).strip()
    if "," in text and "." in text:
        decimal_separator = "," if text.rfind(",") > text.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        text = text.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError from exc
    if not result.is_finite():
        raise ValueError
    return result


def _resolve_policies(
    dataset_type: DatasetType,
    overrides: Mapping[str, NumericPolicy] | None,
) -> dict[str, NumericPolicy]:
    policies = get_numeric_policies(dataset_type)
    if overrides:
        policies.update(overrides)
    return policies


def _apply_numeric_policies(
    frame: pd.DataFrame,
    policies: Mapping[str, NumericPolicy],
    issues: list[PipelineIssue],
) -> tuple[pd.DataFrame, tuple[PolicyApplication, ...], int]:
    applications: list[PolicyApplication] = []
    rows_to_remove: set[Any] = set()
    rejected_rows: set[Any] = set()
    for column, policy in policies.items():
        if column not in frame:
            applications.append(
                PolicyApplication(column, policy.strategy, 0, policy.value, column_present=False)
            )
            continue
        missing = frame[column].isna()
        affected = int(missing.sum())
        applied_value: Any = policy.value
        if affected and policy.strategy in {NumericStrategy.ZERO, NumericStrategy.FIXED}:
            applied_value = 0 if policy.strategy == NumericStrategy.ZERO else policy.value
            frame.loc[missing, column] = applied_value
        elif affected and policy.strategy in {NumericStrategy.MEAN, NumericStrategy.MEDIAN}:
            valid: list[Decimal] = []
            for value in frame.loc[~missing, column]:
                try:
                    parsed = _numeric(value)
                except ValueError:
                    continue
                if parsed is not None:
                    valid.append(parsed)
            if valid:
                applied_value = (
                    sum(valid, Decimal(0)) / len(valid)
                    if policy.strategy == NumericStrategy.MEAN
                    else median(valid)
                )
                frame.loc[missing, column] = applied_value
            else:
                affected = 0
                issues.append(
                    PipelineIssue(
                        "numeric-policy-no-valid-values",
                        f"no hay valores válidos para aplicar {policy.strategy.value}",
                        column=column,
                    )
                )
        elif affected and policy.strategy in {NumericStrategy.REJECT, NumericStrategy.DROP_ROW}:
            indexes = set(frame.index[missing])
            rows_to_remove.update(indexes)
            if policy.strategy == NumericStrategy.REJECT:
                rejected_rows.update(indexes)
                issues.append(
                    PipelineIssue(
                        "rows-rejected-by-policy",
                        f"{affected} filas rechazadas por valor numérico ausente",
                        column=column,
                    )
                )
        applications.append(PolicyApplication(column, policy.strategy, affected, applied_value))
    if rows_to_remove:
        frame = frame.drop(index=sorted(rows_to_remove))
    return frame, tuple(applications), len(rejected_rows)


def _feature_collisions(frame: pd.DataFrame) -> int:
    required = {"competidor_id", "plan_id", "nombre_modulo"}
    if not required.issubset(frame.columns):
        return 0
    comparison = frame.loc[:, sorted(required)].copy()
    comparison["normalized"] = comparison["nombre_modulo"].map(normalized_key)
    complete = comparison.dropna()
    duplicated = complete.duplicated(subset=["competidor_id", "plan_id", "normalized"], keep=False)
    if not duplicated.any():
        return 0
    groups = complete.loc[duplicated].groupby(
        ["competidor_id", "plan_id", "normalized"], dropna=False
    )["nombre_modulo"]
    return sum(1 for _, values in groups if values.astype(str).nunique() > 1)


def clean_dataset(
    input_data: pd.DataFrame,
    dataset_type: DatasetType | str,
    *,
    strict: bool = False,
    numeric_policies: Mapping[str, NumericPolicy] | None = None,
) -> CleaningResult:
    """Clean a frame without inventing values or changing source identifiers."""

    profile = get_profile(dataset_type)
    frame = input_data.copy(deep=True)
    input_rows = len(frame)
    issues: list[PipelineIssue] = []
    cleaned_cells = 0

    for column in frame.columns:
        before = frame[column].copy()
        frame[column] = frame[column].map(_blank_to_null)
        cleaned_cells += _count_changes(before, frame[column])

    reason_columns = sorted(ABSENCE_REASON_COLUMNS.intersection(frame.columns))
    if reason_columns:
        frame = frame.drop(columns=reason_columns)
        issues.append(
            PipelineIssue(
                "absence-reason-columns-removed",
                f"se retiraron columnas de estado de ausencia: {', '.join(reason_columns)}",
            )
        )

    empty_columns_removed = tuple(
        str(column) for column in frame.columns if frame[column].isna().all()
    )
    if empty_columns_removed:
        frame = frame.drop(columns=list(empty_columns_removed))

    for column in profile.text_columns.intersection(frame.columns):
        before = frame[column].copy()
        frame[column] = frame[column].map(_clean_text)
        cleaned_cells += _count_changes(before, frame[column])

    empty_mask = frame.isna().all(axis=1)
    empty_rows_removed = int(empty_mask.sum())
    frame = frame.loc[~empty_mask].copy()

    policies = _resolve_policies(profile.dataset_type, numeric_policies)
    unknown_numeric = [
        column
        for column in frame.columns
        if pd.api.types.is_numeric_dtype(frame[column].dtype)
        and not pd.api.types.is_bool_dtype(frame[column].dtype)
        and column not in policies
    ]
    for column in unknown_numeric:
        issues.append(
            PipelineIssue(
                "numeric-policy-missing",
                "la columna numérica se conservó sin imputar porque no tiene política explícita",
                column=column,
            )
        )
    frame, policy_applications, rejected_rows = _apply_numeric_policies(frame, policies, issues)

    duplicate_mask = frame.duplicated(keep="first")
    duplicates_removed = int(duplicate_mask.sum())
    frame = frame.loc[~duplicate_mask].copy()

    missing_required = [column for column in profile.required_columns if column not in frame]
    if missing_required:
        issues.append(
            PipelineIssue(
                "missing-identification-columns",
                f"faltan columnas mínimas: {', '.join(missing_required)}",
            )
        )

    duplicate_key_rows = 0
    key = [column for column in profile.deduplication_key if column in frame]
    if len(key) == len(profile.deduplication_key) and not frame.empty:
        complete_key = frame[key].notna().all(axis=1)
        collisions = frame.loc[complete_key].duplicated(subset=key, keep=False)
        duplicate_key_rows = int(collisions.sum())
        if duplicate_key_rows:
            issues.append(
                PipelineIssue(
                    "duplicate-key-conflict",
                    f"{duplicate_key_rows} filas comparten la clave {', '.join(key)} "
                    "pero difieren en otros valores; se conservaron",
                )
            )

    truncated = 0
    if "respuesta_desarrollador" in frame:
        truncated = int(
            frame["respuesta_desarrollador"]
            .fillna("")
            .astype(str)
            .str.rstrip()
            .str.endswith("… Más")
            .sum()
        )
        if truncated:
            issues.append(
                PipelineIssue(
                    "possibly-truncated-response",
                    f"{truncated} respuestas terminan en '… Más'; se conservaron",
                    column="respuesta_desarrollador",
                )
            )

    normalization_collisions = (
        _feature_collisions(frame) if profile.dataset_type == DatasetType.FEATURE else 0
    )
    if normalization_collisions:
        issues.append(
            PipelineIssue(
                "normalization-collision",
                f"{normalization_collisions} claves de característica agrupan etiquetas distintas",
                column="nombre_modulo",
            )
        )

    frame = frame.reset_index(drop=True)
    report = QualityReport(
        dataset_type=profile.dataset_type,
        input_rows=input_rows,
        output_rows=len(frame),
        rejected_rows=rejected_rows,
        removed_rows=empty_rows_removed + duplicates_removed,
        empty_columns_removed=empty_columns_removed,
        nulls_by_column={column: int(frame[column].isna().sum()) for column in frame},
        numeric_policies=policy_applications,
        exact_duplicates_removed=duplicates_removed,
        duplicate_key_rows=duplicate_key_rows,
        normalization_collisions=normalization_collisions,
        possibly_truncated_responses=truncated,
        issues=tuple(issues),
    )
    if strict and issues:
        raise PipelineValidationError(issues[0].format())
    return CleaningResult(
        data=frame,
        dataset_type=profile.dataset_type,
        issues=tuple(issues),
        input_rows=input_rows,
        output_rows=len(frame),
        empty_rows_removed=empty_rows_removed,
        duplicates_removed=duplicates_removed,
        cleaned_cells=cleaned_cells,
        empty_columns_removed=empty_columns_removed,
        rejected_rows=rejected_rows,
        numeric_policies_applied=policy_applications,
        report=report,
    )
