from django.apps import AppConfig


class ScrapingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scraping"
    verbose_name = "Scraping"

    def ready(self):
        from .infrastructure import sqlite  # noqa: F401
        from .infrastructure.builtin import register_builtin_adapters

        register_builtin_adapters()
