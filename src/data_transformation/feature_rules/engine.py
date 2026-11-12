"""Pure feature-equivalence evaluation, reduction, fallback and derivation."""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

from data_pipeline.normalization import normalized_key
from data_transformation.feature_rules.contracts import (
    ColumnSpec,
    DerivedColumnSpec,
    FeatureFlattenResult,
    FeatureRulesConfig,
    FeatureRulesExecutionError,
    FeatureRulesReport,
    Reducer,
    RuleSpec,
    ValueType,
)


def _is_null(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _input_boolean(value: Any) -> bool | None:
    if _is_null(value) or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    values = {
        "true": True,
        "1": True,
        "yes": True,
        "si": True,
        "sí": True,
        "false": False,
        "0": False,
        "no": False,
    }
    if normalized not in values:
        raise FeatureRulesExecutionError(f"incluido contiene un booleano inválido: {value!r}")
    return values[normalized]


def _coerce(value: Any, value_type: ValueType) -> Any:
    if _is_null(value) or (isinstance(value, str) and not value.strip()):
        return None
    if value_type == ValueType.BOOLEAN:
        return _input_boolean(value)
    if value_type in {ValueType.INTEGER, ValueType.DECIMAL}:
        if isinstance(value, bool):
            raise ValueError("un booleano no es numérico")
        try:
            number = Decimal(str(value).strip().replace(",", "."))
        except InvalidOperation as exc:
            raise ValueError("valor numérico inválido") from exc
        if not number.is_finite():
            raise ValueError("el número debe ser finito")
        if value_type == ValueType.INTEGER:
            if number != number.to_integral_value():
                raise ValueError("se esperaba un entero")
            return int(number)
        return number
    if value_type == ValueType.STRING:
        return str(value)
    if value_type == ValueType.STRING_LIST:
        if isinstance(value, (list, tuple)):
            if not all(isinstance(item, str) for item in value):
                raise ValueError("string_list sólo admite strings")
            return list(value)
        return [str(value)]
    raise ValueError(f"tipo no soportado: {value_type}")


def _matches(rule: RuleSpec, row: pd.Series):
    value = row.get(rule.when.field, pd.NA)
    if _is_null(value):
        return None
    if rule.when.operator == "equals":
        return True if value == rule.when.value else None
    return rule.when.compiled.search(str(value))


def _source_value(rule: RuleSpec, output, row: pd.Series, match) -> Any:
    source = output.source
    if source.kind == "literal":
        return source.value
    if source.kind == "field":
        return row.get(source.value, pd.NA)
    if match is None or match is True:
        raise ValueError(f"la regla {rule.rule_id} no produjo capturas")
    return match.group(source.value)


def _unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if candidate not in result:
                result.append(candidate)
    return result


def _reduce(
    values: list[Any],
    *,
    reducer: Reducer,
    default: Any,
    column: str,
    report: FeatureRulesReport,
) -> Any:
    present = [value for value in values if not _is_null(value)]
    if not present:
        return pd.NA if default is None else default
    if reducer == Reducer.SUM:
        return sum(present)
    if reducer == Reducer.MAX:
        return max(present)
    if reducer == Reducer.MIN:
        return min(present)
    if reducer == Reducer.FIRST:
        return present[0]
    if reducer == Reducer.LAST:
        return present[-1]
    if reducer == Reducer.ANY:
        return any(present)
    if reducer == Reducer.ALL:
        return all(present)
    unique = _unique(present)
    if reducer == Reducer.JOIN_UNIQUE:
        return unique
    if reducer == Reducer.ERROR:
        if len(unique) > 1:
            report.column_collisions.append(column)
            raise FeatureRulesExecutionError(
                f"La columna {column} recibió más de un valor diferente: {unique!r}",
                report=report,
            )
        return unique[0]
    raise FeatureRulesExecutionError(f"Reductor no soportado: {reducer}")


def _render_reduced(value: Any, column: ColumnSpec) -> Any:
    if _is_null(value):
        return pd.NA
    if column.reducer == Reducer.JOIN_UNIQUE and column.value_type == ValueType.STRING:
        return "|".join(str(item) for item in value)
    if column.value_type == ValueType.STRING_LIST and not isinstance(value, list):
        return [str(value)]
    return value


def _rules_for(config: FeatureRulesConfig, competitor: str) -> tuple[RuleSpec, ...]:
    selected = config.competitors.get(competitor)
    if selected is None:
        return ()
    rules = [rule for rule_set in selected.rule_sets for rule in config.rule_sets[rule_set]]
    return tuple(sorted(rules, key=lambda rule: (-rule.priority, rule.declaration_order)))


def _derive_value(
    spec: DerivedColumnSpec,
    record: dict[str, Any],
    config: FeatureRulesConfig,
    resolving: set[str],
) -> Any:
    if spec.name in record:
        return record[spec.name]
    if spec.name in resolving:
        raise FeatureRulesExecutionError(f"Ciclo derivado inesperado en {spec.name}")
    resolving.add(spec.name)
    if spec.operation == "sum_columns":
        values: list[Any] = []
        for name in spec.inputs:
            if name in config.derived_by_name:
                value = _derive_value(config.derived_by_name[name], record, config, resolving)
            else:
                value = record.get(name, pd.NA)
            if not _is_null(value):
                values.append(value)
        if values:
            result = sum(values)
        elif spec.null_policy == "null_if_all_null":
            result = pd.NA
        else:
            result = pd.NA if spec.default is None else spec.default
    else:
        selected = [column for column in config.columns if spec.select_tag in column.tags]
        truthy = [column for column in selected if record.get(column.name) is True]
        if spec.operation == "count_true":
            result = len(truthy)
        elif spec.operation == "join_labels":
            labels = [column.label for column in truthy]
            if spec.distinct:
                labels = _unique(labels)
            if not labels:
                result = pd.NA if spec.default is None else spec.default
            elif spec.value_type == ValueType.STRING_LIST:
                result = labels
            else:
                result = spec.separator.join(labels)
        else:
            raise FeatureRulesExecutionError(f"Operación derivada no soportada: {spec.operation}")
    resolving.remove(spec.name)
    record[spec.name] = result
    return result


def _cast_column(series: pd.Series, value_type: ValueType) -> pd.Series:
    if value_type == ValueType.BOOLEAN:
        values = series.map(lambda value: pd.NA if _is_null(value) else int(bool(value)))
        return pd.array(values, dtype="Int8")
    if value_type == ValueType.INTEGER:
        return pd.array(series, dtype="Int64")
    if value_type == ValueType.DECIMAL:
        return pd.array(series, dtype="Float64")
    if value_type == ValueType.STRING:
        return pd.array(series, dtype="string")
    return series.astype(object)


FEATURE_VALUE_COLUMNS = (
    "run_id",
    "plan_id",
    "competidor_id",
    "feature_code",
    "value_type",
    "value_boolean",
    "value_integer",
    "value_decimal",
    "value_text",
    "value_json",
    "availability",
    "origin",
    "rule_id",
    "is_derived",
)


def _availability(value: Any, *, origin: str, value_type: ValueType) -> str:
    if origin == "default" or _is_null(value):
        return "unknown"
    if value_type == ValueType.BOOLEAN and value is False:
        return "excluded"
    return "present"


def _feature_value_record(
    *,
    run_id: str | None,
    group: dict[str, Any],
    feature_code: str,
    value_type: ValueType,
    value: Any,
    origin: str,
    rule_id: str | None,
    is_derived: bool,
) -> dict[str, Any]:
    record = {column: pd.NA for column in FEATURE_VALUE_COLUMNS}
    record.update(
        {
            "run_id": pd.NA if run_id is None else run_id,
            "plan_id": group["plan_id"],
            "competidor_id": group["competidor_id"],
            "feature_code": feature_code,
            "value_type": value_type.value,
            "availability": _availability(value, origin=origin, value_type=value_type),
            "origin": origin,
            "rule_id": pd.NA if rule_id is None else rule_id,
            "is_derived": is_derived,
        }
    )
    if _is_null(value):
        return record
    if value_type == ValueType.BOOLEAN:
        record["value_boolean"] = bool(value)
    elif value_type == ValueType.INTEGER:
        record["value_integer"] = int(value)
    elif value_type == ValueType.DECIMAL:
        record["value_decimal"] = value
    elif value_type == ValueType.STRING:
        record["value_text"] = str(value)
    else:
        record["value_json"] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return record


def wide_from_feature_values(
    values: pd.DataFrame,
    *,
    group_by: tuple[str, ...],
    feature_order: tuple[str, ...],
) -> pd.DataFrame:
    """Build the compatibility matrix exclusively from typed long feature values."""

    if values.empty:
        return pd.DataFrame(columns=[*group_by, *feature_order])
    typed_columns = {
        ValueType.BOOLEAN.value: "value_boolean",
        ValueType.INTEGER.value: "value_integer",
        ValueType.DECIMAL.value: "value_decimal",
        ValueType.STRING.value: "value_text",
        ValueType.STRING_LIST.value: "value_json",
    }
    rows: list[dict[str, Any]] = []
    for group_key, group in values.groupby(list(group_by), sort=False, dropna=False):
        keys = group_key if isinstance(group_key, tuple) else (group_key,)
        record = dict(zip(group_by, keys, strict=True))
        for item in group.to_dict(orient="records"):
            value_type = item["value_type"]
            value = item[typed_columns[value_type]]
            if value_type == ValueType.STRING_LIST.value and not _is_null(value):
                value = json.loads(value)
            record[item["feature_code"]] = value
        rows.append(record)
    output = pd.DataFrame(rows, columns=[*group_by, *feature_order])
    type_by_feature = {
        str(item["feature_code"]): ValueType(str(item["value_type"]))
        for item in values.loc[:, ["feature_code", "value_type"]]
        .drop_duplicates()
        .to_dict(orient="records")
    }
    for name in feature_order:
        output[name] = _cast_column(output[name], type_by_feature[name])
    return output


def flatten_features(
    dataframe: pd.DataFrame,
    *,
    config: FeatureRulesConfig,
    strict: bool = False,
    run_id: str | None = None,
) -> FeatureFlattenResult:
    """Flatten a long feature table using one validated configuration."""

    frame = dataframe.copy(deep=True)
    input_spec = config.input
    required = set(input_spec.group_by) | {
        input_spec.competitor_field,
        input_spec.text_field,
        input_spec.included_field,
        *input_spec.deduplicate_by,
    }
    required.discard(input_spec.normalized_text_field)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise FeatureRulesExecutionError(
            f"Faltan columnas de entrada requeridas por las reglas: {', '.join(missing)}"
        )
    if input_spec.normalized_text_field not in frame:
        frame[input_spec.normalized_text_field] = frame[input_spec.text_field].map(normalized_key)
    missing_deduplication = sorted(set(input_spec.deduplicate_by) - set(frame.columns))
    if missing_deduplication:
        raise FeatureRulesExecutionError(
            f"No se pudieron calcular columnas de deduplicación: {', '.join(missing_deduplication)}"
        )
    frame[input_spec.included_field] = frame[input_spec.included_field].map(_input_boolean)
    if frame[list(input_spec.group_by)].isna().any(axis=None):
        raise FeatureRulesExecutionError("Las claves input.group_by no pueden contener nulos")

    before = len(frame)
    frame = frame.drop_duplicates(subset=list(input_spec.deduplicate_by), keep="first").copy()
    report = FeatureRulesReport(
        schema_version=config.schema_version,
        loaded_rules=tuple(rule.rule_id for rule in config.rules),
        exact_duplicates_removed=before - len(frame),
        canonical_columns=tuple(column.name for column in config.columns),
    )

    group_records: list[tuple[dict[str, Any], dict[str, list[Any]], dict[str, list[str]]]] = []
    dynamic_names: set[str] = set()
    columns_by_name = config.columns_by_name
    derived_names = {item.name for item in config.derived_columns}
    reserved = set(input_spec.group_by) | set(columns_by_name) | derived_names

    for raw_group_key, group in frame.groupby(list(input_spec.group_by), sort=False, dropna=False):
        group_key = raw_group_key if isinstance(raw_group_key, tuple) else (raw_group_key,)
        record = dict(zip(input_spec.group_by, group_key, strict=True))
        competitor = str(record[input_spec.competitor_field])
        competitor_spec = config.competitors.get(competitor)
        if competitor_spec is None:
            report.unknown_competitors[competitor] += 1
            if config.behavior.unknown_competitor == "error" or strict:
                raise FeatureRulesExecutionError(
                    f"Competidor sin configuración: {competitor}", report=report
                )
        rules = _rules_for(config, competitor)
        contributions: dict[str, list[Any]] = defaultdict(list)
        contribution_rules: dict[str, list[str]] = defaultdict(list)
        dynamic: dict[str, list[Any]] = defaultdict(list)

        for row_index, row in group.iterrows():
            matches = [(rule, _matches(rule, row)) for rule in rules]
            matches = [(rule, match) for rule, match in matches if match is not None]
            consuming = [rule.rule_id for rule, _ in matches if rule.consume]
            if len(consuming) > 1:
                conflict = {"row": int(row_index), "rules": consuming}
                report.multiple_matches.append(conflict)
                if config.behavior.multiple_matching_rules == "error" or strict:
                    raise FeatureRulesExecutionError(
                        f"La fila {row_index} coincide con varias reglas consumidoras: "
                        f"{', '.join(consuming)}",
                        report=report,
                    )
            consumed = False
            for rule, match in matches:
                report.match_counts[rule.rule_id] += 1
                for output in rule.outputs:
                    try:
                        raw_value = _source_value(rule, output, row, match)
                        value = _coerce(raw_value, columns_by_name[output.column].value_type)
                    except (ValueError, TypeError) as exc:
                        detail = {
                            "row": int(row_index),
                            "rule": rule.rule_id,
                            "column": output.column,
                            "value": row.get(rule.when.field),
                            "error": str(exc),
                        }
                        report.invalid_captures.append(detail)
                        if config.behavior.invalid_capture == "error" or strict:
                            raise FeatureRulesExecutionError(
                                f"Captura inválida en {rule.rule_id}/{output.column}: {exc}",
                                report=report,
                            ) from exc
                        continue
                    contributions[output.column].append(value)
                    contribution_rules[output.column].append(rule.rule_id)
                if rule.consume:
                    consumed = True
                    report.rows_consumed += 1
                    break

            if consumed:
                continue
            fallback = config.behavior.unmatched
            raw_name = row.get(fallback.column_from, pd.NA)
            display_name = "" if _is_null(raw_name) else str(raw_name)
            report.unmatched_features[display_name or "(nulo)"] += 1
            if fallback.mode == "error":
                raise FeatureRulesExecutionError(
                    f"Característica sin regla en fila {row_index}: {display_name or '(nulo)'}",
                    report=report,
                )
            if fallback.mode == "ignore":
                continue
            normalized = normalized_key(f"{fallback.prefix}{display_name}")
            if _is_null(normalized):
                raise FeatureRulesExecutionError(
                    f"La característica de la fila {row_index} no produce una columna válida",
                    report=report,
                )
            dynamic_name = str(normalized)
            if dynamic_name in reserved:
                report.column_collisions.append(dynamic_name)
                raise FeatureRulesExecutionError(
                    f"La columna dinámica {dynamic_name} colisiona con una columna reservada",
                    report=report,
                )
            value = _coerce(row.get(fallback.value_from, pd.NA), ValueType.BOOLEAN)
            dynamic[dynamic_name].append(value)
            dynamic_names.add(dynamic_name)
            report.fallback_rows += 1

        competitor_defaults = competitor_spec.column_defaults if competitor_spec else {}
        for column in config.columns:
            default = competitor_defaults.get(column.name, column.default)
            reduced = _reduce(
                contributions[column.name],
                reducer=column.reducer,
                default=default,
                column=column.name,
                report=report,
            )
            record[column.name] = _render_reduced(reduced, column)
        for derived in config.derived_columns:
            _derive_value(derived, record, config, set())
        group_records.append((record, dynamic, contribution_rules))

    ordered_dynamic = tuple(sorted(dynamic_names))
    report.dynamic_columns = ordered_dynamic
    value_records: list[dict[str, Any]] = []
    fallback = config.behavior.unmatched
    for record, dynamic, contribution_rules in group_records:
        for name in ordered_dynamic:
            record[name] = _reduce(
                dynamic[name],
                reducer=fallback.reducer,
                default=fallback.default,
                column=name,
                report=report,
            )
        for column in config.columns:
            rules = tuple(dict.fromkeys(contribution_rules[column.name]))
            value_records.append(
                _feature_value_record(
                    run_id=run_id,
                    group=record,
                    feature_code=column.name,
                    value_type=column.value_type,
                    value=record[column.name],
                    origin="rule" if rules else "default",
                    rule_id="|".join(rules) if rules else None,
                    is_derived=False,
                )
            )
        for derived in config.derived_columns:
            value_records.append(
                _feature_value_record(
                    run_id=run_id,
                    group=record,
                    feature_code=derived.name,
                    value_type=derived.value_type,
                    value=record[derived.name],
                    origin="derived",
                    rule_id=None,
                    is_derived=True,
                )
            )
        for name in ordered_dynamic:
            value_records.append(
                _feature_value_record(
                    run_id=run_id,
                    group=record,
                    feature_code=name,
                    value_type=ValueType.BOOLEAN,
                    value=record[name],
                    origin="fallback" if dynamic[name] else "default",
                    rule_id=None,
                    is_derived=False,
                )
            )
    values = pd.DataFrame(value_records, columns=FEATURE_VALUE_COLUMNS)
    feature_order = (
        *(column.name for column in config.columns),
        *(column.name for column in config.derived_columns),
        *ordered_dynamic,
    )
    output = wide_from_feature_values(
        values,
        group_by=input_spec.group_by,
        feature_order=feature_order,
    )
    return FeatureFlattenResult(dataframe=output, values_dataframe=values, report=report)
