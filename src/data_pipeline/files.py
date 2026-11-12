"""Safe UTF-8 CSV and JSON array I/O for small tabular datasets."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from data_pipeline.errors import DatasetIOError

SUPPORTED_SUFFIXES = frozenset({".csv", ".json"})


def discover_input_files(paths: Sequence[str | Path]) -> tuple[Path, ...]:
    """Expand files and directories recursively into unique supported input files."""

    discovered: dict[Path, Path] = {}
    try:
        for raw_path in paths:
            source = Path(raw_path)
            if not source.exists():
                raise DatasetIOError(f"No existe la entrada: {source}")
            if source.is_symlink():
                raise DatasetIOError(f"No se permiten enlaces simbólicos como entrada: {source}")
            if source.is_file():
                if source.suffix.casefold() not in SUPPORTED_SUFFIXES:
                    raise DatasetIOError(
                        f"Formato de entrada no soportado para {source}; usa .csv o .json"
                    )
                candidates = (source,)
            elif source.is_dir():
                candidates = tuple(
                    candidate
                    for candidate in sorted(
                        source.rglob("*"), key=lambda item: str(item).casefold()
                    )
                    if candidate.is_file()
                    and not candidate.is_symlink()
                    and candidate.suffix.casefold() in SUPPORTED_SUFFIXES
                )
            else:
                raise DatasetIOError(f"La entrada no es un archivo ni una carpeta: {source}")
            for candidate in candidates:
                resolved = candidate.resolve()
                discovered.setdefault(resolved, candidate)
    except OSError as exc:
        raise DatasetIOError(f"No se pudieron inspeccionar las entradas: {exc}") from exc
    if not discovered:
        raise DatasetIOError("No se encontraron archivos CSV o JSON en las entradas")
    return tuple(discovered[resolved] for resolved in sorted(discovered, key=str))


def infer_format(path: str | Path, explicit: str | None = None) -> str:
    if explicit is not None:
        if explicit not in {"csv", "json"}:
            raise DatasetIOError(f"Formato no soportado: {explicit}")
        return explicit
    suffix = Path(path).suffix.casefold().lstrip(".")
    if suffix not in {"csv", "json"}:
        raise DatasetIOError("No se pudo inferir el formato; usa una extensión .csv o .json")
    return suffix


def read_dataset(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if not source.is_file():
        raise DatasetIOError(f"No existe el archivo de entrada: {source}")
    input_format = infer_format(source)
    try:
        if input_format == "csv":
            frame = pd.read_csv(
                source,
                dtype="string",
                encoding="utf-8",
                keep_default_na=False,
                na_filter=False,
            )
        else:
            payload = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
                raise DatasetIOError("JSON debe contener un arreglo raíz de objetos")
            frame = pd.DataFrame(payload)
    except DatasetIOError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, pd.errors.ParserError) as exc:
        raise DatasetIOError(f"No se pudo leer {source}: {exc}") from exc
    if frame.columns.duplicated().any():
        duplicated = sorted(set(frame.columns[frame.columns.duplicated()].astype(str)))
        raise DatasetIOError(f"Columnas duplicadas no permitidas: {', '.join(duplicated)}")
    frame.columns = [str(column) for column in frame.columns]
    return frame


def _json_scalar(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "item"):
        return value.item()
    return value


def _csv_scalar(value: Any, *, null_value: str = "") -> Any:
    value = _json_scalar(value)
    if value is None:
        return null_value
    if isinstance(value, (list, tuple)):
        return "|".join(str(item) for item in value)
    if value is True:
        return "TRUE"
    if value is False:
        return "FALSE"
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _write(
    stream,
    frame: pd.DataFrame,
    output_format: str,
    *,
    csv_null_value: str = "",
) -> None:
    if output_format == "csv":
        writer = csv.DictWriter(stream, fieldnames=list(frame.columns), lineterminator="\n")
        writer.writeheader()
        for row in frame.to_dict(orient="records"):
            writer.writerow(
                {key: _csv_scalar(value, null_value=csv_null_value) for key, value in row.items()}
            )
        return
    records = [
        {str(key): _json_scalar(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]
    json.dump(records, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    stream.write("\n")


def write_dataset(
    frame: pd.DataFrame,
    path: str | Path,
    *,
    output_format: str | None = None,
    overwrite: bool = False,
    input_path: str | Path | None = None,
    csv_null_value: str = "",
) -> Path:
    target = Path(path)
    if input_path is not None and target.resolve() == Path(input_path).resolve():
        raise DatasetIOError("La salida no puede sobrescribir el archivo de entrada")
    resolved_format = infer_format(target, output_format)
    if target.exists() and not overwrite:
        raise DatasetIOError(f"El archivo ya existe (usa --overwrite): {target}")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            _write(stream, frame, resolved_format, csv_null_value=csv_null_value)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target)
            except FileExistsError as exc:
                raise DatasetIOError(f"El archivo ya existe (usa --overwrite): {target}") from exc
            temporary.unlink()
            temporary = None
        return target
    except DatasetIOError:
        raise
    except OSError as exc:
        raise DatasetIOError(f"No se pudo escribir {target}: {exc}") from exc
    finally:
        if "temporary" in locals() and temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json_report(payload: Any, path: str | Path, *, overwrite: bool = False) -> Path:
    """Publish a JSON quality report atomically with the same overwrite policy as datasets."""

    target = Path(path)
    if target.exists() and not overwrite:
        raise DatasetIOError(f"El archivo ya existe (usa --overwrite): {target}")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target)
            except FileExistsError as exc:
                raise DatasetIOError(f"El archivo ya existe (usa --overwrite): {target}") from exc
            temporary.unlink()
            temporary = None
        return target
    except DatasetIOError:
        raise
    except OSError as exc:
        raise DatasetIOError(f"No se pudo escribir {target}: {exc}") from exc
    finally:
        if "temporary" in locals() and temporary is not None:
            temporary.unlink(missing_ok=True)
