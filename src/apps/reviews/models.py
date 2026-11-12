from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.reviews.domain import normalize_country_code, response_days
from apps.scraping.models import validate_iana_timezone
from apps.scraping.validators import validate_safe_source_url


class ReviewSource(models.Model):
    class Platform(models.TextChoices):
        GOOGLE_PLAY = "google_play", "Google Play Store"
        GOOGLE_MAPS = "google_maps", "Google Maps"
        OTHER = "other", "Otra"

    class State(models.TextChoices):
        IDLE = "idle", "En espera"
        RUNNING = "running", "En curso"
        ERROR = "error", "Con error"

    provider = models.ForeignKey(
        "market.Provider", on_delete=models.PROTECT, related_name="review_sources"
    )
    name = models.CharField(max_length=160)
    platform = models.CharField(max_length=32, choices=Platform.choices)
    adapter_key = models.CharField(max_length=80)
    source_url = models.URLField(max_length=2048, validators=[validate_safe_source_url])
    external_entity_id = models.CharField(max_length=255, blank=True)
    country_code = models.CharField(max_length=2, null=True, blank=True)
    enabled = models.BooleanField(default=False)
    schedule_enabled = models.BooleanField(default=True)
    request_delay_seconds = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    timeout_seconds = models.PositiveSmallIntegerField(default=20)
    retry_limit = models.PositiveSmallIntegerField(default=2)
    max_pages = models.PositiveSmallIntegerField(default=5)
    max_reviews = models.PositiveIntegerField(default=500)
    review_window = models.PositiveSmallIntegerField(default=25)
    adapter_config = models.JSONField(default=dict, blank=True)
    last_cursor = models.JSONField(default=dict, blank=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.IDLE)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error_type = models.CharField(max_length=80, blank=True)
    last_error_message = models.CharField(max_length=500, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("provider__name", "platform", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "platform", "source_url"), name="uq_review_source_target"
            )
        ]
        indexes = [
            models.Index(
                fields=("provider", "platform", "enabled"), name="review_src_provider_plat"
            ),
            models.Index(fields=("enabled", "state"), name="review_src_enabled_state"),
        ]
        permissions = [
            ("run_reviews", "Puede solicitar scraping de reseñas"),
            ("export_reviews", "Puede exportar reseñas"),
            ("enrich_reviews", "Puede ejecutar enriquecimiento de reseñas"),
            ("view_review_evidence", "Puede consultar evidencia técnica de reseñas"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.provider_id and self.provider.data_scope != "real":
            raise ValidationError({"provider": "Una fuente de reseñas requiere datos REAL"})
        try:
            self.country_code = normalize_country_code(self.country_code)
        except ValueError as exc:
            raise ValidationError({"country_code": str(exc)}) from exc
        if not isinstance(self.adapter_config, dict):
            raise ValidationError({"adapter_config": "Debe ser un objeto JSON"})
        if not isinstance(self.last_cursor, dict):
            raise ValidationError({"last_cursor": "Debe ser un objeto JSON"})

    def __str__(self) -> str:  # noqa: DJ012
        return f"{self.provider}: {self.name}"


class ReviewRun(models.Model):
    class Origin(models.TextChoices):
        SCHEDULED = "scheduled", "Programada"
        MANUAL = "manual", "Manual"

    class Status(models.TextChoices):
        RUNNING = "running", "En curso"
        PARTIAL = "partial", "Parcial"
        SUCCEEDED = "succeeded", "Correcta"
        FAILED = "failed", "Fallida"

    origin = models.CharField(max_length=16, choices=Origin.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    total_sources = models.PositiveIntegerField(default=0)
    total_reviews = models.PositiveIntegerField(default=0)
    total_new = models.PositiveIntegerField(default=0)
    total_updated = models.PositiveIntegerField(default=0)
    total_responses = models.PositiveIntegerField(default=0)
    total_errors = models.PositiveIntegerField(default=0)
    summary = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-id",)
        indexes = [models.Index(fields=("status", "-started_at"), name="review_run_status_time")]

    def __str__(self) -> str:
        return f"Ejecución de reseñas #{self.pk or 'nueva'} · {self.get_status_display()}"


class ReviewSourceResult(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "En curso"
        SUCCEEDED = "succeeded", "Correcta"
        FAILED = "failed", "Fallida"
        SKIPPED = "skipped", "Omitida"

    run = models.ForeignKey(ReviewRun, on_delete=models.CASCADE, related_name="source_results")
    source = models.ForeignKey(ReviewSource, on_delete=models.PROTECT, related_name="run_results")
    status = models.CharField(max_length=16, choices=Status.choices)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    pages = models.PositiveIntegerField(default=0)
    found_count = models.PositiveIntegerField(default=0)
    new_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    new_response_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    error_type = models.CharField(max_length=80, blank=True)
    error_message = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("run", "source"), name="uq_review_run_source")
        ]

    def __str__(self) -> str:
        return (
            f"Ejecución #{self.run_id or '—'} · fuente #{self.source_id or '—'} · "
            f"{self.get_status_display()}"
        )


class MarketReview(models.Model):
    source = models.ForeignKey(ReviewSource, on_delete=models.PROTECT, related_name="reviews")
    external_review_id = models.CharField(max_length=255, blank=True)
    review_id = models.CharField(max_length=240)
    identity_hash = models.CharField(max_length=80)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-last_seen_at",)
        constraints = [
            models.UniqueConstraint(fields=("source", "review_id"), name="uq_review_identity"),
            models.UniqueConstraint(fields=("source", "identity_hash"), name="uq_review_hash"),
        ]
        indexes = [
            models.Index(fields=("source", "-last_seen_at"), name="review_source_seen"),
            models.Index(fields=("is_visible", "-last_seen_at"), name="review_visible_seen"),
        ]

    @property
    def provider(self):
        return self.source.provider

    def __str__(self) -> str:  # noqa: DJ012
        return self.review_id


class ReviewObservation(models.Model):
    review = models.ForeignKey(MarketReview, on_delete=models.PROTECT, related_name="observations")
    observed_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    author_name = models.TextField(null=True, blank=True)
    rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    review_text = models.TextField(null=True, blank=True)
    app_id = models.CharField(max_length=255, null=True, blank=True)
    country_code = models.CharField(max_length=2, null=True, blank=True)
    app_version = models.CharField(max_length=80, null=True, blank=True)
    helpful_votes = models.PositiveIntegerField(null=True, blank=True)
    developer_response_text = models.TextField(null=True, blank=True)
    developer_response_at = models.DateTimeField(null=True, blank=True)
    response_known = models.BooleanField(null=True, blank=True)
    raw_payload = models.JSONField(null=True, blank=True)
    content_hash = models.CharField(max_length=80)
    run = models.ForeignKey(ReviewRun, on_delete=models.PROTECT, related_name="observations")
    source_result = models.ForeignKey(
        ReviewSourceResult, on_delete=models.PROTECT, related_name="observations"
    )

    class Meta:
        ordering = ("-observed_at",)
        constraints = [
            models.UniqueConstraint(fields=("review", "content_hash"), name="uq_review_observation")
        ]
        indexes = [
            models.Index(fields=("review", "-observed_at"), name="review_obs_review_time"),
            models.Index(fields=("published_at",), name="review_obs_published"),
            models.Index(fields=("rating",), name="review_obs_rating"),
        ]

    def clean(self) -> None:
        super().clean()
        try:
            response_days(self.published_at, self.developer_response_at)
        except ValueError as exc:
            raise ValidationError({"developer_response_at": str(exc)}) from exc

    @property
    def has_response(self) -> bool | None:
        if self.developer_response_text is not None or self.developer_response_at is not None:
            return True
        return self.response_known

    def __str__(self) -> str:  # noqa: DJ012
        author = (self.author_name or "Autor anónimo").strip()[:80]
        return f"{author} · {self.rating or 'sin calificación'}"

    @property
    def days_to_response(self):
        return response_days(self.published_at, self.developer_response_at)


class ReviewEnrichment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        PROCESSING = "processing", "Procesando"
        COMPLETED = "completed", "Completado"
        FAILED = "failed", "Fallido"
        NOT_APPLICABLE = "not_applicable", "No aplica"

    observation = models.ForeignKey(
        ReviewObservation, on_delete=models.PROTECT, related_name="enrichments"
    )
    category = models.CharField(max_length=120, null=True, blank=True)
    sentiment = models.CharField(max_length=40, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    analyzer = models.CharField(max_length=120, default="rules-es")
    analyzer_version = models.CharField(max_length=40, default="1.0")
    processed_at = models.DateTimeField(null=True, blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("observation", "analyzer", "analyzer_version"),
                name="uq_review_enrichment_version",
            )
        ]
        indexes = [models.Index(fields=("status", "created_at"), name="review_enrich_status")]

    def __str__(self) -> str:
        return f"Enriquecimiento #{self.pk or 'nuevo'} · {self.get_status_display()}"


class ManualReviewRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        RUNNING = "running", "En curso"
        COMPLETED = "completed", "Completada"
        FAILED = "failed", "Fallida"

    source = models.ForeignKey(
        ReviewSource, null=True, blank=True, on_delete=models.PROTECT, related_name="requests"
    )
    provider = models.ForeignKey(
        "market.Provider",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="review_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="review_requests"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    run = models.ForeignKey(ReviewRun, null=True, blank=True, on_delete=models.SET_NULL)
    error_message = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=("status", "created_at"), name="review_req_status_time")]
        constraints = [
            models.CheckConstraint(
                condition=~(models.Q(source__isnull=False) & models.Q(provider__isnull=False)),
                name="review_request_one_scope",
            )
        ]

    def __str__(self) -> str:
        if self.source_id:
            scope = f"fuente #{self.source_id}"
        elif self.provider_id:
            scope = f"competidor #{self.provider_id}"
        else:
            scope = "todas las fuentes"
        return f"Solicitud #{self.pk or 'nueva'} · {scope} · {self.get_status_display()}"


class ReviewScheduleConfig(models.Model):
    enabled = models.BooleanField(default=False)
    daily_time = models.TimeField(default="08:00")
    timezone = models.CharField(
        max_length=64, default="America/Lima", validators=[validate_iana_timezone]
    )
    next_run_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:  # noqa: DJ012
        state = "habilitado" if self.enabled else "deshabilitado"
        return f"Horario diario de reseñas {self.daily_time} · {state}"
