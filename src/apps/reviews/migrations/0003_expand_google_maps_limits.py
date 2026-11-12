from django.db import migrations

OLD_CONFIG = {
    "page_size": 20,
    "max_scrolls": 30,
    "stable_scroll_attempts": 3,
    "scroll_pause_ms": 750,
}
NEW_CONFIG = {
    "page_size": 100,
    "max_scrolls": 200,
    "stable_scroll_attempts": 5,
    "scroll_pause_ms": 1200,
    "max_load_seconds": 180,
}


def expand_google_maps_limits(apps, schema_editor):
    ReviewSource = apps.get_model("reviews", "ReviewSource")
    for source in ReviewSource.objects.filter(adapter_key="google_maps_reviews"):
        # Preserve operator customizations; only upgrade the exact seeded defaults.
        if source.max_pages == 5 and source.adapter_config == OLD_CONFIG:
            source.max_pages = 10
            source.adapter_config = NEW_CONFIG
            source.save(update_fields=("max_pages", "adapter_config", "updated_at"))


class Migration(migrations.Migration):
    dependencies = [("reviews", "0002_google_maps_review_sources")]

    operations = [migrations.RunPython(expand_google_maps_limits, migrations.RunPython.noop)]
