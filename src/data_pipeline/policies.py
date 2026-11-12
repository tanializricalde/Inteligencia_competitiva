"""Explicit numeric missing-value policies for known scraper fields."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from data_pipeline.profiles import DatasetType


class NumericStrategy(StrEnum):
    KEEP_NA = "keep_na"
    ZERO = "zero"
    MEAN = "mean"
    MEDIAN = "median"
    FIXED = "fixed"
    REJECT = "reject"
    DROP_ROW = "drop_row"


@dataclass(frozen=True, slots=True)
class NumericPolicy:
    strategy: NumericStrategy
    justification: str
    value: Any = None

    def __post_init__(self) -> None:
        if self.strategy == NumericStrategy.FIXED and self.value is None:
            raise ValueError("La estrategia fixed requiere un valor")


@dataclass(frozen=True, slots=True)
class PolicyApplication:
    column: str
    strategy: NumericStrategy
    affected_rows: int
    value: Any = None
    column_present: bool = True

    def as_dict(self) -> dict[str, Any]:
        value = float(self.value) if isinstance(self.value, Decimal) else self.value
        return {
            "column": self.column,
            "strategy": self.strategy.value,
            "affected_rows": self.affected_rows,
            "value": value,
            "column_present": self.column_present,
        }


KEEP_UNKNOWN = "No existe una inferencia de dominio segura para este campo."

NUMERIC_POLICIES: dict[DatasetType, dict[str, NumericPolicy]] = {
    DatasetType.REVIEW: {
        "calificacion_estrellas": NumericPolicy(
            NumericStrategy.KEEP_NA,
            "Una calificación ausente no puede inferirse.",
        ),
        "likes_comentario": NumericPolicy(
            NumericStrategy.KEEP_NA,
            "La ausencia no demuestra que la reseña tenga cero votos.",
        ),
        "dias_para_responder": NumericPolicy(
            NumericStrategy.KEEP_NA,
            "Se calcula sólo cuando existen ambas fechas.",
        ),
    },
    DatasetType.PLAN: {
        "precio_mensual": NumericPolicy(NumericStrategy.KEEP_NA, KEEP_UNKNOWN),
        "precio_anual_total": NumericPolicy(NumericStrategy.KEEP_NA, KEEP_UNKNOWN),
        "precio_mensual_efectivo": NumericPolicy(NumericStrategy.KEEP_NA, KEEP_UNKNOWN),
        "descuento_anual_pct": NumericPolicy(NumericStrategy.KEEP_NA, KEEP_UNKNOWN),
    },
    DatasetType.FEATURE: {
        "costo_adicional": NumericPolicy(
            NumericStrategy.KEEP_NA,
            "Un costo desconocido no equivale a cero.",
        ),
    },
}


def get_numeric_policies(dataset_type: DatasetType | str) -> dict[str, NumericPolicy]:
    """Return an independent mapping so callers can override policies safely."""

    return dict(NUMERIC_POLICIES[DatasetType(dataset_type)])
