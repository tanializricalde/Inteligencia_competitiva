import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("market", "0008_application_branding"),
        ("pipeline", "0003_seed_anfibius_recovery_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="dashboardpreset",
            name="feature_selection",
            field=models.CharField(
                choices=[
                    ("all_current", "Todas las características disponibles"),
                    ("explicit", "Selección explícita"),
                ],
                default="all_current",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="DashboardPresetFeature",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("position", models.PositiveIntegerField(default=0)),
                (
                    "feature_definition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="pipeline.featuredefinition",
                    ),
                ),
                (
                    "preset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="market.dashboardpreset",
                    ),
                ),
            ],
            options={"ordering": ("position", "id")},
        ),
        migrations.AddField(
            model_name="dashboardpreset",
            name="features",
            field=models.ManyToManyField(
                related_name="dashboard_presets",
                through="market.DashboardPresetFeature",
                to="pipeline.featuredefinition",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="dashboardpreset",
            name="dashboard_system_preset_shape",
        ),
        migrations.AddConstraint(
            model_name="dashboardpreset",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("is_system", False))
                    | models.Q(
                        ("feature_selection", "all_current"),
                        ("plan_selection", "all_current"),
                        ("slug__in", ("all", "demo")),
                    )
                ),
                name="dashboard_system_preset_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="dashboardpresetfeature",
            constraint=models.UniqueConstraint(
                fields=("preset", "feature_definition"),
                name="uq_dashboard_preset_feature",
            ),
        ),
        migrations.AddConstraint(
            model_name="dashboardpresetfeature",
            constraint=models.UniqueConstraint(
                fields=("preset", "position"),
                name="uq_dashboard_feature_position",
            ),
        ),
    ]
