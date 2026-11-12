from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("scraping", "0004_alter_scrapesource_adapter_key")]

    operations = [
        migrations.AlterField(
            model_name="scrapesource",
            name="adapter_key",
            field=models.CharField(
                choices=[
                    ("anfibius_plans", "Anfibius planes"),
                    ("example_httpx", "Ejemplo HTTPX"),
                    ("example_playwright", "Ejemplo Playwright"),
                    ("idrixcontable_plans", "iDrix Contable planes (Playwright)"),
                    ("perseo_plans", "Perseo planes"),
                    ("siigo_plans", "Siigo planes (Next.js)"),
                ],
                max_length=64,
            ),
        ),
    ]
