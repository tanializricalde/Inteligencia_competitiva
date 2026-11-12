from django.db import migrations, models

import apps.scraping.validators

SOURCES = (
    (
        "anfibius",
        "Anfibius",
        "Reseñas Google Maps Anfibius",
        "https://www.google.com/maps/place/Anfibius+Ecuador/@-0.2597262,-79.1611512,9363m/data=!3m1!1e3!4m18!1m9!3m8!1s0x91d5465e56e9b047:0x6b055a06a877fcfb!2sAnfibius+Ecuador!8m2!3d-0.2611238!4d-79.1367797!9m1!1b1!16s%2Fg%2F11cs0ffs97!3m7!1s0x91d5465e56e9b047:0x6b055a06a877fcfb!8m2!3d-0.2611238!4d-79.1367797!9m1!1b1!16s%2Fg%2F11cs0ffs97?entry=ttu&g_ep=EgoyMDI2MDkyOC4wIKXMDSoASAFQAw%3D%3D",
        "/g/11cs0ffs97",
    ),
    (
        "perseo",
        "Perseo",
        "Reseñas Google Maps Perseo",
        "https://www.google.com/maps/place/PERSEO+%7C+Sistema+Contable:+Gestor+Comercial/@-2.1864395,-77.9284373,1197542m/data=!3m1!1e3!4m8!3m7!1s0x8e2a77685f08830f:0xace9b3998acecfd8!8m2!3d0.0082756!4d-78.4382119!9m1!1b1!16s%2Fg%2F11nckwkl5y?entry=ttu&g_ep=EgoyMDI2MDkyOC4wIKXMDSoASAFQAw%3D%3D",
        "/g/11nckwkl5y",
    ),
    (
        "siigo_ec",
        "Siigo Ecuador",
        "Reseñas Google Maps Siigo Contífico",
        "https://www.google.com/maps/place/Siigo+Cont%C3%ADfico+%7C+Sistema+de+facturaci%C3%B3n+electr%C3%B3nica+%7C+POS+online+%7C+contable/@-2.1543509,-79.8918241,2339m/data=!3m2!1e3!5s0x902d6d988080e2f9:0xbcf80464be0f81fb!4m16!1m7!3m6!1s0x902d6d987f04cd01:0xb340790bf6f17312!2sSiigo+Cont%C3%ADfico+%7C+Sistema+de+facturaci%C3%B3n+electr%C3%B3nica+%7C+POS+online+%7C+contable!8m2!3d-2.1578239!4d-79.8969951!16s%2Fg%2F11c2k42c7j!3m7!1s0x902d6d987f04cd01:0xb340790bf6f17312!8m2!3d-2.1578239!4d-79.8969951!9m1!1b1!16s%2Fg%2F11c2k42c7j?entry=ttu&g_ep=EgoyMDI2MDkyOC4wIKXMDSoASAFQAw%3D%3D",
        "/g/11c2k42c7j",
    ),
)


def configure_sources(apps, schema_editor):
    Provider = apps.get_model("market", "Provider")
    ReviewSource = apps.get_model("reviews", "ReviewSource")
    for code, provider_name, source_name, source_url, entity_id in SOURCES:
        provider, _ = Provider.objects.get_or_create(code=code, defaults={"name": provider_name})
        ReviewSource.objects.get_or_create(
            provider=provider,
            platform="google_maps",
            source_url=source_url,
            defaults={
                "name": source_name,
                "adapter_key": "google_maps_reviews",
                "external_entity_id": entity_id,
                "country_code": "EC",
                "enabled": False,
                "schedule_enabled": False,
                "request_delay_seconds": 2,
                "timeout_seconds": 30,
                "retry_limit": 2,
                "max_pages": 5,
                "max_reviews": 100,
                "review_window": 20,
                "adapter_config": {
                    "page_size": 20,
                    "max_scrolls": 30,
                    "stable_scroll_attempts": 3,
                    "scroll_pause_ms": 750,
                },
            },
        )


class Migration(migrations.Migration):
    dependencies = [("reviews", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="reviewsource",
            name="source_url",
            field=models.URLField(
                max_length=2048,
                validators=[apps.scraping.validators.validate_safe_source_url],
            ),
        ),
        migrations.RunPython(configure_sources, migrations.RunPython.noop),
    ]
