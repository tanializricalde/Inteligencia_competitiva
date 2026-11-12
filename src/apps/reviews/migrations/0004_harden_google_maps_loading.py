from django.db import migrations

PREVIOUS_CONFIG = {
    "page_size": 100,
    "max_scrolls": 200,
    "stable_scroll_attempts": 5,
    "scroll_pause_ms": 1200,
    "max_load_seconds": 180,
}
RESILIENT_CONFIG = {
    "page_size": 50,
    "max_scrolls": 200,
    "stable_scroll_attempts": 10,
    "scroll_pause_ms": 1500,
    "max_load_seconds": 300,
}


def harden_google_maps_loading(apps, schema_editor):
    ReviewSource = apps.get_model("reviews", "ReviewSource")
    sources = ReviewSource.objects.filter(
        adapter_key="google_maps_reviews",
        timeout_seconds=30,
        retry_limit=2,
        max_pages=10,
        max_reviews=100,
        adapter_config=PREVIOUS_CONFIG,
    )
    for source in sources:
        source.timeout_seconds = 120
        source.retry_limit = 3
        source.max_pages = 20
        source.max_reviews = 1_000
        source.adapter_config = RESILIENT_CONFIG
        source.save(
            update_fields=(
                "timeout_seconds",
                "retry_limit",
                "max_pages",
                "max_reviews",
                "adapter_config",
                "updated_at",
            )
        )


class Migration(migrations.Migration):
    dependencies = [("reviews", "0003_expand_google_maps_limits")]

    operations = [
        migrations.RunPython(harden_google_maps_loading, migrations.RunPython.noop),
    ]
