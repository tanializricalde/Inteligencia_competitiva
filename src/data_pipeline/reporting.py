"""Serializable quality report shared by cleaning and transformation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_pipeline.errors import PipelineIssue
from data_pipeline.policies import PolicyApplication
from data_pipeline.profiles import DatasetType

RULES_VERSION = "cleanup-transformation-v2"


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        return value.item()
    return str(value)


@dataclass(frozen=True, slots=True)
class QualityReport:
    dataset_type: DatasetType
    input_rows: int
    output_rows: int
    rejected_rows: int = 0
    removed_rows: int = 0
    empty_columns_removed: tuple[str, ...] = ()
    nulls_by_column: dict[str, int] = field(default_factory=dict)
    numeric_policies: tuple[PolicyApplication, ...] = ()
    exact_duplicates_removed: int = 0
    duplicate_key_rows: int = 0
    normalization_collisions: int = 0
    orphan_keys: int = 0
    out_of_range_values: int = 0
    possibly_truncated_responses: int = 0
    price_discrepancies: int = 0
    conversion_failures: int = 0
    issues: tuple[PipelineIssue, ...] = ()
    rules_version: str = RULES_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_type": self.dataset_type.value,
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "rejected_rows": self.rejected_rows,
            "removed_rows": self.removed_rows,
            "empty_columns_removed": list(self.empty_columns_removed),
            "nulls_by_column": self.nulls_by_column,
            "numeric_policies": [item.as_dict() for item in self.numeric_policies],
            "exact_duplicates_removed": self.exact_duplicates_removed,
            "duplicate_key_rows": self.duplicate_key_rows,
            "normalization_collisions": self.normalization_collisions,
            "orphan_keys": self.orphan_keys,
            "out_of_range_values": self.out_of_range_values,
            "possibly_truncated_responses": self.possibly_truncated_responses,
            "price_discrepancies": self.price_discrepancies,
            "conversion_failures": self.conversion_failures,
            "issues": [
                {
                    "code": issue.code,
                    "message": issue.message,
                    "column": issue.column,
                    "row": issue.row,
                    "value": _json_value(issue.value),
                }
                for issue in self.issues
            ],
            "rules_version": self.rules_version,
        }
