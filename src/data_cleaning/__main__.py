"""Command-line entry point for data cleaning."""

from __future__ import annotations

from collections.abc import Sequence

from data_cleaning.service import clean_dataset
from data_pipeline.cli import run_pipeline_cli


def main(argv: Sequence[str] | None = None) -> int:
    return run_pipeline_cli(
        argv,
        prog="python -m data_cleaning",
        description="Limpia CSV/JSON de scraping sin cambiar su significado ni esquema.",
        stage="clean",
        operation=clean_dataset,
    )


if __name__ == "__main__":
    raise SystemExit(main())
