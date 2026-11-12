"""Transform clean datasets into traceable analytical views."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

from data_pipeline.errors import PipelineIssue, PipelineValidationError
from data_pipeline.normalization import normalized_key
from data_pipeline.policies import PolicyApplication
from data_pipeline.profiles import DatasetType, get_profile
from data_pipeline.reporting import QualityReport
from data_transformation.feature_rules import (
    FeatureRulesConfig,
    FeatureRulesReport,
    flatten_features,
)

DECIMAL_PATTERN = re.compile(r"^[+-]?(?:\d+(?:[.,]\d+)?|\d{1,3}(?:[.,]\d{3})+[.,]\d+)$")
BOOL_VALUES = {
    "true": 1,
    "1": 1,
    "yes": 1,
    "si": 1,
    "sí": 1,
    "false": 0,
    "0": 0,
    "no": 0,
}
DERIVED_FIELDS = {
    DatasetType.REVIEW: frozenset(
        {"sentimiento_por_calificacion", "plataforma_codigo", "categoria_tema_codigo"}
    ),
    DatasetType.PLAN: frozenset(
        {
            "plan_nombre_normalizado",
            "moneda_codigo",
            "precio_mensual_calculado",
            "diferencia_mensual",
            "diferencia_mensual_porcentaje",
            "precio_inconsistente_bandera",
        }
    ),
    DatasetType.FEATURE: frozenset({"nombre_modulo_normalizado"}),
}


@dataclass(frozen=True, slots=True)
class TransformationResult:
    data: pd.DataFrame
    dataset_type: DatasetType
    issues: tuple[PipelineIssue, ...]
    input_rows: int
    output_rows: int
    invalid_values: int
    derived_values: int
    empty_columns_removed: tuple[str, ...]
    duplicates_removed: int
    rejected_rows: int
    numeric_policies_applied: tuple[PolicyApplication, ...]
    wide_data: pd.DataFrame | None
    feature_values: pd.DataFrame | None
    feature_rules_report: FeatureRulesReport | None
    report: QualityReport


def _is_null(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _decimal(value: Any, *, percentage: bool = False) -> Decimal | None:
    if _is_null(value) or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError("un booleano no es un decimal")
    if isinstance(value, (int, float, Decimal)):
        result = Decimal(str(value))
    else:
        text = str(value).strip()
        if percentage and text.endswith("%"):
            text = text[:-1].strip()
        if not DECIMAL_PATTERN.fullmatch(text):
            raise ValueError("formato decimal no reconocido")
        if "," in text and "." in text:
            decimal_separator = "," if text.rfind(",") > text.rfind(".") else "."
            thousands_separator = "." if decimal_separator == "," else ","
            text = text.replace(thousands_separator, "").replace(decimal_separator, ".")
        elif "," in text:
            tail = text.rsplit(",", 1)[-1]
            text = text.replace(",", "." if len(tail) <= 2 else "")
        result = Decimal(text)
    if not result.is_finite():
        raise ValueError("el decimal debe ser finito")
    return result


def _integer(value: Any) -> int | None:
    result = _decimal(value)
    if result is None:
        return None
    if result != result.to_integral_value():
        raise ValueError("se esperaba un entero")
    return int(result)


def _boolean(value: Any) -> int | None:
    if _is_null(value) or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        return int(value)
    normalized = str(value).strip().casefold()
    if normalized not in BOOL_VALUES:
        raise ValueError("booleano no reconocido")
    return BOOL_VALUES[normalized]


def _datetime(value: Any) -> str | None:
    if _is_null(value) or (isinstance(value, str) and not value.strip()):
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("fecha ISO-8601 inválida") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("la fecha debe incluir zona horaria")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _convert_series(
    frame: pd.DataFrame,
    column: str,
    converter: Callable[[Any], Any],
    issues: list[PipelineIssue],
) -> tuple[pd.Series, int]:
    converted: list[Any] = []
    invalid = 0
    for row, value in frame[column].items():
        try:
            converted.append(converter(value))
        except (InvalidOperation, ValueError) as exc:
            invalid += 1
            converted.append(None)
            issues.append(
                PipelineIssue(
                    "invalid-value",
                    str(exc),
                    column=column,
                    row=row,
                    value=value,
                )
            )
    return pd.Series(converted, index=frame.index), invalid


def _bounded_integer(value: Any, minimum: int, maximum: int | None = None) -> int | None:
    result = _integer(value)
    if result is None:
        return None
    if result < minimum or (maximum is not None and result > maximum):
        maximum_text = f" y {maximum}" if maximum is not None else ""
        raise ValueError(f"el entero debe estar entre {minimum}{maximum_text}")
    return result


def _bounded_decimal(
    value: Any,
    *,
    minimum: Decimal = Decimal("0"),
    maximum: Decimal | None = None,
    percentage: bool = False,
) -> Decimal | None:
    result = _decimal(value, percentage=percentage)
    if result is None:
        return None
    if result < minimum or (maximum is not None and result > maximum):
        maximum_text = f" y {maximum}" if maximum is not None else ""
        raise ValueError(f"el decimal debe estar entre {minimum}{maximum_text}")
    return result


def _code(value: Any, length: int, label: str) -> str | None:
    if _is_null(value) or (isinstance(value, str) and not value.strip()):
        return None
    result = str(value).strip().upper()
    if len(result) != length or not result.isascii() or not result.isalpha():
        raise ValueError(f"{label} debe contener {length} letras ASCII")
    return result


def _validate_provider_relation(frame: pd.DataFrame, issues: list[PipelineIssue]) -> None:
    if "provider_code" not in frame:
        return
    if "competidor_id" not in frame:
        frame["competidor_id"] = frame["provider_code"]
        issues.append(
            PipelineIssue(
                "provider-code-mapped",
                "competidor_id se obtuvo de provider_code; adapter_key nunca se usa como identidad",
            )
        )
        return
    comparable = frame[["competidor_id", "provider_code"]].dropna()
    conflicts = comparable["competidor_id"].astype(str) != comparable["provider_code"].astype(str)
    if conflicts.any():
        issues.append(
            PipelineIssue(
                "provider-code-conflict",
                f"{int(conflicts.sum())} filas difieren entre competidor_id y provider_code; "
                "se conservó competidor_id",
            )
        )


def _derive_review_values(frame: pd.DataFrame, issues: list[PipelineIssue]) -> int:
    derived = 0
    ratings = frame.get("calificacion_estrellas", pd.Series(pd.NA, index=frame.index))
    sentiment = []
    for value in ratings:
        if pd.isna(value):
            sentiment.append(pd.NA)
        elif value <= 2:
            sentiment.append("negative")
            derived += 1
        elif value == 3:
            sentiment.append("neutral")
            derived += 1
        else:
            sentiment.append("positive")
            derived += 1
    frame["sentimiento_por_calificacion"] = pd.array(sentiment, dtype="string")

    if "tiene_respuesta" not in frame:
        frame["tiene_respuesta"] = pd.array([pd.NA] * len(frame), dtype="Int8")
    for row in frame.index:
        response_text = (
            frame.at[row, "respuesta_desarrollador"]
            if "respuesta_desarrollador" in frame
            else pd.NA
        )
        response_date = frame.at[row, "fecha_respuesta"] if "fecha_respuesta" in frame else pd.NA
        has_evidence = not pd.isna(response_text) or not pd.isna(response_date)
        current = frame.at[row, "tiene_respuesta"]
        if has_evidence and (pd.isna(current) or current == 0):
            if not pd.isna(current) and current == 0:
                issues.append(
                    PipelineIssue(
                        "response-contradiction",
                        "hay respuesta pero tiene_respuesta indicaba 0; se derivó 1",
                        column="tiene_respuesta",
                        row=row,
                    )
                )
            frame.at[row, "tiene_respuesta"] = 1
            derived += 1
        elif not has_evidence and pd.isna(current):
            frame.at[row, "tiene_respuesta"] = 0
            derived += 1

    if "dias_para_responder" not in frame:
        frame["dias_para_responder"] = pd.array([pd.NA] * len(frame), dtype="Float64")
    if {"fecha_comentario", "fecha_respuesta"}.issubset(frame.columns):
        for row in frame.index:
            if not pd.isna(frame.at[row, "dias_para_responder"]):
                continue
            published = frame.at[row, "fecha_comentario"]
            response = frame.at[row, "fecha_respuesta"]
            if pd.isna(published) or pd.isna(response):
                continue
            start = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(response).replace("Z", "+00:00"))
            if end >= start:
                frame.at[row, "dias_para_responder"] = (end - start).total_seconds() / 86_400
                derived += 1
            else:
                issues.append(
                    PipelineIssue(
                        "invalid-date-order",
                        "fecha_respuesta es anterior a fecha_comentario; no se derivó el plazo",
                        column="dias_para_responder",
                        row=row,
                    )
                )
    for source, target in (
        ("plataforma", "plataforma_codigo"),
        ("categoria_tema", "categoria_tema_codigo"),
    ):
        if source in frame:
            frame[target] = pd.array(frame[source].map(normalized_key), dtype="string")
    return derived


def _derive_plan_values(frame: pd.DataFrame) -> tuple[int, int]:
    derived = 0
    discrepancies = 0
    if "plan_nombre" in frame:
        frame["plan_nombre_normalizado"] = pd.array(
            frame["plan_nombre"].map(normalized_key), dtype="string"
        )
    if "moneda" in frame:
        frame["moneda_codigo"] = frame["moneda"].astype("string").str.strip().str.upper()
    calculated: list[Any] = []
    difference: list[Any] = []
    percentage: list[Any] = []
    inconsistent: list[Any] = []
    for row in frame.index:
        annual = frame.at[row, "precio_anual_total"] if "precio_anual_total" in frame else pd.NA
        informed = (
            frame.at[row, "precio_mensual_efectivo"]
            if "precio_mensual_efectivo" in frame
            and not pd.isna(frame.at[row, "precio_mensual_efectivo"])
            else frame.at[row, "precio_mensual"]
            if "precio_mensual" in frame
            else pd.NA
        )
        if pd.isna(annual):
            calculated.append(pd.NA)
            difference.append(pd.NA)
            percentage.append(pd.NA)
            inconsistent.append(pd.NA)
            continue
        monthly = annual / 12
        calculated.append(monthly)
        derived += 1
        if pd.isna(informed):
            difference.append(pd.NA)
            percentage.append(pd.NA)
            inconsistent.append(pd.NA)
            continue
        delta = informed - monthly
        difference.append(delta)
        percentage.append((delta / informed * 100) if informed != 0 else pd.NA)
        flag = int(abs(delta) > 0.01)
        inconsistent.append(flag)
        discrepancies += flag
        derived += 3
    frame["precio_mensual_calculado"] = pd.array(calculated, dtype="Float64")
    frame["diferencia_mensual"] = pd.array(difference, dtype="Float64")
    frame["diferencia_mensual_porcentaje"] = pd.array(percentage, dtype="Float64")
    frame["precio_inconsistente_bandera"] = pd.array(inconsistent, dtype="Int8")
    return derived, discrepancies


def _normalize_feature_values(
    frame: pd.DataFrame,
    issues: list[PipelineIssue],
    *,
    configured_wide: bool,
) -> tuple[int, int, set[tuple[Any, Any, Any]]]:
    frame["nombre_modulo_normalizado"] = pd.array(
        frame.get("nombre_modulo", pd.Series(pd.NA, index=frame.index)).map(normalized_key),
        dtype="string",
    )
    keys = ["competidor_id", "plan_id"]
    columns = [*keys, "nombre_modulo_normalizado", "nombre_modulo", "incluido"]
    available = frame.loc[:, [column for column in columns if column in frame]].dropna(
        subset=[column for column in [*keys, "nombre_modulo_normalizado"] if column in frame]
    )
    collision_count = 0
    collided: set[tuple[Any, Any, Any]] = set()
    if all(column in available for column in columns):
        for group_key, group in available.groupby(
            [*keys, "nombre_modulo_normalizado"], sort=False, dropna=False
        ):
            originals = group["nombre_modulo"].astype(str).nunique()
            values = group["incluido"].dropna().nunique()
            if len(group) > 1 and (originals > 1 or values > 1):
                collision_count += 1
                collided.add(group_key)
        if collision_count:
            consequence = (
                "las reglas o el fallback resolverán según sus reductores"
                if configured_wide
                else "la vista ancha usa nulo en conflictos"
            )
            issues.append(
                PipelineIssue(
                    "normalization-collision",
                    f"{collision_count} claves colisionan; {consequence}",
                    column="nombre_modulo_normalizado",
                )
            )
    return int(frame["nombre_modulo_normalizado"].notna().sum()), collision_count, collided


def _flatten_features_legacy(
    frame: pd.DataFrame, collided: set[tuple[Any, Any, Any]]
) -> pd.DataFrame:
    keys = ["competidor_id", "plan_id"]
    records: list[dict[str, Any]] = []
    feature_names: list[str] = []
    if set(keys).issubset(frame.columns):
        feature_names = sorted(
            str(value) for value in frame["nombre_modulo_normalizado"].dropna().unique()
        )
        for group_key, group in frame.groupby(keys, sort=False, dropna=False):
            record = dict(zip(keys, group_key, strict=True))
            record.update({name: pd.NA for name in feature_names})
            for _, row in group.iterrows():
                name = row["nombre_modulo_normalizado"]
                if pd.isna(name):
                    continue
                collision_key = (*group_key, name)
                if collision_key not in collided:
                    record[str(name)] = row.get("incluido", pd.NA)
            records.append(record)
    return pd.DataFrame(records, columns=[*keys, *feature_names] if records else keys)


def transform_dataset(
    input_data: pd.DataFrame,
    dataset_type: DatasetType | str,
    *,
    strict: bool = False,
    feature_rules: FeatureRulesConfig | None = None,
    strict_feature_rules: bool = False,
    run_id: str | None = None,
) -> TransformationResult:
    """Convert safe values and add derived columns without overwriting observed facts."""

    profile = get_profile(dataset_type)
    if feature_rules is not None and profile.dataset_type != DatasetType.FEATURE:
        raise ValueError("feature_rules sólo se puede aplicar al tipo feature")
    if strict_feature_rules and feature_rules is None:
        raise ValueError("strict_feature_rules requiere feature_rules")
    frame = input_data.copy(deep=True)
    input_rows = len(frame)
    issues: list[PipelineIssue] = []
    _validate_provider_relation(frame, issues)

    missing_required = [column for column in profile.required_columns if column not in frame]
    for column in missing_required:
        frame[column] = pd.NA
    if missing_required:
        issues.append(
            PipelineIssue(
                "missing-required-columns",
                f"se añadieron como nulas: {', '.join(missing_required)}",
            )
        )
    extra = [
        column
        for column in frame
        if column not in profile.fields
        and column not in DERIVED_FIELDS[profile.dataset_type]
        and column != "provider_code"
    ]
    if extra:
        issues.append(
            PipelineIssue("extra-columns", f"se omitieron del esquema final: {', '.join(extra)}")
        )
    ordered = [column for column in profile.fields if column in frame]
    frame = frame.loc[:, ordered].copy()

    invalid_values = 0
    for column in profile.decimal_columns.intersection(frame.columns):
        percentage = column == "descuento_anual_pct"
        maximum = Decimal("100") if percentage else None
        series, invalid = _convert_series(
            frame,
            column,
            lambda value, percentage=percentage, maximum=maximum: _bounded_decimal(
                value, percentage=percentage, maximum=maximum
            ),
            issues,
        )
        frame[column] = pd.array(series, dtype="Float64")
        invalid_values += invalid
    for column in profile.integer_columns.intersection(frame.columns):
        maximum = 5 if column == "calificacion_estrellas" else None
        minimum = 1 if column == "calificacion_estrellas" else 0
        series, invalid = _convert_series(
            frame,
            column,
            lambda value, minimum=minimum, maximum=maximum: _bounded_integer(
                value, minimum, maximum
            ),
            issues,
        )
        frame[column] = pd.array(series, dtype="Int64")
        invalid_values += invalid
    for column in profile.boolean_columns.intersection(frame.columns):
        series, invalid = _convert_series(frame, column, _boolean, issues)
        frame[column] = pd.array(series, dtype="Int8")
        invalid_values += invalid
    for column in profile.datetime_columns.intersection(frame.columns):
        series, invalid = _convert_series(frame, column, _datetime, issues)
        frame[column] = pd.array(series, dtype="string")
        invalid_values += invalid

    typed = (
        profile.decimal_columns
        | profile.integer_columns
        | profile.boolean_columns
        | profile.datetime_columns
    )
    for column in set(frame.columns) - typed:
        frame[column] = (
            frame[column]
            .map(
                lambda value: (
                    pd.NA
                    if _is_null(value) or (isinstance(value, str) and not value.strip())
                    else str(value)
                )
            )
            .astype("string")
        )

    for column, length in (("moneda", 3), ("pais_codigo", 2)):
        if column not in frame:
            continue
        series, invalid = _convert_series(
            frame,
            column,
            lambda value, length=length, column=column: _code(value, length, column),
            issues,
        )
        frame[column] = pd.array(series, dtype="string")
        invalid_values += invalid

    derived_values = 0
    price_discrepancies = 0
    normalization_collisions = 0
    wide_data: pd.DataFrame | None = None
    feature_values: pd.DataFrame | None = None
    feature_rules_report: FeatureRulesReport | None = None
    if profile.dataset_type == DatasetType.REVIEW:
        derived_values = _derive_review_values(frame, issues)
    elif profile.dataset_type == DatasetType.PLAN:
        derived_values, price_discrepancies = _derive_plan_values(frame)
        if price_discrepancies:
            issues.append(
                PipelineIssue(
                    "price-discrepancy",
                    f"{price_discrepancies} precios mensuales difieren del anual dividido por 12",
                )
            )
    else:
        derived_values, normalization_collisions, collided = _normalize_feature_values(
            frame,
            issues,
            configured_wide=feature_rules is not None,
        )
        if feature_rules is None:
            wide_data = _flatten_features_legacy(frame, collided)
        else:
            flattened = flatten_features(
                frame,
                config=feature_rules,
                strict=strict_feature_rules,
                run_id=run_id,
            )
            wide_data = flattened.dataframe
            feature_values = flattened.values_dataframe
            feature_rules_report = flattened.report

    for column in profile.required_columns:
        missing_count = int(frame[column].isna().sum())
        if missing_count:
            issues.append(
                PipelineIssue(
                    "missing-required-values",
                    f"{missing_count} filas carecen de un valor requerido",
                    column=column,
                )
            )

    report = QualityReport(
        dataset_type=profile.dataset_type,
        input_rows=input_rows,
        output_rows=len(frame),
        nulls_by_column={column: int(frame[column].isna().sum()) for column in frame},
        normalization_collisions=normalization_collisions,
        out_of_range_values=sum(issue.code == "invalid-value" for issue in issues),
        price_discrepancies=price_discrepancies,
        conversion_failures=invalid_values,
        issues=tuple(issues),
    )
    if strict and issues:
        raise PipelineValidationError(issues[0].format())
    return TransformationResult(
        data=frame,
        dataset_type=profile.dataset_type,
        issues=tuple(issues),
        input_rows=input_rows,
        output_rows=len(frame),
        invalid_values=invalid_values,
        derived_values=derived_values,
        empty_columns_removed=(),
        duplicates_removed=0,
        rejected_rows=0,
        numeric_policies_applied=(),
        wide_data=wide_data,
        feature_values=feature_values,
        feature_rules_report=feature_rules_report,
        report=report,
    )
