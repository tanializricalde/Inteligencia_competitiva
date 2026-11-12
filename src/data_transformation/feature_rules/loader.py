"""Strict JSON loader for versioned feature-equivalence rules."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from data_transformation.feature_rules.contracts import (
    BehaviorSpec,
    ColumnSpec,
    CompetitorSpec,
    ConditionSpec,
    DerivedColumnSpec,
    FeatureRulesConfig,
    FeatureRulesConfigError,
    InputSpec,
    OutputSpec,
    Reducer,
    RuleSpec,
    UnmatchedSpec,
    ValueSource,
    ValueType,
)

SUPPORTED_SCHEMA_VERSION = 1
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
FLAG_VALUES = {"IGNORECASE": re.IGNORECASE, "MULTILINE": re.MULTILINE}
REDUCERS_BY_TYPE = {
    ValueType.BOOLEAN: {Reducer.FIRST, Reducer.LAST, Reducer.ANY, Reducer.ALL, Reducer.ERROR},
    ValueType.INTEGER: {
        Reducer.SUM,
        Reducer.MAX,
        Reducer.MIN,
        Reducer.FIRST,
        Reducer.LAST,
        Reducer.ERROR,
    },
    ValueType.DECIMAL: {
        Reducer.SUM,
        Reducer.MAX,
        Reducer.MIN,
        Reducer.FIRST,
        Reducer.LAST,
        Reducer.ERROR,
    },
    ValueType.STRING: {
        Reducer.FIRST,
        Reducer.LAST,
        Reducer.JOIN_UNIQUE,
        Reducer.ERROR,
    },
    ValueType.STRING_LIST: {
        Reducer.FIRST,
        Reducer.LAST,
        Reducer.JOIN_UNIQUE,
        Reducer.ERROR,
    },
}


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FeatureRulesConfigError(f"{path} debe ser un objeto JSON")
    return value


def _sequence(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise FeatureRulesConfigError(f"{path} debe ser un arreglo JSON")
    return value


def _keys(
    value: dict[str, Any], *, path: str, allowed: set[str], required: set[str] = frozenset()
) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise FeatureRulesConfigError(f"{path} contiene claves desconocidas: {', '.join(unknown)}")
    if missing:
        raise FeatureRulesConfigError(f"{path} requiere: {', '.join(missing)}")


def _name(value: Any, path: str) -> str:
    if not isinstance(value, str) or not NAME_PATTERN.fullmatch(value):
        raise FeatureRulesConfigError(f"{path} debe ser un nombre snake_case válido")
    return value


def _string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise FeatureRulesConfigError(f"{path} debe ser una cadena no vacía")
    return value


def _string_list(value: Any, path: str, *, names: bool = False) -> tuple[str, ...]:
    items = _sequence(value, path)
    parsed = tuple(
        _name(item, f"{path}[{index}]") if names else _string(item, f"{path}[{index}]")
        for index, item in enumerate(items)
    )
    if len(set(parsed)) != len(parsed):
        raise FeatureRulesConfigError(f"{path} no permite valores duplicados")
    return parsed


def _typed_json(value: Any, value_type: ValueType, path: str) -> Any:
    if value is None:
        return None
    if value_type == ValueType.BOOLEAN:
        if not isinstance(value, bool):
            raise FeatureRulesConfigError(f"{path} debe ser boolean o null")
    elif value_type == ValueType.INTEGER:
        if not isinstance(value, int) or isinstance(value, bool):
            raise FeatureRulesConfigError(f"{path} debe ser integer o null")
    elif value_type == ValueType.DECIMAL:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise FeatureRulesConfigError(f"{path} debe ser decimal o null")
    elif value_type == ValueType.STRING:
        if not isinstance(value, str):
            raise FeatureRulesConfigError(f"{path} debe ser string o null")
    elif value_type == ValueType.STRING_LIST:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise FeatureRulesConfigError(f"{path} debe ser un arreglo de strings o null")
        return tuple(value)
    return value


def _enum(enum_type, value: Any, path: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in enum_type)
        raise FeatureRulesConfigError(f"{path} inválido; opciones: {choices}") from exc


def _parse_input(raw: Any) -> InputSpec:
    value = _mapping(raw, "input")
    required = {
        "group_by",
        "competitor_field",
        "text_field",
        "normalized_text_field",
        "included_field",
        "deduplicate_by",
    }
    _keys(value, path="input", allowed=required, required=required)
    result = InputSpec(
        group_by=_string_list(value["group_by"], "input.group_by", names=True),
        competitor_field=_name(value["competitor_field"], "input.competitor_field"),
        text_field=_name(value["text_field"], "input.text_field"),
        normalized_text_field=_name(value["normalized_text_field"], "input.normalized_text_field"),
        included_field=_name(value["included_field"], "input.included_field"),
        deduplicate_by=_string_list(value["deduplicate_by"], "input.deduplicate_by", names=True),
    )
    if not result.group_by or not result.deduplicate_by:
        raise FeatureRulesConfigError(
            "input.group_by y input.deduplicate_by no pueden estar vacíos"
        )
    if result.competitor_field not in result.group_by:
        raise FeatureRulesConfigError("input.competitor_field debe pertenecer a input.group_by")
    return result


def _parse_behavior(raw: Any) -> BehaviorSpec:
    value = _mapping(raw, "behavior")
    required = {
        "unknown_competitor",
        "multiple_matching_rules",
        "invalid_capture",
        "unmatched",
    }
    _keys(value, path="behavior", allowed=required, required=required)
    unknown_competitor = value["unknown_competitor"]
    multiple = value["multiple_matching_rules"]
    invalid_capture = value["invalid_capture"]
    if unknown_competitor not in {"fallback", "error"}:
        raise FeatureRulesConfigError("behavior.unknown_competitor debe ser fallback o error")
    if multiple not in {"error", "first"}:
        raise FeatureRulesConfigError("behavior.multiple_matching_rules debe ser error o first")
    if invalid_capture not in {"error", "report"}:
        raise FeatureRulesConfigError("behavior.invalid_capture debe ser error o report")
    unmatched = _mapping(value["unmatched"], "behavior.unmatched")
    unmatched_keys = {
        "mode",
        "column_from",
        "value_from",
        "reducer",
        "default",
        "prefix",
    }
    _keys(unmatched, path="behavior.unmatched", allowed=unmatched_keys, required=unmatched_keys)
    mode = unmatched["mode"]
    if mode not in {"dynamic_boolean", "ignore", "error"}:
        raise FeatureRulesConfigError(
            "behavior.unmatched.mode debe ser dynamic_boolean, ignore o error"
        )
    reducer = _enum(Reducer, unmatched["reducer"], "behavior.unmatched.reducer")
    if reducer not in REDUCERS_BY_TYPE[ValueType.BOOLEAN]:
        raise FeatureRulesConfigError("behavior.unmatched.reducer no es compatible con boolean")
    return BehaviorSpec(
        unknown_competitor=unknown_competitor,
        multiple_matching_rules=multiple,
        invalid_capture=invalid_capture,
        unmatched=UnmatchedSpec(
            mode=mode,
            column_from=_name(unmatched["column_from"], "behavior.unmatched.column_from"),
            value_from=_name(unmatched["value_from"], "behavior.unmatched.value_from"),
            reducer=reducer,
            default=_typed_json(
                unmatched["default"], ValueType.BOOLEAN, "behavior.unmatched.default"
            ),
            prefix=_string(unmatched["prefix"], "behavior.unmatched.prefix", allow_empty=True),
        ),
    )


def _parse_columns(raw: Any) -> tuple[ColumnSpec, ...]:
    value = _mapping(raw, "columns")
    if not value:
        raise FeatureRulesConfigError("columns no puede estar vacío")
    columns: list[ColumnSpec] = []
    for raw_name, raw_spec in value.items():
        name = _name(raw_name, f"columns.{raw_name}")
        path = f"columns.{name}"
        spec = _mapping(raw_spec, path)
        _keys(
            spec,
            path=path,
            allowed={"type", "default", "reducer", "tags", "label"},
            required={"type", "default", "reducer"},
        )
        value_type = _enum(ValueType, spec["type"], f"{path}.type")
        reducer = _enum(Reducer, spec["reducer"], f"{path}.reducer")
        if reducer not in REDUCERS_BY_TYPE[value_type]:
            raise FeatureRulesConfigError(
                f"{path}.reducer={reducer.value} no es compatible con {value_type.value}"
            )
        tags = _string_list(spec.get("tags", []), f"{path}.tags", names=True)
        label = spec.get("label")
        if label is not None:
            label = _string(label, f"{path}.label")
        columns.append(
            ColumnSpec(
                name=name,
                value_type=value_type,
                default=_typed_json(spec["default"], value_type, f"{path}.default"),
                reducer=reducer,
                tags=tags,
                label=label,
            )
        )
    return tuple(columns)


def _parse_derived(raw: Any, columns: tuple[ColumnSpec, ...]) -> tuple[DerivedColumnSpec, ...]:
    value = _mapping(raw, "derived_columns")
    canonical = {column.name: column for column in columns}
    derived: list[DerivedColumnSpec] = []
    names: set[str] = set()
    for raw_name, raw_spec in value.items():
        name = _name(raw_name, f"derived_columns.{raw_name}")
        path = f"derived_columns.{name}"
        if name in canonical:
            raise FeatureRulesConfigError(f"{path} colisiona con una columna canónica")
        names.add(name)
        spec = _mapping(raw_spec, path)
        _keys(
            spec,
            path=path,
            allowed={
                "type",
                "operation",
                "inputs",
                "select",
                "null_policy",
                "separator",
                "distinct",
                "default",
            },
            required={"type", "operation"},
        )
        value_type = _enum(ValueType, spec["type"], f"{path}.type")
        operation = spec["operation"]
        if operation not in {"sum_columns", "count_true", "join_labels"}:
            raise FeatureRulesConfigError(f"{path}.operation no está permitida")
        inputs = _string_list(spec.get("inputs", []), f"{path}.inputs", names=True)
        selection = spec.get("select", {})
        select_tag = None
        if selection:
            selection = _mapping(selection, f"{path}.select")
            _keys(selection, path=f"{path}.select", allowed={"tag"}, required={"tag"})
            select_tag = _name(selection["tag"], f"{path}.select.tag")
        default = _typed_json(spec.get("default"), value_type, f"{path}.default")
        derived.append(
            DerivedColumnSpec(
                name=name,
                value_type=value_type,
                operation=operation,
                inputs=inputs,
                select_tag=select_tag,
                null_policy=spec.get("null_policy"),
                separator=_string(
                    spec.get("separator", "|"), f"{path}.separator", allow_empty=True
                ),
                distinct=spec.get("distinct", True),
                default=default,
            )
        )
    all_types = {column.name: column.value_type for column in columns}
    all_types.update({item.name: item.value_type for item in derived})
    for item in derived:
        path = f"derived_columns.{item.name}"
        if item.operation == "sum_columns":
            if not item.inputs:
                raise FeatureRulesConfigError(f"{path}.inputs no puede estar vacío")
            unknown = sorted(set(item.inputs) - set(all_types))
            if unknown:
                raise FeatureRulesConfigError(
                    f"{path}.inputs referencia columnas inexistentes: {', '.join(unknown)}"
                )
            numeric = {ValueType.INTEGER, ValueType.DECIMAL}
            incompatible_input = any(all_types[name] not in numeric for name in item.inputs)
            if item.value_type not in numeric or incompatible_input:
                raise FeatureRulesConfigError(f"{path} sólo puede sumar columnas numéricas")
            if item.null_policy not in {None, "null_if_all_null"}:
                raise FeatureRulesConfigError(f"{path}.null_policy sólo admite null_if_all_null")
        else:
            if item.inputs:
                raise FeatureRulesConfigError(f"{path}.inputs no aplica a {item.operation}")
            if not item.select_tag:
                raise FeatureRulesConfigError(f"{path}.select.tag es obligatorio")
            selected = [column for column in columns if item.select_tag in column.tags]
            if not selected:
                raise FeatureRulesConfigError(f"{path}.select.tag no selecciona columnas")
            if any(column.value_type != ValueType.BOOLEAN for column in selected):
                raise FeatureRulesConfigError(f"{path}.select.tag debe seleccionar booleanos")
            if item.operation == "count_true" and item.value_type != ValueType.INTEGER:
                raise FeatureRulesConfigError(f"{path}.type debe ser integer")
            if item.operation == "join_labels":
                if item.value_type not in {ValueType.STRING, ValueType.STRING_LIST}:
                    raise FeatureRulesConfigError(f"{path}.type debe ser string o string_list")
                if any(not column.label for column in selected):
                    raise FeatureRulesConfigError(
                        f"{path} requiere label en todas las columnas seleccionadas"
                    )
        if not isinstance(item.distinct, bool):
            raise FeatureRulesConfigError(f"{path}.distinct debe ser boolean")
    _validate_derived_cycles(derived)
    return tuple(derived)


def _validate_derived_cycles(derived: list[DerivedColumnSpec]) -> None:
    derived_names = {item.name for item in derived}
    dependencies = {
        item.name: {name for name in item.inputs if name in derived_names} for item in derived
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            raise FeatureRulesConfigError(f"derived_columns contiene un ciclo en {name}")
        if name in visited:
            return
        visiting.add(name)
        for dependency in dependencies[name]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for name in dependencies:
        visit(name)


def _parse_condition(raw: Any, path: str) -> ConditionSpec:
    value = _mapping(raw, path)
    _keys(
        value,
        path=path,
        allowed={"field", "operator", "value", "pattern", "flags"},
        required={"field", "operator"},
    )
    field = _name(value["field"], f"{path}.field")
    operator = value["operator"]
    if operator == "equals":
        if "value" not in value or "pattern" in value or "flags" in value:
            raise FeatureRulesConfigError(
                f"{path} con equals requiere value y no admite pattern/flags"
            )
        return ConditionSpec(field=field, operator=operator, value=value["value"])
    if operator != "regex":
        raise FeatureRulesConfigError(f"{path}.operator debe ser equals o regex")
    if "pattern" not in value or "value" in value:
        raise FeatureRulesConfigError(f"{path} con regex requiere pattern y no admite value")
    pattern = _string(value["pattern"], f"{path}.pattern")
    flags = _string_list(value.get("flags", []), f"{path}.flags")
    unknown_flags = sorted(set(flags) - set(FLAG_VALUES))
    if unknown_flags:
        raise FeatureRulesConfigError(f"{path}.flags no permitidas: {', '.join(unknown_flags)}")
    try:
        compiled = re.compile(pattern, sum((FLAG_VALUES[flag] for flag in flags), re.NOFLAG))
    except re.error as exc:
        raise FeatureRulesConfigError(f"{path}.pattern inválido: {exc}") from exc
    return ConditionSpec(
        field=field,
        operator=operator,
        pattern=pattern,
        flags=flags,
        compiled=compiled,
    )


def _parse_rules(raw: Any, columns: tuple[ColumnSpec, ...]) -> dict[str, tuple[RuleSpec, ...]]:
    value = _mapping(raw, "rule_sets")
    column_map = {column.name: column for column in columns}
    rule_sets: dict[str, tuple[RuleSpec, ...]] = {}
    rule_ids: set[str] = set()
    declaration_order = 0
    for raw_set_name, raw_rules in value.items():
        set_name = _name(raw_set_name, f"rule_sets.{raw_set_name}")
        rules: list[RuleSpec] = []
        for index, raw_rule in enumerate(_sequence(raw_rules, f"rule_sets.{set_name}")):
            path = f"rule_sets.{set_name}[{index}]"
            rule = _mapping(raw_rule, path)
            _keys(
                rule,
                path=path,
                allowed={"id", "priority", "when", "outputs", "consume"},
                required={"id", "priority", "when", "outputs", "consume"},
            )
            rule_id = _name(rule["id"], f"{path}.id")
            if rule_id in rule_ids:
                raise FeatureRulesConfigError(f"ID de regla duplicado: {rule_id}")
            rule_ids.add(rule_id)
            priority = rule["priority"]
            if not isinstance(priority, int) or isinstance(priority, bool):
                raise FeatureRulesConfigError(f"{path}.priority debe ser integer")
            if not isinstance(rule["consume"], bool):
                raise FeatureRulesConfigError(f"{path}.consume debe ser boolean")
            condition = _parse_condition(rule["when"], f"{path}.when")
            outputs: list[OutputSpec] = []
            for output_index, raw_output in enumerate(
                _sequence(rule["outputs"], f"{path}.outputs")
            ):
                output_path = f"{path}.outputs[{output_index}]"
                output = _mapping(raw_output, output_path)
                _keys(
                    output,
                    path=output_path,
                    allowed={"column", "value"},
                    required={"column", "value"},
                )
                column = _name(output["column"], f"{output_path}.column")
                if column not in column_map:
                    raise FeatureRulesConfigError(
                        f"{output_path}.column referencia una columna inexistente: {column}"
                    )
                source = _mapping(output["value"], f"{output_path}.value")
                source_keys = set(source).intersection({"capture", "literal", "field"})
                if len(source_keys) != 1 or set(source) != source_keys:
                    raise FeatureRulesConfigError(
                        f"{output_path}.value debe declarar exactamente capture, literal o field"
                    )
                kind = next(iter(source_keys))
                source_value = source[kind]
                if kind in {"capture", "field"}:
                    source_value = _name(source_value, f"{output_path}.value.{kind}")
                invalid_capture = kind == "capture" and (
                    condition.operator != "regex"
                    or source_value not in condition.compiled.groupindex
                )
                if invalid_capture:
                    raise FeatureRulesConfigError(
                        f"{output_path} referencia una captura inexistente: {source_value}"
                    )
                if kind == "literal":
                    source_value = _typed_json(
                        source_value,
                        column_map[column].value_type,
                        f"{output_path}.value.literal",
                    )
                outputs.append(
                    OutputSpec(column=column, source=ValueSource(kind=kind, value=source_value))
                )
            if not outputs:
                raise FeatureRulesConfigError(f"{path}.outputs no puede estar vacío")
            rules.append(
                RuleSpec(
                    rule_id=rule_id,
                    priority=priority,
                    when=condition,
                    outputs=tuple(outputs),
                    consume=rule["consume"],
                    declaration_order=declaration_order,
                )
            )
            declaration_order += 1
        rule_sets[set_name] = tuple(rules)
    return rule_sets


def _parse_competitors(
    raw: Any,
    *,
    rule_sets: dict[str, tuple[RuleSpec, ...]],
    columns: tuple[ColumnSpec, ...],
) -> dict[str, CompetitorSpec]:
    value = _mapping(raw, "competitors")
    column_map = {column.name: column for column in columns}
    competitors: dict[str, CompetitorSpec] = {}
    for raw_name, raw_spec in value.items():
        name = _name(raw_name, f"competitors.{raw_name}")
        path = f"competitors.{name}"
        spec = _mapping(raw_spec, path)
        _keys(
            spec,
            path=path,
            allowed={"rule_sets", "column_defaults"},
            required={"rule_sets"},
        )
        selected_rule_sets = _string_list(spec["rule_sets"], f"{path}.rule_sets", names=True)
        unknown_sets = sorted(set(selected_rule_sets) - set(rule_sets))
        if unknown_sets:
            raise FeatureRulesConfigError(
                f"{path}.rule_sets referencia conjuntos inexistentes: {', '.join(unknown_sets)}"
            )
        defaults = _mapping(spec.get("column_defaults", {}), f"{path}.column_defaults")
        unknown_columns = sorted(set(defaults) - set(column_map))
        if unknown_columns:
            raise FeatureRulesConfigError(
                f"{path}.column_defaults referencia columnas inexistentes: "
                f"{', '.join(unknown_columns)}"
            )
        competitors[name] = CompetitorSpec(
            rule_sets=selected_rule_sets,
            column_defaults={
                column: _typed_json(
                    default,
                    column_map[column].value_type,
                    f"{path}.column_defaults.{column}",
                )
                for column, default in defaults.items()
            },
        )
    return competitors


def _parse(payload: Any) -> FeatureRulesConfig:
    root = _mapping(payload, "raíz")
    required = {
        "schema_version",
        "input",
        "behavior",
        "columns",
        "derived_columns",
        "rule_sets",
        "competitors",
    }
    _keys(root, path="raíz", allowed={*required, "$schema"}, required=required)
    if root["schema_version"] != SUPPORTED_SCHEMA_VERSION:
        raise FeatureRulesConfigError(
            f"schema_version no soportada: {root['schema_version']!r}; "
            f"se esperaba {SUPPORTED_SCHEMA_VERSION}"
        )
    input_spec = _parse_input(root["input"])
    behavior = _parse_behavior(root["behavior"])
    columns = _parse_columns(root["columns"])
    derived = _parse_derived(root["derived_columns"], columns)
    reserved = set(input_spec.group_by)
    collisions = sorted(
        reserved.intersection({column.name for column in columns}).union(
            reserved.intersection({column.name for column in derived})
        )
    )
    if collisions:
        raise FeatureRulesConfigError(
            f"Columnas configuradas colisionan con group_by: {', '.join(collisions)}"
        )
    rule_sets = _parse_rules(root["rule_sets"], columns)
    competitors = _parse_competitors(root["competitors"], rule_sets=rule_sets, columns=columns)
    return FeatureRulesConfig(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        input=input_spec,
        behavior=behavior,
        columns=columns,
        derived_columns=derived,
        rule_sets=rule_sets,
        competitors=competitors,
    )


def load_feature_rules(path: str | Path) -> FeatureRulesConfig:
    """Load and fully validate a schema-v1 JSON document before dataset processing."""

    source = Path(path)
    if not source.is_file():
        raise FeatureRulesConfigError(f"No existe el archivo de reglas: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FeatureRulesConfigError(
            f"No se pudo leer el archivo de reglas {source}: {exc}"
        ) from exc
    return parse_feature_rules(payload)


def parse_feature_rules(payload: Any) -> FeatureRulesConfig:
    """Validate an already decoded document for file, Django or API callers."""

    return _parse(payload)
