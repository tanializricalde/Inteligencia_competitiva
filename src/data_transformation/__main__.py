"""Command-line entry point for canonical transformations."""

from __future__ import annotations

from collections.abc import Sequence

from data_pipeline.cli import run_pipeline_cli
from data_transformation.feature_rules import load_feature_rules
from data_transformation.service import transform_dataset


def main(argv: Sequence[str] | None = None) -> int:
    return run_pipeline_cli(
        argv,
        prog="python -m data_transformation",
        description="Normaliza CSV/JSON limpios hacia los esquemas canónicos de análisis.",
        stage="normalized",
        operation=transform_dataset,
        feature_rules_loader=load_feature_rules,
    )


if __name__ == "__main__":
    raise SystemExit(main())
