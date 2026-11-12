from django.apps import AppConfig


class ReviewsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reviews"
    verbose_name = "Reseñas"

    def ready(self) -> None:
        from .infrastructure.builtin import register_builtin_review_adapters

        register_builtin_review_adapters()
