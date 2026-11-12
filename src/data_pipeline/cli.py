"""Shared command-line behavior for both post-scraping stages."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from data_pipeline.detection import detect_dataset_type
from data_pipeline.errors import (
    DatasetDetectionError,
    DatasetIOError,
    PipelineIssue,
    PipelineValidationError,
)
from data_pipeline.files import discover_input_files, read_dataset, write_dataset, write_json_report
from data_pipeline.profiles import DatasetType

EXIT_USAGE = 2
EXIT_WARNINGS = 4
EXIT_OUTPUT = 5
DEFAULT_FILENAMES = {
    DatasetType.REVIEW: "reviews",
    DatasetType.PLAN: "plans",
    DatasetType.FEATURE: "features",
}


class PipelineResult(Protocol):
    data: pd.DataFrame
    dataset_type: DatasetType
    issues: tuple[PipelineIssue, ...]
    input_rows: int
    output_rows: int
    report: object


def build_parser(
    prog: str, description: str, stage: str, *, enable_feature_rules: bool = False
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            f"  {prog} data/raw/reviews.csv --output data/{stage}/reviews.csv\n"
            f"  {prog} input-a input-b --type review --output data/{stage}/reviews.csv\n"
            f"  {prog} data/raw --output-dir data/{stage} --plan-filename catalogo.csv"
        ),
    )
    parser.add_argument(
        "input",
        nargs="+",
        metavar="INPUT_PATH",
        help="uno o más archivos o carpetas; las carpetas se recorren recursivamente",
    )
    parser.add_argument(
        "--output",
        metavar="OUTPUT_PATH",
        help="archivo de salida; sólo admite un tipo consolidado",
    )
    parser.add_argument(
        "--output-dir",
        metavar="OUTPUT_DIR",
        help="carpeta para una salida por cada tipo detectado",
    )
    for dataset_type in DatasetType:
        parser.add_argument(
            f"--{dataset_type.value}-filename",
            metavar="NAME",
            help=f"nombre de la salida {dataset_type.value} dentro de --output-dir",
        )
    parser.add_argument(
        "--type",
        choices=("auto", "review", "plan", "feature"),
        default="auto",
        help="tipo de datos; auto combina ruta y columnas (predeterminado: auto)",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "json"),
        help="formato de salida; se infiere de la extensión si se omite",
    )
    parser.add_argument(
        "--csv-null-value",
        metavar="TEXT",
        default="",
        help="texto para valores nulos en salidas CSV (predeterminado: campo vacío)",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="permite reemplazar una salida existente"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="falla si encuentra una incidencia recuperable",
    )
    parser.add_argument(
        "--report",
        metavar="REPORT_PATH",
        help="escribe un reporte de calidad JSON para todos los tipos procesados",
    )
    parser.add_argument(
        "--wide-output",
        metavar="OUTPUT_PATH",
        help="publica la vista ancha derivada de características (sólo transformación)",
    )
    if enable_feature_rules:
        parser.add_argument(
            "--feature-rules",
            metavar="PATH",
            help="JSON versionado de equivalencias para la vista ancha de características",
        )
        parser.add_argument(
            "--feature-rules-report",
            metavar="PATH",
            help="escribe cobertura, conflictos y fallback de las reglas en JSON",
        )
        parser.add_argument(
            "--feature-values-output",
            metavar="PATH",
            help="publica valores largos tipados de características antes de la vista ancha",
        )
        parser.add_argument(
            "--run-id",
            metavar="ID",
            help="identificador de ejecución incluido en --feature-values-output",
        )
        parser.add_argument(
            "--strict-feature-rules",
            action="store_true",
            help="convierte diagnósticos recuperables de las reglas en errores",
        )
    return parser


def _custom_filename(args: argparse.Namespace, dataset_type: DatasetType) -> str | None:
    return getattr(args, f"{dataset_type.value}_filename")


def _directory_target(
    output_dir: str | Path,
    dataset_type: DatasetType,
    *,
    custom_name: str | None,
    output_format: str | None,
) -> Path:
    name = custom_name or DEFAULT_FILENAMES[dataset_type]
    candidate = Path(name)
    if not name or candidate.is_absolute() or candidate.name != name or name in {".", ".."}:
        raise ValueError(
            f"El nombre para {dataset_type.value} debe ser sólo un nombre de archivo: {name}"
        )
    if candidate.suffix:
        suffix = candidate.suffix.casefold().lstrip(".")
        if suffix not in {"csv", "json"}:
            raise ValueError(f"Extensión no soportada para {name}; usa .csv o .json")
        inferred = suffix
        if output_format is not None and inferred != output_format:
            raise ValueError(f"La extensión de {name} no coincide con --format {output_format}")
    else:
        candidate = candidate.with_suffix(f".{output_format or 'csv'}")
    return Path(output_dir) / candidate


def _all_directory_targets(args: argparse.Namespace) -> dict[DatasetType, Path]:
    if args.output_dir is None:
        return {}
    return {
        dataset_type: _directory_target(
            args.output_dir,
            dataset_type,
            custom_name=_custom_filename(args, dataset_type),
            output_format=args.format,
        )
        for dataset_type in DatasetType
    }


def _validate_output_options(args: argparse.Namespace) -> dict[DatasetType, Path]:
    custom_names = [_custom_filename(args, dataset_type) for dataset_type in DatasetType]
    if args.output and args.output_dir:
        raise ValueError("Usa --output o --output-dir, no ambos")
    if any(custom_names) and args.output_dir is None:
        raise ValueError("Los nombres por tipo requieren --output-dir")
    if args.output is None and args.output_dir is None:
        raise ValueError("Debes indicar --output o --output-dir")
    if args.output_dir is not None and Path(args.output_dir).is_file():
        raise DatasetIOError(f"La ruta de salida es un archivo, no una carpeta: {args.output_dir}")
    return _all_directory_targets(args)


def _load_groups(
    files: Sequence[Path],
    *,
    requested_type: DatasetType | None,
    batch_mode: bool,
) -> tuple[dict[DatasetType, list[pd.DataFrame]], list[str], int]:
    groups = {dataset_type: [] for dataset_type in DatasetType}
    warnings: list[str] = []
    selected_files = 0
    for source in files:
        try:
            frame = read_dataset(source)
            if batch_mode or requested_type is None:
                detected_type = detect_dataset_type(source, frame.columns)
            else:
                detected_type = requested_type
        except (DatasetDetectionError, DatasetIOError) as exc:
            if not batch_mode:
                raise
            warnings.append(f"{source}: {exc}")
            continue
        if requested_type is not None and detected_type != requested_type:
            continue
        groups[detected_type].append(frame)
        selected_files += 1
    return groups, warnings, selected_files


def _preflight_outputs(
    targets: dict[Any, Path],
    *,
    inputs: Sequence[Path],
    overwrite: bool,
) -> None:
    resolved_inputs = {path.resolve() for path in inputs}
    resolved_targets: set[Path] = set()
    for target in targets.values():
        resolved = target.resolve()
        if resolved in resolved_inputs:
            raise DatasetIOError(f"La salida no puede sobrescribir una entrada: {target}")
        if resolved in resolved_targets:
            raise DatasetIOError(f"Dos tipos usan la misma ruta de salida: {target}")
        if target.exists() and not overwrite:
            raise DatasetIOError(f"El archivo ya existe (usa --overwrite): {target}")
        resolved_targets.add(resolved)


def _extra_targets(args: argparse.Namespace) -> tuple[Path, ...]:
    values = (
        args.report,
        args.wide_output,
        getattr(args, "feature_rules_report", None),
        getattr(args, "feature_values_output", None),
    )
    return tuple(Path(value) for value in values if value)


def run_pipeline_cli(
    argv: Sequence[str] | None,
    *,
    prog: str,
    description: str,
    stage: str,
    operation: Callable[..., PipelineResult],
    feature_rules_loader: Callable[[str | Path], Any] | None = None,
) -> int:
    parser = build_parser(
        prog,
        description,
        stage,
        enable_feature_rules=feature_rules_loader is not None,
    )
    args = parser.parse_args(argv)
    try:
        if any(character in args.csv_null_value for character in ("\r", "\n", "\0")):
            raise ValueError("--csv-null-value no admite saltos de línea ni bytes nulos")
        feature_rules = None
        if feature_rules_loader is not None:
            if (args.feature_rules_report or args.strict_feature_rules) and not args.feature_rules:
                raise ValueError(
                    "--feature-rules-report y --strict-feature-rules requieren --feature-rules"
                )
            if args.feature_rules:
                feature_rules = feature_rules_loader(args.feature_rules)
            if args.feature_values_output and not args.feature_rules:
                raise ValueError("--feature-values-output requiere --feature-rules")
            if args.feature_values_output and not args.run_id:
                raise ValueError("--feature-values-output requiere --run-id")
        directory_targets = _validate_output_options(args)
        files = discover_input_files(args.input)
        batch_mode = len(args.input) > 1 or any(Path(path).is_dir() for path in args.input)
        requested_type = None if args.type == "auto" else DatasetType(args.type)
        if batch_mode and requested_type is None and args.output is not None:
            raise ValueError("El modo lote sin --type requiere --output-dir")
        groups, input_warnings, selected_files = _load_groups(
            files,
            requested_type=requested_type,
            batch_mode=batch_mode,
        )
        if args.strict and input_warnings:
            raise PipelineValidationError(input_warnings[0])
        selected = {dataset_type: frames for dataset_type, frames in groups.items() if frames}
        if not selected:
            suffix = f" del tipo {requested_type.value}" if requested_type is not None else ""
            raise DatasetDetectionError(f"No se encontraron entradas deducibles{suffix}")
        if args.output is not None:
            if len(selected) != 1:
                raise ValueError("--output sólo puede recibir un tipo; usa --output-dir")
            only_type = next(iter(selected))
            targets = {only_type: Path(args.output)}
        else:
            targets = {dataset_type: directory_targets[dataset_type] for dataset_type in selected}
        protected_inputs: tuple[Path, ...] = tuple(files)
        if feature_rules is not None:
            protected_inputs = (*protected_inputs, Path(args.feature_rules))
        _preflight_outputs(targets, inputs=protected_inputs, overwrite=args.overwrite)
        auxiliary_targets = _extra_targets(args)
        if len({path.resolve() for path in auxiliary_targets}) != len(auxiliary_targets):
            raise DatasetIOError("El reporte y la vista ancha no pueden usar la misma ruta")
        _preflight_outputs(
            {index: target for index, target in enumerate(auxiliary_targets)},
            inputs=(*protected_inputs, *targets.values()),
            overwrite=args.overwrite,
        )

        pending_results: list[tuple[PipelineResult, Path, int]] = []
        for dataset_type, frames in selected.items():
            # Object dtype preserves heterogeneous raw scalars and avoids pandas choosing
            # a dtype from an all-null fragment differently across versions.
            frame = pd.concat(
                [fragment.astype(object) for fragment in frames],
                ignore_index=True,
                sort=False,
            )
            operation_options: dict[str, Any] = {"strict": args.strict}
            if feature_rules is not None and dataset_type == DatasetType.FEATURE:
                operation_options.update(
                    feature_rules=feature_rules,
                    strict_feature_rules=args.strict_feature_rules,
                    run_id=args.run_id,
                )
            result = operation(frame, dataset_type, **operation_options)
            pending_results.append((result, targets[dataset_type], len(frames)))

        feature_results = [
            result for result, _, _ in pending_results if result.dataset_type == DatasetType.FEATURE
        ]
        if args.wide_output and (
            len(feature_results) != 1 or getattr(feature_results[0], "wide_data", None) is None
        ):
            raise ValueError("--wide-output requiere una transformación de características")
        if feature_rules is not None and (
            len(feature_results) != 1
            or getattr(feature_results[0], "feature_rules_report", None) is None
        ):
            raise ValueError("--feature-rules requiere procesar exactamente un grupo feature")

        results: list[tuple[PipelineResult, Path, int]] = []
        for result, target, file_count in pending_results:
            output = write_dataset(
                result.data,
                target,
                output_format=args.format,
                overwrite=args.overwrite,
                csv_null_value=args.csv_null_value,
            )
            results.append((result, output, file_count))
        if args.wide_output:
            write_dataset(
                feature_results[0].wide_data,
                args.wide_output,
                output_format=args.format,
                overwrite=args.overwrite,
                csv_null_value=args.csv_null_value,
            )
        if feature_rules is not None and args.feature_values_output:
            write_dataset(
                feature_results[0].feature_values,
                args.feature_values_output,
                output_format=args.format,
                overwrite=args.overwrite,
                csv_null_value=args.csv_null_value,
            )
        if args.report:
            write_json_report(
                [result.report.as_dict() for result, _, _ in results],
                args.report,
                overwrite=args.overwrite,
            )
        if feature_rules is not None and args.feature_rules_report:
            write_json_report(
                feature_results[0].feature_rules_report.as_dict(),
                args.feature_rules_report,
                overwrite=args.overwrite,
            )
    except (DatasetDetectionError, PipelineValidationError, ValueError) as exc:
        diagnostic = getattr(exc, "feature_rules_report", None)
        diagnostic_path = getattr(args, "feature_rules_report", None)
        if diagnostic is not None and diagnostic_path:
            try:
                write_json_report(
                    diagnostic.as_dict(),
                    diagnostic_path,
                    overwrite=args.overwrite,
                )
            except DatasetIOError as report_exc:
                print(f"Error de archivo: {report_exc}", file=sys.stderr)
                return EXIT_OUTPUT
        print(f"Datos inválidos: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except DatasetIOError as exc:
        print(f"Error de archivo: {exc}", file=sys.stderr)
        return EXIT_OUTPUT
    for warning in input_warnings:
        print(f"ADVERTENCIA entrada omitida: {warning}", file=sys.stderr)
    issue_count = 0
    for result, output, file_count in results:
        for issue in result.issues:
            print(f"ADVERTENCIA {issue.format()}", file=sys.stderr)
        issue_count += len(result.issues)
        print(
            f"Resumen: tipo={result.dataset_type.value} archivos={file_count} "
            f"filas_entrada={result.input_rows} filas_salida={result.output_rows} "
            f"advertencias={len(result.issues)} salida={output}",
            file=sys.stderr,
        )
        feature_report = getattr(result, "feature_rules_report", None)
        if feature_report is not None:
            diagnostics = (
                len(feature_report.invalid_captures)
                + len(feature_report.multiple_matches)
                + sum(feature_report.unknown_competitors.values())
            )
            issue_count += diagnostics
            print(
                f"Reglas feature: cargadas={len(feature_report.loaded_rules)} "
                f"usadas={len(feature_report.used_rules)} "
                f"coincidencias={sum(feature_report.match_counts.values())} "
                f"fallback={feature_report.fallback_rows} diagnósticos={diagnostics}",
                file=sys.stderr,
            )
    if batch_mode:
        print(
            f"Resumen lote: descubiertos={len(files)} procesados={selected_files} "
            f"tipos={len(results)} omitidos={len(files) - selected_files}",
            file=sys.stderr,
        )
    return EXIT_WARNINGS if input_warnings or issue_count else 0
