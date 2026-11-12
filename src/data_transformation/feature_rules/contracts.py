"""Typed contracts for feature-equivalence configuration and reports."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

import pandas as pd


class FeatureRulesConfigError(ValueError):
    """Raised before processing when a feature-rules document is invalid."""


class FeatureRulesExecutionError(ValueError):
    """Raised when configured runtime behavior declares a data conflict fatal."""

    def __init__(self, message: str, *, report: FeatureRulesReport | None = None) -> None:
        super().__init__(message)
        self.feature_rules_report = report


class ValueType(StrEnum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    DECIMAL = "decimal"
    STRING = "string"
    STRING_LIST = "string_list"


class Reducer(StrEnum):
    SUM = "sum"
    MAX = "max"
    MIN = "min"
    FIRST = "first"
    LAST = "last"
    ANY = "any"
    ALL = "all"
    JOIN_UNIQUE = "join_unique"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class InputSpec:
    group_by: tuple[str, ...]
    competitor_field: str
    text_field: str
    normalized_text_field: str
    included_field: str
    deduplicate_by: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UnmatchedSpec:
    mode: str
    column_from: str
    value_from: str
    reducer: Reducer
    default: Any
    prefix: str


@dataclass(frozen=True, slots=True)
class BehaviorSpec:
    unknown_competitor: str
    multiple_matching_rules: str
    invalid_capture: str
    unmatched: UnmatchedSpec


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    name: str
    value_type: ValueType
    default: Any
    reducer: Reducer
    tags: tuple[str, ...] = ()
    label: str | None = None


@dataclass(frozen=True, slots=True)
class DerivedColumnSpec:
    name: str
    value_type: ValueType
    operation: str
    inputs: tuple[str, ...] = ()
    select_tag: str | None = None
    null_policy: str | None = None
    separator: str = "|"
    distinct: bool = True
    default: Any = None


@dataclass(frozen=True, slots=True)
class ConditionSpec:
    field: str
    operator: str
    value: Any = None
    pattern: str | None = None
    flags: tuple[str, ...] = ()
    compiled: re.Pattern[str] | None = None


@dataclass(frozen=True, slots=True)
class ValueSource:
    kind: str
    value: Any


@dataclass(frozen=True, slots=True)
class OutputSpec:
    column: str
    source: ValueSource


@dataclass(frozen=True, slots=True)
class RuleSpec:
    rule_id: str
    priority: int
    when: ConditionSpec
    outputs: tuple[OutputSpec, ...]
    consume: bool
    declaration_order: int


@dataclass(frozen=True, slots=True)
class CompetitorSpec:
    rule_sets: tuple[str, ...]
    column_defaults: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FeatureRulesConfig:
    schema_version: int
    input: InputSpec
    behavior: BehaviorSpec
    columns: tuple[ColumnSpec, ...]
    derived_columns: tuple[DerivedColumnSpec, ...]
    rule_sets: dict[str, tuple[RuleSpec, ...]]
    competitors: dict[str, CompetitorSpec]

    @property
    def columns_by_name(self) -> dict[str, ColumnSpec]:
        return {column.name: column for column in self.columns}

    @property
    def derived_by_name(self) -> dict[str, DerivedColumnSpec]:
        return {column.name: column for column in self.derived_columns}

    @property
    def rules(self) -> tuple[RuleSpec, ...]:
        return tuple(rule for rules in self.rule_sets.values() for rule in rules)


def _json_value(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        return value.item()
    return str(value)


@dataclass(slots=True)
class FeatureRulesReport:
    schema_version: int
    loaded_rules: tuple[str, ...]
    match_counts: Counter[str] = field(default_factory=Counter)
    rows_consumed: int = 0
    fallback_rows: int = 0
    unmatched_features: Counter[str] = field(default_factory=Counter)
    invalid_captures: list[dict[str, Any]] = field(default_factory=list)
    multiple_matches: list[dict[str, Any]] = field(default_factory=list)
    exact_duplicates_removed: int = 0
    column_collisions: list[str] = field(default_factory=list)
    unknown_competitors: Counter[str] = field(default_factory=Counter)
    canonical_columns: tuple[str, ...] = ()
    dynamic_columns: tuple[str, ...] = ()

    @property
    def used_rules(self) -> tuple[str, ...]:
        return tuple(rule for rule in self.loaded_rules if self.match_counts[rule] > 0)

    @property
    def unused_rules(self) -> tuple[str, ...]:
        return tuple(rule for rule in self.loaded_rules if self.match_counts[rule] == 0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rules_loaded": list(self.loaded_rules),
            "rules_used": list(self.used_rules),
            "match_counts": {rule: self.match_counts[rule] for rule in self.loaded_rules},
            "unused_rules": list(self.unused_rules),
            "rows_consumed": self.rows_consumed,
            "fallback_rows": self.fallback_rows,
            "unmatched_features": [
                {"feature": name, "count": count}
                for name, count in self.unmatched_features.most_common()
            ],
            "invalid_captures": [
                {key: _json_value(value) for key, value in item.items()}
                for item in self.invalid_captures
            ],
            "multiple_matches": self.multiple_matches,
            "exact_duplicates_removed": self.exact_duplicates_removed,
            "column_collisions": self.column_collisions,
            "unknown_competitors": dict(self.unknown_competitors),
            "canonical_columns": list(self.canonical_columns),
            "dynamic_columns": list(self.dynamic_columns),
        }


@dataclass(frozen=True, slots=True)
class FeatureFlattenResult:
    dataframe: pd.DataFrame
    values_dataframe: pd.DataFrame
    report: FeatureRulesReport
