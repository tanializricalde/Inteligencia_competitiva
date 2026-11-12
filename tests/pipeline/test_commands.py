import json
from pathlib import Path

import pytest
from django.core.management import call_command

from apps.market.models import Provider
from apps.pipeline.models import (
    MarketSource,
    PipelineConfigVersion,
    PipelineProfile,
    PipelineRun,
    PlanFeatureSource,
    PlanFeatureValue,
    PlanSnapshot,
    ReviewSnapshot,
    ScheduledJob,
)
from apps.reviews.models import ReviewSource
from apps.scraping.models import ScrapeSource

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.django_db
def test_config_commands_import_draft_publish_and_export(tmp_path, capsys):
    source = ROOT / "feature_rules/feature-equivalence.example.json"
    output = tmp_path / "exported.json"

    call_command(
        "validate_pipeline_config",
        str(source),
        "--stage",
        "feature_equivalence",
    )
    call_command(
        "import_pipeline_config",
        str(source),
        "--code",
        "feature-rules",
        "--stage",
        "feature_equivalence",
        "--config-version",
        "1",
    )
    item = PipelineConfigVersion.objects.get()
    assert item.status == PipelineConfigVersion.Status.DRAFT

    call_command(
        "publish_pipeline_config",
        "--code",
        "feature-rules",
        "--config-version",
        "1",
    )
    call_command(
        "export_pipeline_config",
        "--code",
        "feature-rules",
        "--config-version",
        "1",
        "--output",
        str(output),
    )

    item.refresh_from_db()
    assert item.status == PipelineConfigVersion.Status.PUBLISHED
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 1
    assert "Publicada" in capsys.readouterr().out


@pytest.mark.django_db
def test_seed_market_pipeline_is_idempotent():
    legacy_counts = (ScrapeSource.objects.count(), ReviewSource.objects.count())
    call_command("seed_market_pipeline")
    counts = (
        PipelineConfigVersion.objects.count(),
        PipelineProfile.objects.count(),
        MarketSource.objects.count(),
        ScheduledJob.objects.count(),
    )

    call_command("seed_market_pipeline")

    assert counts == (
        PipelineConfigVersion.objects.count(),
        PipelineProfile.objects.count(),
        MarketSource.objects.count(),
        ScheduledJob.objects.count(),
    )
    assert PipelineConfigVersion.objects.filter(status="published").count() == 4
    assert PipelineProfile.objects.get(code="nightly-market").active_version is not None
    assert Provider.objects.filter(code="idrixcontable", is_active=True).exists()
    real_codes = {"idrixcontable", "siigo_ec", "anfibius", "perseo"}
    assert (
        set(
            Provider.objects.filter(code__in=real_codes, is_active=True).values_list(
                "code", flat=True
            )
        )
        == real_codes
    )
    assert not MarketSource.objects.filter(provider__code__in=real_codes, is_active=False).exists()
    assert not MarketSource.objects.filter(provider__code="competidor_demo").exists()
    assert legacy_counts == (ScrapeSource.objects.count(), ReviewSource.objects.count())


@pytest.mark.django_db
def test_seed_versions_changed_configuration_without_rewriting_published(tmp_path):
    call_command("seed_market_pipeline")
    original = (ROOT / "config.example.toml").read_text(encoding="utf-8")
    changed = tmp_path / "config.toml"
    changed.write_text(original.replace("timeout_seconds = 20", "timeout_seconds = 21", 1))

    call_command("seed_market_pipeline", "--config", changed)

    extraction = PipelineConfigVersion.objects.filter(
        pipeline_config__code="extraction-default"
    ).order_by("version")
    assert list(extraction.values_list("version", flat=True)) == [1, 2]
    profile = PipelineProfile.objects.get(code="nightly-market")
    assert profile.active_version.version == 2
    assert extraction.get(version=1).content_json["defaults"]["timeout_seconds"] == 20


@pytest.mark.django_db
def test_run_market_pipeline_dry_run_has_no_business_writes(capsys):
    call_command("seed_market_pipeline")
    initial_run_ids = set(PipelineRun.objects.values_list("id", flat=True))

    call_command("run_market_pipeline", "--profile", "nightly-market", "--dry-run")

    output = capsys.readouterr().out
    assert output.index("plans:idrixcontable") < output.index("features:idrixcontable")
    assert output.index("features:idrixcontable") < output.index("reviews:idrixcontable")
    assert PipelineProfile.objects.get(code="nightly-market").versions.count() == 1
    assert set(PipelineRun.objects.values_list("id", flat=True)) == initial_run_ids


@pytest.mark.django_db
def test_import_normalized_dataset_command_publishes_real_sample():
    call_command("seed_market_pipeline")
    initial_run_ids = set(PipelineRun.objects.values_list("id", flat=True))

    call_command(
        "import_normalized_dataset",
        str(ROOT / "data/normalized"),
        "--profile",
        "nightly-market",
        "--publish",
    )

    real_runs = PipelineRun.objects.filter(
        provider_runs__provider__data_scope=Provider.DataScope.REAL,
    ).distinct()
    imported = real_runs.exclude(id__in=initial_run_ids).get()
    assert imported.status == PipelineRun.Status.PUBLISHED
    assert PlanSnapshot.objects.filter(provider_run__pipeline_run=imported).count() == 27
    assert (
        PlanFeatureSource.objects.filter(plan_snapshot__provider_run__pipeline_run=imported).count()
        == 367
    )
    assert (
        PlanFeatureValue.objects.filter(plan_snapshot__provider_run__pipeline_run=imported).count()
        == 1674
    )
    assert ReviewSnapshot.objects.filter(provider_run__pipeline_run=imported).count() == 402
