from django.urls import path

from . import actions, presentation

urlpatterns = [
    path(
        "sources/<int:source_id>/toggle/",
        presentation.legacy_ingestion_unavailable,
        name="toggle_source",
    ),
    path("settings/test-email/", actions.test_email_configuration, name="test_email_configuration"),
    path("", presentation.dashboard, name="dashboard"),
    path(
        "dashboard/branding/image/",
        presentation.dashboard_brand_image,
        name="dashboard_brand_image",
    ),
    path(
        "application/branding/<slug:asset>/",
        presentation.application_brand_asset,
        name="application_brand_asset",
    ),
    path(
        "application/settings/",
        presentation.application_settings,
        name="application_settings",
    ),
    path(
        "dashboard/settings/",
        presentation.application_settings,
        name="dashboard_settings",
    ),
    path(
        "dashboard/presets/save/", presentation.dashboard_preset_save, name="dashboard_preset_save"
    ),
    path(
        "dashboard/presets/<int:preset_id>/delete/",
        presentation.dashboard_preset_delete,
        name="dashboard_preset_delete",
    ),
    path("comparison/", presentation.comparison, name="comparison"),
    path("plans/<int:plan_id>/history/", presentation.plan_history, name="plan_history"),
    path("sources/", presentation.legacy_ingestion_unavailable, name="sources"),
    path("pipeline-runs/", presentation.pipeline_runs, name="pipeline_runs"),
    path(
        "pipeline-runs/request/",
        presentation.request_pipeline_run,
        name="request_pipeline_run",
    ),
    path(
        "sources/run/", presentation.legacy_ingestion_unavailable, name="request_scrape_all"
    ),
    path(
        "sources/<int:source_id>/run/",
        presentation.legacy_ingestion_unavailable,
        name="request_scrape",
    ),
    path("runs/", presentation.legacy_ingestion_unavailable, name="runs"),
    path(
        "runs/<int:run_id>/", presentation.legacy_ingestion_unavailable, name="run_detail"
    ),
    path("settings/", presentation.functional_settings, name="functional_settings"),
]
