#!/usr/bin/env python3
"""Build and validate the source-only standalone CLI distribution."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
PACKAGE_DIRS = (
    Path("src/scraping_core"),
    Path("src/scraper_cli"),
    Path("src/data_pipeline"),
    Path("src/data_cleaning"),
    Path("src/data_transformation"),
)
FILES = {
    Path("config.example.toml"): Path("config.example.toml"),
    Path("cli_dist/requirements.txt"): Path("requirements.txt"),
    Path("cli_dist/README.md"): Path("README.md"),
    Path("cli_dist/THIRD_PARTY_NOTICES.md"): Path("THIRD_PARTY_NOTICES.md"),
    Path("cli_dist/run.py"): Path("run.py"),
    Path("docs/cli/CLI_ARCHITECTURE.md"): Path("docs/cli/CLI_ARCHITECTURE.md"),
    Path("docs/cli/CLI_CONFIG.md"): Path("docs/cli/CLI_CONFIG.md"),
    Path("docs/cli/CLI_LEER_PRIMERO.md"): Path("docs/cli/CLI_LEER_PRIMERO.md"),
    Path("docs/cli/CLI_USAGE.md"): Path("docs/cli/CLI_USAGE.md"),
    Path("docs/cli/CLI_OUTPUT_SCHEMAS.md"): Path("docs/cli/CLI_OUTPUT_SCHEMAS.md"),
    Path("docs/cli/CLI_DISTRIBUTION.md"): Path("docs/cli/CLI_DISTRIBUTION.md"),
    Path("docs/data/DATA_PIPELINE.md"): Path("docs/data/DATA_PIPELINE.md"),
    Path("docs/data/DATA_CLEANING.md"): Path("docs/data/DATA_CLEANING.md"),
    Path("docs/data/DATA_TRANSFORMATION.md"): Path("docs/data/DATA_TRANSFORMATION.md"),
    Path("docs/data/FEATURE_EQUIVALENCE_RULES.md"): Path(
        "docs/data/FEATURE_EQUIVALENCE_RULES.md"
    ),
    Path("docs/data/FEATURE_EQUIVALENCE_ANALYSIS.md"): Path(
        "docs/data/FEATURE_EQUIVALENCE_ANALYSIS.md"
    ),
    Path("docs/development/WINDOWS_LINUX.md"): Path(
        "docs/development/WINDOWS_LINUX.md"
    ),
    Path("feature_rules/feature-equivalence.schema.json"): Path(
        "feature_rules/feature-equivalence.schema.json"
    ),
    Path("feature_rules/feature-equivalence.example.json"): Path(
        "feature_rules/feature-equivalence.example.json"
    ),
}
FORBIDDEN_IMPORT_ROOTS = {"django", "apps", "config"}
FORBIDDEN_PARTS = {"models", "migrations", "repositories"}


class BuildError(RuntimeError):
    pass


def _safe_output(raw: str) -> Path:
    if not raw.strip():
        raise BuildError("El destino no puede estar vacío")
    output = Path(raw).expanduser().resolve()
    dangerous = {Path("/").resolve(), Path.home().resolve(), REPOSITORY.resolve()}
    if output in dangerous:
        raise BuildError(f"Destino peligroso rechazado: {output}")
    return output


def _copy_tree(source: Path, destination: Path) -> None:
    for item in sorted(source.rglob("*")):
        if item.is_symlink():
            raise BuildError(f"No se permiten symlinks en la allowlist: {item}")
        if item.is_dir() or item.suffix != ".py":
            continue
        relative = item.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def _copy_allowlist(stage: Path) -> None:
    for relative in PACKAGE_DIRS:
        source = REPOSITORY / relative
        _copy_tree(source, stage / source.name)
    for source_relative, target_relative in FILES.items():
        source = REPOSITORY / source_relative
        if not source.is_file() or source.is_symlink():
            raise BuildError(f"Falta archivo permitido o es symlink: {source_relative}")
        target = stage / target_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _validate_python(stage: Path) -> None:
    available = {
        "scraping_core",
        "scraper_cli",
        "data_pipeline",
        "data_cleaning",
        "data_transformation",
    }
    for path in sorted(stage.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        compile(tree, str(path), "exec")
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                parts = set(name.split("."))
                root = name.split(".", 1)[0]
                if root in FORBIDDEN_IMPORT_ROOTS or parts & FORBIDDEN_PARTS:
                    raise BuildError(f"Import prohibido en {path.relative_to(stage)}: {name}")
                if root in available and not (stage / root).is_dir():
                    raise BuildError(f"Paquete interno ausente para import {name}")


def _run(stage: Path, *arguments: str, module: str = "scraper_cli") -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["DATABASE_URL"] = "postgresql://invalid:invalid@127.0.0.1:1/invalid"
    completed = subprocess.run(
        [sys.executable, "-m", module, *arguments],
        cwd=stage,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise BuildError(
            f"Falló ejecución aislada ({' '.join(arguments)}): "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )


def _validate_runtime(stage: Path, scratch: Path) -> None:
    _run(stage, "--help")
    _run(stage, "list-adapters")
    _run(stage, "validate-config", "--config", "config.example.toml")
    _run(
        stage,
        "all",
        "--config",
        "config.example.toml",
        "--provider",
        "competidor_demo",
        "--format",
        "json",
        "--output-dir",
        str(scratch / "fixture-output"),
    )
    raw_reviews = scratch / "fixture-output" / "reviews.json"
    raw_features = scratch / "fixture-feature.json"
    raw_features.write_text(
        json.dumps(
            [
                {
                    "plan_id": "fixture-plan",
                    "competidor_id": "perseo",
                    "nombre_modulo": "Usuarios: 2",
                    "incluido": True,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    clean_reviews = scratch / "clean" / "reviews.json"
    normalized_reviews = scratch / "normalized" / "reviews.json"
    _run(stage, "--help", module="data_cleaning")
    _run(
        stage,
        str(raw_reviews),
        "--type",
        "review",
        "--output",
        str(clean_reviews),
        module="data_cleaning",
    )
    _run(
        stage,
        str(clean_reviews),
        "--type",
        "review",
        "--output",
        str(normalized_reviews),
        module="data_transformation",
    )
    _run(
        stage,
        str(raw_features),
        "--type",
        "feature",
        "--output",
        str(scratch / "normalized" / "features.json"),
        "--wide-output",
        str(scratch / "normalized" / "features-wide.json"),
        "--feature-rules",
        "feature_rules/feature-equivalence.example.json",
        "--feature-rules-report",
        str(scratch / "normalized" / "feature-rules-report.json"),
        module="data_transformation",
    )


def _manifest(stage: Path) -> None:
    records = []
    for path in sorted(stage.rglob("*")):
        if not path.is_file() or path.name == "MANIFEST.json":
            continue
        content = path.read_bytes()
        records.append(
            {
                "path": path.relative_to(stage).as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        )
    payload = {"schema": 1, "files": records}
    (stage / "MANIFEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build(output: Path, *, overwrite: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        raise BuildError(f"El destino ya existe (usa --overwrite): {output}")
    with tempfile.TemporaryDirectory(prefix="scraper-cli-build-", dir=output.parent) as temporary:
        temporary_root = Path(temporary)
        stage = temporary_root / "stage"
        stage.mkdir()
        _copy_allowlist(stage)
        _validate_python(stage)
        _validate_runtime(stage, temporary_root)
        _manifest(stage)
        backup = temporary_root / "previous"
        if output.exists():
            os.replace(output, backup)
        try:
            os.replace(stage, output)
        except Exception:
            if backup.exists() and not output.exists():
                os.replace(backup, output)
            raise
        if backup.exists():
            shutil.rmtree(backup)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        build(_safe_output(args.output), overwrite=args.overwrite)
    except (BuildError, OSError) as exc:
        print(f"Error de distribución: {exc}", file=sys.stderr)
        return 1
    print(f"Distribución creada: {Path(args.output).expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
