from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("", views.review_list, name="list"),
    path("runs/", views.legacy_ingestion_unavailable, name="runs"),
    path("runs/<int:run_id>/", views.legacy_ingestion_unavailable, name="run_detail"),
    path("summary/", views.review_summary, name="summary"),
    path("summary/<slug:provider_code>/", views.review_summary, name="provider_summary"),
    path("<int:review_id>/", views.review_detail, name="detail"),
    path("sources/", views.legacy_ingestion_unavailable, name="sources"),
    path("sources/new/", views.legacy_ingestion_unavailable, name="source_create"),
    path(
        "sources/<int:source_id>/edit/",
        views.legacy_ingestion_unavailable,
        name="source_edit",
    ),
    path("sources/run/", views.legacy_ingestion_unavailable, name="request_all"),
    path(
        "sources/<int:source_id>/run/",
        views.legacy_ingestion_unavailable,
        name="request_source",
    ),
    path(
        "providers/<int:provider_id>/run/",
        views.legacy_ingestion_unavailable,
        name="request_provider",
    ),
    path("enrich/", views.legacy_ingestion_unavailable, name="enrich"),
    path("export.csv", views.export_reviews, {"format_name": "csv"}, name="export_csv"),
    path("export.json", views.export_reviews, {"format_name": "json"}, name="export_json"),
]
