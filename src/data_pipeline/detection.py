"""Conservative dataset-type detection shared by both pipeline stages."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from data_pipeline.errors import DatasetDetectionError
from data_pipeline.profiles import PROFILES, DatasetType

PATH_TOKENS = {
    DatasetType.REVIEW: {"review", "reviews", "resena", "resenas"},
    DatasetType.PLAN: {"plan", "plans", "planes"},
    DatasetType.FEATURE: {"feature", "features", "caracteristica", "caracteristicas"},
}


def _path_candidates(path: str | Path) -> set[DatasetType]:
    raw_tokens = re.split(r"[^a-z0-9áéíóúñ]+", str(path).casefold())
    normalized = {
        token.translate(str.maketrans("áéíóúñ", "aeioun")) for token in raw_tokens if token
    }
    candidates = {
        dataset_type
        for dataset_type, tokens in PATH_TOKENS.items()
        if normalized.intersection(tokens)
    }
    # The public filename is ``plan_features``: "feature" is the specific signal.
    if DatasetType.FEATURE in candidates:
        candidates.discard(DatasetType.PLAN)
    return candidates


def _column_candidates(columns: Iterable[object]) -> set[DatasetType]:
    names = {str(column) for column in columns}
    return {
        dataset_type
        for dataset_type, profile in PROFILES.items()
        if profile.signature.issubset(names)
    }


def _inspect_columns(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        raise DatasetDetectionError(f"No existe el archivo de entrada: {path}")
    suffix = path.suffix.casefold()
    try:
        if suffix == ".csv":
            return tuple(pd.read_csv(path, nrows=0, encoding="utf-8").columns)
        if suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
                raise DatasetDetectionError(
                    "JSON debe ser un arreglo no vacío de objetos para detectar su tipo"
                )
            return tuple(payload[0])
    except (OSError, UnicodeError, json.JSONDecodeError, pd.errors.ParserError) as exc:
        raise DatasetDetectionError(f"No se pudo inspeccionar {path}: {exc}") from exc
    raise DatasetDetectionError(
        f"Extensión no soportada para detección: {path.suffix or '(sin extensión)'}"
    )


def detect_dataset_type(path: str | Path, columns: Iterable[object] | None = None) -> DatasetType:
    """Infer a type only when path and canonical signatures do not conflict."""

    source = Path(path)
    inspected_columns = tuple(columns) if columns is not None else _inspect_columns(source)
    path_matches = _path_candidates(source)
    column_matches = _column_candidates(inspected_columns)
    found = ", ".join(sorted(str(column) for column in inspected_columns)) or "(ninguna)"

    if len(path_matches) > 1 or len(column_matches) > 1:
        candidates = sorted((path_matches | column_matches), key=lambda item: item.value)
        names = ", ".join(item.value for item in candidates)
        raise DatasetDetectionError(
            f"Tipo ambiguo ({names}); columnas encontradas: {found}. Usa --type explícitamente."
        )
    path_type = next(iter(path_matches), None)
    column_type = next(iter(column_matches), None)
    if path_type is not None and column_type is not None and path_type != column_type:
        raise DatasetDetectionError(
            f"Señales contradictorias: la ruta sugiere {path_type.value} y las columnas "
            f"sugieren {column_type.value}. Columnas: {found}. Usa --type explícitamente."
        )
    detected = column_type or path_type
    if detected is None:
        signatures = "; ".join(
            f"{kind.value}={sorted(profile.signature)}" for kind, profile in PROFILES.items()
        )
        raise DatasetDetectionError(
            f"No se pudo detectar el tipo. Columnas encontradas: {found}. "
            f"Firmas mínimas: {signatures}. Usa --type review|plan|feature."
        )
    return detected
