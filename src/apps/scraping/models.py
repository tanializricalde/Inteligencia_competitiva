from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.scraping.validators import validate_safe_source_url


def validate_iana_timezone(value: str) -> None:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValidationError("Zona horaria IANA inválida") from exc


class ScrapeSource(models.Model):
    ADAPTER_CHOICES = (
        ("anfibius_plans", "Anfibius planes"),
        ("example_httpx", "Ejemplo HTTPX"),
        ("example_playwright", "Ejemplo Playwright"),
        ("idrixcontable_plans", "iDrix Contable planes (Playwright)"),
        ("perseo_plans", "Perseo planes"),
        ("siigo_plans", "Siigo planes (Next.js)"),
    )
    provider = models.ForeignKey(
        "market.Provider", on_delete=models.PROTECT, related_name="sources"
    )
    name = models.CharField(max_length=160)
    target_url = models.URLField(validators=[validate_safe_source_url])
    adapter_key = models.CharField(max_length=64, choices=ADAPTER_CHOICES)
    is_active = models.BooleanField(default=True)
    timeout_seconds = models.PositiveSmallIntegerField(default=20)
    retry_limit = models.PositiveSmallIntegerField(default=2)
    min_delay_seconds = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    config = models.JSONField(default=dict, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error_type = models.CharField(max_length=80, blank=True)
    last_error_message = models.CharField(max_length=500, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("provider__name", "name")
        permissions = [("run_scrape", "Puede solicitar ejecuciones de scraping")]

    def __str__(self) -> str:
        return f"{self.provider}: {self.name}"

    def clean(self) -> None:
        super().clean()
        if self.provider_id and self.provider.data_scope != "real":
            raise ValidationError({"provider": "Una fuente de scraping requiere datos REAL"})


class ScrapeRun(models.Model):
    class Origin(models.TextChoices):
        SCHEDULED = "scheduled", "Programada"
        MANUAL = "manual", "Manual"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        RUNNING = "running", "En curso"
        PARTIAL = "partial", "Parcial"
        SUCCEEDED = "succeeded", "Correcta"
        FAILED = "failed", "Fallida"
        CANCELLED = "cancelled", "Cancelada"

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    origin = models.CharField(max_length=16, choices=Origin.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    total_sources = models.PositiveIntegerField(default=0)
    total_plans = models.PositiveIntegerField(default=0)
    total_changes = models.PositiveIntegerField(default=0)
    total_errors = models.PositiveIntegerField(default=0)
    summary = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-id",)
        indexes = [models.Index(fields=("status", "-started_at"), name="run_status_started")]

    def __str__(self) -> str:
        return f"Ejecución #{self.pk or 'nueva'} · {self.get_status_display()}"


class ScrapeSourceResult(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "En curso"
        SUCCEEDED = "succeeded", "Correcta"
        FAILED = "failed", "Fallida"

    run = models.ForeignKey(ScrapeRun, on_delete=models.CASCADE, related_name="source_results")
    source = models.ForeignKey(ScrapeSource, on_delete=models.PROTECT, related_name="run_results")
    status = models.CharField(max_length=16, choices=Status.choices)
    duration_ms = models.PositiveIntegerField(default=0)
    plan_count = models.PositiveIntegerField(default=0)
    error_type = models.CharField(max_length=80, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    evidence = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("run", "source"), name="uq_run_source_result")
        ]

    def __str__(self) -> str:
        return (
            f"Ejecución #{self.run_id or '—'} · fuente #{self.source_id or '—'} · "
            f"{self.get_status_display()}"
        )


class ManualScrapeRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        RUNNING = "running", "En curso"
        COMPLETED = "completed", "Completada"
        FAILED = "failed", "Fallida"

    source = models.ForeignKey(
        ScrapeSource, null=True, blank=True, on_delete=models.PROTECT, related_name="requests"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="scrape_requests"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    run = models.ForeignKey(ScrapeRun, null=True, blank=True, on_delete=models.SET_NULL)
    error_message = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=("status", "created_at"), name="request_status_created")]

    def __str__(self) -> str:
        scope = f"fuente #{self.source_id}" if self.source_id else "todas las fuentes"
        return f"Solicitud #{self.pk or 'nueva'} · {scope} · {self.get_status_display()}"


class ScheduleConfig(models.Model):
    enabled = models.BooleanField(default=True)
    daily_time = models.TimeField(default="07:00")
    timezone = models.CharField(
        max_length=64, default="America/Lima", validators=[validate_iana_timezone]
    )
    next_run_at = models.DateTimeField(null=True, blank=True)
    error_cooldown_minutes = models.PositiveIntegerField(default=60)

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:  # noqa: DJ012
        state = "habilitado" if self.enabled else "deshabilitado"
        return f"Horario diario {self.daily_time} · {state}"


class SchedulerHeartbeat(models.Model):
    name = models.CharField(max_length=40, unique=True, default="primary")
    process_id = models.PositiveIntegerField(null=True, blank=True)
    hostname = models.CharField(max_length=255, blank=True)
    last_seen_at = models.DateTimeField()
    started_at = models.DateTimeField()

    def __str__(self) -> str:
        return f"{self.name or 'scheduler'} · {self.hostname or 'host desconocido'}"
