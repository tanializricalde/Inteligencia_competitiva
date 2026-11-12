"""Argparse entry point for the standalone scraper CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from time import monotonic

from scraper_cli.config import (
    ConfigError,
    load_config,
    resolve_output_directory,
    resolve_output_file,
)
from scraper_cli.exporters import OutputError, export_rows
from scraper_cli.runner import RunResult, run_plans, run_reviews
from scraper_cli.schemas import PLAN_FEATURE_FIELDS, PLAN_FIELDS, REVIEW_FIELDS
from scraping_core.registry import PLAN_ADAPTERS, REVIEW_ADAPTERS

EXIT_UNEXPECTED = 1
EXIT_CONFIG = 2
EXIT_TOTAL_FAILURE = 3
EXIT_PARTIAL = 4
EXIT_OUTPUT = 5


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("debe ser mayor que cero")
    return number


def _selection_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config", required=True, metavar="PATH", help="ruta del archivo TOML de configuración"
    )
    parser.add_argument(
        "--provider",
        action="append",
        metavar="CODE",
        help="selecciona un código de proveedor; puede repetirse",
    )
    parser.add_argument(
        "--source",
        action="append",
        metavar="NAME",
        help="selecciona el nombre exacto de una fuente activa; puede repetirse",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "json"),
        default="csv",
        help="formato de salida (predeterminado: csv)",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        metavar="N",
        help="máximo de registros por fuente; sustituye defaults.max_items",
    )
    parser.add_argument(
        "--timeout",
        type=positive_int,
        metavar="SECONDS",
        help="timeout por solicitud o navegación; sustituye el valor TOML",
    )
    parser.add_argument(
        "--pretty", action="store_true", help="indenta JSON; no altera la salida CSV"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="muestra contadores adicionales en stderr",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="detiene la ejecución después del primer fallo de fuente",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="permite reemplazar archivos de salida existentes",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scraper_cli",
        description="Ejecuta scrapers y exporta contratos canónicos sin Django ni base de datos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Ejemplos:
  python -m scraper_cli list-adapters
  python -m scraper_cli validate-config --config config.toml
  python -m scraper_cli plans --help
  python -m scraper_cli reviews --config config.toml --output reviews.csv

Referencia completa: docs/cli/CLI_USAGE.md""",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, title="subcomandos")
    subparsers.add_parser(
        "list-adapters",
        help="lista las claves de adapters disponibles",
        description="Lista por tipo las claves que pueden usarse como adapter_key en el TOML.",
    )
    validate = subparsers.add_parser(
        "validate-config",
        help="valida el TOML sin ejecutar fuentes",
        description="Valida el TOML completo sin ejecutar fuentes.",
        epilog="Ejemplo:\n  python -m scraper_cli validate-config --config config.toml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    validate.add_argument("--config", required=True, metavar="PATH", help="ruta del archivo TOML")

    plans = subparsers.add_parser(
        "plans",
        help="extrae planes y características",
        description="Ejecuta fuentes activas y exporta planes y características por separado.",
        epilog="""Ejemplos:
  python -m scraper_cli plans --config config.toml --output plans.csv
  python -m scraper_cli plans --config config.toml --format json --pretty --output plans.json
  python -m scraper_cli plans --config config.toml --output - --features-output features.csv""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _selection_options(plans)
    plans.add_argument(
        "--output",
        metavar="PATH|-",
        help=(
            "archivo de planes o '-' para stdout; si se omite usa output.directory y "
            "providers.plans_filename de un único proveedor"
        ),
    )
    plans.add_argument(
        "--features-output",
        metavar="PATH",
        help="archivo de características; si se omite se deriva de la salida de planes resuelta",
    )

    reviews = subparsers.add_parser(
        "reviews",
        help="extrae reseñas",
        description="Ejecuta fuentes activas, pagina hasta los límites y exporta reviews_v1.",
        epilog="""Ejemplos:
  python -m scraper_cli reviews --config config.toml --output reviews.csv
  python -m scraper_cli reviews --config config.toml --format json --output reviews.json""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _selection_options(reviews)
    reviews.add_argument(
        "--country",
        metavar="ISO2",
        help="país ISO-2 de la ejecución; prevalece sobre fuente y defaults",
    )
    reviews.add_argument(
        "--output",
        metavar="PATH|-",
        help=(
            "archivo de reseñas o '-' para stdout; si se omite usa output.directory y "
            "providers.reviews_filename de un único proveedor"
        ),
    )

    all_parser = subparsers.add_parser(
        "all",
        help="extrae planes, características y reseñas",
        description="Ejecuta planes y reseñas, y crea tres archivos en un directorio.",
        epilog="""Ejemplos:
  python -m scraper_cli all --config config.toml --output-dir output
  python -m scraper_cli all --config config.toml --provider anfibius --output-dir output""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _selection_options(all_parser)
    all_parser.add_argument(
        "--country",
        metavar="ISO2",
        help="país ISO-2 para reseñas; prevalece sobre fuente y defaults",
    )
    all_parser.add_argument(
        "--output-dir",
        metavar="DIR",
        help=(
            "directorio para plans, plan_features y reviews; si se omite usa output.directory"
        ),
    )
    return parser


def _features_path(output: str, output_format: str) -> str:
    path = Path(output)
    suffix = path.suffix or f".{output_format}"
    return str(path.with_name(f"{path.stem}_features{suffix}"))


def _format_duration(seconds: float) -> str:
    total = max(0.0, seconds)
    hours, remainder = divmod(total, 3_600)
    minutes, seconds = divmod(remainder, 60)
    if hours >= 1:
        return f"{int(hours)}h {int(minutes):02d}m {seconds:05.2f}s"
    if minutes >= 1:
        return f"{int(minutes)}m {seconds:05.2f}s"
    return f"{seconds:.2f}s"


def _report(
    result: RunResult,
    outputs: list[str],
    *,
    verbose: bool,
    elapsed_seconds: float,
) -> None:
    for warning in result.warnings:
        print(f"ADVERTENCIA {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"ERROR {error}", file=sys.stderr)
    print(
        f"Resumen: intentadas={result.attempted} exitosas={result.succeeded} "
        f"fallidas={result.failed} registros={len(result.rows)} "
        f"salidas={','.join(outputs)} duración={_format_duration(elapsed_seconds)} "
        f"código={result.exit_code}",
        file=sys.stderr,
    )
    if verbose and result.feature_rows:
        print(f"Características exportadas: {len(result.feature_rows)}", file=sys.stderr)


def _common(args) -> dict:
    return {
        "provider_codes": args.provider,
        "source_names": args.source,
        "limit": args.limit,
        "timeout": args.timeout,
        "fail_fast": args.fail_fast,
    }


def _export(result, fields, output, args) -> None:
    export_rows(
        result,
        fields,
        output_format=args.format,
        output=output,
        pretty=args.pretty,
        overwrite=args.overwrite,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "list-adapters":
        print("Planes:")
        for key in sorted(PLAN_ADAPTERS):
            print(f"  {key}")
        print("Reseñas:")
        for key in sorted(REVIEW_ADAPTERS):
            print(f"  {key}")
        return 0
    started_at = monotonic()
    try:
        config = load_config(args.config)
        if args.command == "validate-config":
            print(f"Configuración válida: {len(config.providers)} proveedor(es)", file=sys.stderr)
            return 0
        if args.command == "plans":
            output = resolve_output_file(
                config,
                provider_codes=args.provider,
                kind="plans",
                output_format=args.format,
                cli_value=args.output,
            )
            features_output = (
                resolve_output_file(
                    config,
                    provider_codes=args.provider,
                    kind="plans",
                    output_format=args.format,
                    cli_value=args.features_output,
                )
                if args.features_output
                else None
            )
            result = run_plans(config, **_common(args))
            if output == "-" and result.feature_rows and not features_output:
                raise ConfigError(
                    "--features-output es obligatorio al enviar planes a stdout con características"
                )
            if features_output is None and output != "-":
                features_output = _features_path(output, args.format)
            _export(result.rows, PLAN_FIELDS, output, args)
            outputs = [output]
            if features_output is not None:
                _export(result.feature_rows, PLAN_FEATURE_FIELDS, features_output, args)
                outputs.append(features_output)
            _report(
                result,
                outputs,
                verbose=args.verbose,
                elapsed_seconds=monotonic() - started_at,
            )
            return result.exit_code
        if args.command == "reviews":
            output = resolve_output_file(
                config,
                provider_codes=args.provider,
                kind="reviews",
                output_format=args.format,
                cli_value=args.output,
            )
            result = run_reviews(config, country=args.country, **_common(args))
            _export(result.rows, REVIEW_FIELDS, output, args)
            _report(
                result,
                [output],
                verbose=args.verbose,
                elapsed_seconds=monotonic() - started_at,
            )
            return result.exit_code
        output_dir = resolve_output_directory(config, args.output_dir)
        extension = args.format
        plans = run_plans(config, **_common(args))
        reviews = (
            RunResult()
            if args.fail_fast and plans.errors
            else run_reviews(config, country=args.country, **_common(args))
        )
        outputs = {
            "plans": output_dir / f"plans.{extension}",
            "features": output_dir / f"plan_features.{extension}",
            "reviews": output_dir / f"reviews.{extension}",
        }
        _export(plans.rows, PLAN_FIELDS, outputs["plans"], args)
        _export(plans.feature_rows, PLAN_FEATURE_FIELDS, outputs["features"], args)
        _export(reviews.rows, REVIEW_FIELDS, outputs["reviews"], args)
        combined = RunResult(
            rows=plans.rows + reviews.rows,
            feature_rows=plans.feature_rows,
            attempted=plans.attempted + reviews.attempted,
            succeeded=plans.succeeded + reviews.succeeded,
            errors=plans.errors + reviews.errors,
            warnings=plans.warnings + reviews.warnings,
        )
        _report(
            combined,
            [str(path) for path in outputs.values()],
            verbose=args.verbose,
            elapsed_seconds=monotonic() - started_at,
        )
        return combined.exit_code
    except ConfigError as exc:
        print(f"Configuración inválida: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except OutputError as exc:
        print(f"Error de salida: {exc}", file=sys.stderr)
        return EXIT_OUTPUT
    except Exception as exc:
        print(f"Error inesperado: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_UNEXPECTED


if __name__ == "__main__":
    raise SystemExit(main())
