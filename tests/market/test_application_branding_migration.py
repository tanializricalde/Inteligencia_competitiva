import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_application_branding_migration_preserves_existing_dashboard_values():
    previous_target = [
        ("market", "0007_seed_dashboard_demo_data"),
        ("pipeline", "0002_alter_marketreview_options_and_more"),
    ]
    current_target = [
        ("market", "0009_dashboard_preset_features"),
        ("pipeline", "0003_seed_anfibius_recovery_snapshot"),
    ]
    executor = MigrationExecutor(connection)
    executor.migrate(previous_target)
    previous_apps = executor.loader.project_state(previous_target).apps
    PreviousSettings = previous_apps.get_model("market", "DashboardSettings")
    PreviousSettings.objects.update_or_create(
        pk=1,
        defaults={
            "header_title": "Encabezado existente",
            "header_image": "dashboard/branding/existing.svg",
            "header_image_alt": "Logo existente",
        },
    )

    executor = MigrationExecutor(connection)
    executor.migrate(current_target)
    current_apps = executor.loader.project_state(current_target).apps
    CurrentSettings = current_apps.get_model("market", "DashboardSettings")
    migrated = CurrentSettings.objects.get(pk=1)

    assert migrated.application_name == "Market Watch"
    assert migrated.header_title == "Encabezado existente"
    assert migrated.header_image.name == "dashboard/branding/existing.svg"
    assert migrated.header_image_alt == "Logo existente"
