from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("scraping", "0002_alter_scrapesource_target_url")]

    operations = [
        migrations.AlterField(
            model_name="scrapesource",
            name="adapter_key",
            field=models.CharField(
                choices=[
                    ("example_httpx", "Ejemplo HTTPX"),
                    ("example_playwright", "Ejemplo Playwright"),
                    ("siigo_plans", "Siigo planes (Next.js)"),
                ],
                max_length=64,
            ),
        )
    ]
