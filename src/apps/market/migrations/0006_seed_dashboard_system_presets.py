from django.db import migrations


def seed_system_presets(apps, schema_editor):
    DashboardPreset = apps.get_model("market", "DashboardPreset")
    DashboardSettings = apps.get_model("market", "DashboardSettings")
    all_preset, _ = DashboardPreset.objects.update_or_create(
        slug="all",
        defaults={
            "name": "Todos",
            "description": "Todos los proveedores y planes reales vigentes.",
            "data_scope": "real",
            "plan_selection": "all_current",
            "is_active": True,
            "is_system": True,
        },
    )
    DashboardPreset.objects.update_or_create(
        slug="demo",
        defaults={
            "name": "DEMO",
            "description": "Escenario sintético aislado para demostrar el dashboard.",
            "data_scope": "demo",
            "plan_selection": "all_current",
            "is_active": True,
            "is_system": True,
        },
    )
    DashboardSettings.objects.get_or_create(
        pk=1,
        defaults={
            "header_title": "Dashboard de inteligencia competitiva",
            "default_preset": all_preset,
        },
    )


class Migration(migrations.Migration):
    dependencies = [("market", "0005_dashboard_configuration")]

    operations = [migrations.RunPython(seed_system_presets, migrations.RunPython.noop)]
