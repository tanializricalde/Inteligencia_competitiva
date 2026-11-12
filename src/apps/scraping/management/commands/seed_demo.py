from django.core.management.base import BaseCommand

from apps.market.models import Provider
from apps.scraping.models import ScrapeSource


class Command(BaseCommand):
    help = "Crea fuentes de demostración deshabilitadas"

    def handle(self, *args, **options):
        provider, _ = Provider.objects.get_or_create(
            code="demo_fixture",
            defaults={
                "name": "Proveedor fixture de demostración",
                "data_scope": Provider.DataScope.DEMO,
            },
        )
        for key, name in (
            ("example_httpx", "Ejemplo estático"),
            ("example_playwright", "Ejemplo JavaScript"),
        ):
            ScrapeSource.objects.get_or_create(
                provider=provider,
                adapter_key=key,
                defaults={
                    "name": name,
                    "target_url": "https://example.test/plans",
                    "is_active": False,
                },
            )
        self.stdout.write(self.style.SUCCESS("Fuentes demo creadas y deshabilitadas"))
