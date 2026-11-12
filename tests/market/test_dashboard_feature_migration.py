import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_feature_selection_migration_preserves_presets_and_defaults_to_dynamic_all():
    previous_target = [
        ("market", "0008_application_branding"),
        ("pipeline", "0003_seed_anfibius_recovery_snapshot"),
    ]
    current_target = [
        ("market", "0009_dashboard_preset_features"),
        ("pipeline", "0003_seed_anfibius_recovery_snapshot"),
    ]
    executor = MigrationExecutor(connection)
    executor.migrate(previous_target)
    previous_apps = executor.loader.project_state(previous_target).apps
    PreviousPreset = previous_apps.get_model("market", "DashboardPreset")
    PreviousPreset.objects.update_or_create(
        slug="all",
        defaults={
            "name": "Todos",
            "data_scope": "real",
            "plan_selection": "all_current",
            "is_active": True,
            "is_system": True,
        },
    )
    PreviousPreset.objects.update_or_create(
        slug="demo",
        defaults={
            "name": "DEMO",
            "data_scope": "demo",
            "plan_selection": "all_current",
            "is_active": True,
            "is_system": True,
        },
    )
    PreviousPreset.objects.create(name="Vista existente", slug="existing-feature-view")

    try:
        executor = MigrationExecutor(connection)
        executor.migrate(current_target)
        current_apps = executor.loader.project_state(current_target).apps
        CurrentPreset = current_apps.get_model("market", "DashboardPreset")
        PresetFeature = current_apps.get_model("market", "DashboardPresetFeature")

        assert set(CurrentPreset.objects.values_list("slug", "feature_selection")) >= {
            ("all", "all_current"),
            ("demo", "all_current"),
            ("existing-feature-view", "all_current"),
        }
        assert not PresetFeature.objects.exists()
    finally:
        MigrationExecutor(connection).migrate(current_target)
