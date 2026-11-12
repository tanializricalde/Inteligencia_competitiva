"""Contract-validation and atomic CSV/JSON exporters."""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, TextIO


class OutputError(RuntimeError):
    pass


def validate_rows(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    expected = set(fields)
    for index, row in enumerate(rows):
        actual = set(row)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise OutputError(f"fila {index}: faltan={missing}; sobran={extra}")


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if value is True:
        return "TRUE"
    if value is False:
        return "FALSE"
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _write_csv(stream: TextIO, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_value(row[key]) for key in fields})


def _write_json(stream: TextIO, rows: list[dict[str, Any]], *, pretty: bool) -> None:
    json.dump(
        rows,
        stream,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        default=_json_value,
    )
    stream.write("\n")


def export_rows(
    rows: list[dict[str, Any]],
    fields: tuple[str, ...],
    *,
    output_format: str,
    output: str | Path,
    pretty: bool = False,
    overwrite: bool = False,
) -> None:
    validate_rows(rows, fields)
    if str(output) == "-":
        if output_format == "csv":
            _write_csv(sys.stdout, rows, fields)
        else:
            _write_json(sys.stdout, rows, pretty=pretty)
        return
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise OutputError(f"El archivo ya existe (usa --overwrite): {target}")
    temporary: Path | None = None
    try:
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
            if output_format == "csv":
                _write_csv(stream, rows, fields)
            elif output_format == "json":
                _write_json(stream, rows, pretty=pretty)
            else:
                raise OutputError(f"Formato no soportado: {output_format}")
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target)
            except FileExistsError as exc:
                raise OutputError(f"El archivo ya existe (usa --overwrite): {target}") from exc
            temporary.unlink()
            temporary = None
    except OSError as exc:
        raise OutputError(f"No se pudo escribir {target}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
