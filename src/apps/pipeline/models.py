from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.scraping.models import validate_iana_timezone
from apps.scraping.validators import validate_safe_source_url
from data_transformation.feature_rules import FeatureRulesConfigError, parse_feature_rules

FORBIDDEN_CONFIG_KEYS = frozenset(
    {"password", "secret", "token", "cookie", "smtp_password", "api_key", "credentials"}
)


def cached_relation_value(instance, relation: str, attribute: str, fallback: str) -> str:
    related = instance._state.fields_cache.get(relation)
    value = getattr(related, attribute, None) if related is not None else None
    return str(value) if value not in (None, "") else fallback


def canonical_json_hash(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def validate_secret_free_json(value: Any, path: str = "content_json") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).casefold() in FORBIDDEN_CONFIG_KEYS:
                raise ValidationError(f"{path}.{key}: los secretos no se guardan en SQLite")
            validate_secret_free_json(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            validate_secret_free_json(nested, f"{path}[{index}]")


def validate_relative_artifact_path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValidationError("La ruta del artefacto debe ser relativa, POSIX y sin traversal")


class MarketSource(models.Model):
    class DataType(models.TextChoices):
        PLANS = "plans", "Planes"
        FEATURES = "features", "Características"
        REVIEWS = "reviews", "Reseñas"

    provider = models.ForeignKey(
        "market.Provider", on_delete=models.PROTECT, related_name="pipeline_sources"
    )
    code = models.SlugField(max_length=100)
    name = models.CharField(max_length=160)
    data_type = models.CharField(max_length=16, choices=DataType.choices)
    adapter_key = models.CharField(max_length=100)
    url = models.URLField(max_length=2048, validators=[validate_safe_source_url])
    platform_code = models.SlugField(max_length=40, null=True, blank=True)
    country_code = models.CharField(max_length=2, null=True, blank=True)
    execution_order = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    settings_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("data_type", "provider__execution_order", "execution_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("provider", "code"), name="uq_pipe_source_code")
        ]
        indexes = [
            models.Index(
                fields=("data_type", "is_active", "execution_order"),
                name="pipe_source_stage_order",
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider.code}/{self.code}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if self.provider_id and self.provider.data_scope != "real":
            raise ValidationError({"provider": "Las fuentes del pipeline requieren datos REAL"})
        if not isinstance(self.settings_json, dict):
            raise ValidationError({"settings_json": "Debe ser un objeto JSON"})
        validate_secret_free_json(self.settings_json, "settings_json")
        if self.country_code:
            code = self.country_code.strip().upper()
            if len(code) != 2 or not code.isascii() or not code.isalpha():
                raise ValidationError({"country_code": "Debe ser un código ISO-2"})
            self.country_code = code


class PipelineConfig(models.Model):
    class Stage(models.TextChoices):
        EXTRACTION = "extraction", "Extracción"
        CLEANING = "cleaning", "Limpieza"
        NORMALIZATION = "normalization", "Normalización"
        FEATURE_EQUIVALENCE = "feature_equivalence", "Equivalencia de características"

    code = models.SlugField(max_length=100, unique=True)
    stage = models.CharField(max_length=32, choices=Stage.choices)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.code


class ImmutablePublishedMixin:
    IMMUTABLE_FIELDS: tuple[str, ...] = ()

    def _validate_published_immutability(self) -> None:
        if not self.pk:
            return
        previous = (
            type(self).objects.filter(pk=self.pk).values("status", *self.IMMUTABLE_FIELDS).first()
        )
        if not previous or previous["status"] != "published":
            return
        changed = [name for name in self.IMMUTABLE_FIELDS if previous[name] != getattr(self, name)]
        if changed or self.status != "published":
            raise ValidationError("Una versión publicada es inmutable; crea una versión nueva")


class PipelineConfigVersion(ImmutablePublishedMixin, models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        PUBLISHED = "published", "Publicada"
        RETIRED = "retired", "Retirada"

    pipeline_config = models.ForeignKey(
        PipelineConfig, on_delete=models.PROTECT, related_name="versions"
    )
    version = models.PositiveIntegerField()
    schema_version = models.PositiveIntegerField(default=1)
    content_json = models.JSONField()
    content_sha256 = models.CharField(max_length=64, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pipeline_config_versions",
    )
    published_at = models.DateTimeField(null=True, blank=True)

    IMMUTABLE_FIELDS = (
        "pipeline_config_id",
        "version",
        "schema_version",
        "content_json",
        "content_sha256",
        "created_by_id",
    )

    class Meta:
        ordering = ("pipeline_config__code", "-version")
        constraints = [
            models.UniqueConstraint(
                fields=("pipeline_config", "version"), name="uq_pipe_config_version"
            )
        ]

    def __str__(self) -> str:
        return f"{self.pipeline_config.code}@{self.version}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.content_json, dict):
            raise ValidationError({"content_json": "Debe ser un objeto JSON"})
        validate_secret_free_json(self.content_json)
        if (
            self.pipeline_config_id
            and self.pipeline_config.stage == PipelineConfig.Stage.FEATURE_EQUIVALENCE
        ):
            try:
                parse_feature_rules(self.content_json)
            except FeatureRulesConfigError as exc:
                raise ValidationError({"content_json": str(exc)}) from exc
        self._validate_published_immutability()
        expected = canonical_json_hash(self.content_json)
        self.content_sha256 = expected
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()


class PipelineProfile(models.Model):
    code = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    active_version = models.ForeignKey(
        "PipelineProfileVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="active_for_profiles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.code

    def clean(self) -> None:
        super().clean()
        if self.active_version_id:
            if not self.pk or self.active_version.profile_id != self.pk:
                raise ValidationError({"active_version": "La versión pertenece a otro perfil"})
            if self.active_version.status != PipelineProfileVersion.Status.PUBLISHED:
                raise ValidationError({"active_version": "La versión activa debe estar publicada"})


class PipelineProfileVersion(ImmutablePublishedMixin, models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        PUBLISHED = "published", "Publicada"
        RETIRED = "retired", "Retirada"

    profile = models.ForeignKey(PipelineProfile, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pipeline_profile_versions",
    )
    published_at = models.DateTimeField(null=True, blank=True)

    IMMUTABLE_FIELDS = ("profile_id", "version", "description", "created_by_id")

    class Meta:
        ordering = ("profile__code", "-version")
        constraints = [
            models.UniqueConstraint(fields=("profile", "version"), name="uq_pipe_profile_version")
        ]

    def __str__(self) -> str:
        return f"{self.profile.code}@{self.version}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        self._validate_published_immutability()


class PipelineProfileStage(models.Model):
    profile_version = models.ForeignKey(
        PipelineProfileVersion, on_delete=models.CASCADE, related_name="stages"
    )
    stage = models.CharField(max_length=32, choices=PipelineConfig.Stage.choices)
    config_version = models.ForeignKey(
        PipelineConfigVersion, on_delete=models.PROTECT, related_name="profile_stages"
    )
    execution_order = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ("execution_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("profile_version", "stage"), name="uq_pipe_profile_stage"
            ),
            models.UniqueConstraint(
                fields=("profile_version", "execution_order"),
                name="uq_pipe_profile_stage_order",
            ),
        ]

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:  # noqa: DJ012
        return f"{self.get_stage_display()} · perfil v#{self.profile_version_id or '—'}"

    def clean(self) -> None:
        super().clean()
        if self.config_version_id and self.config_version.pipeline_config.stage != self.stage:
            raise ValidationError({"config_version": "La etapa de la configuración no coincide"})
        if (
            self.config_version_id
            and self.config_version.status != PipelineConfigVersion.Status.PUBLISHED
        ):
            raise ValidationError({"config_version": "La configuración debe estar publicada"})
        if (
            self.profile_version_id
            and self.profile_version.status == PipelineProfileVersion.Status.PUBLISHED
        ):
            raise ValidationError("Las etapas de un perfil publicado son inmutables")


class ScheduledJob(models.Model):
    class ConcurrencyPolicy(models.TextChoices):
        SKIP = "skip", "Omitir"
        QUEUE = "queue", "Encolar"

    code = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=160)
    profile = models.ForeignKey(PipelineProfile, on_delete=models.PROTECT, related_name="jobs")
    cron_expression = models.CharField(max_length=100)
    timezone = models.CharField(
        max_length=64, default="America/Lima", validators=[validate_iana_timezone]
    )
    is_active = models.BooleanField(default=True)
    concurrency_policy = models.CharField(
        max_length=16, choices=ConcurrencyPolicy.choices, default=ConcurrencyPolicy.SKIP
    )
    retry_policy_json = models.JSONField(default=dict, blank=True)
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_finished_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:  # noqa: DJ012
        return self.name or self.code or f"Trabajo #{self.pk or 'nuevo'}"

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.retry_policy_json, dict):
            raise ValidationError({"retry_policy_json": "Debe ser un objeto JSON"})
        validate_secret_free_json(self.retry_policy_json, "retry_policy_json")
        try:
            CronTrigger.from_crontab(self.cron_expression, timezone=self.timezone)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"cron_expression": f"Expresión cron inválida: {exc}"}) from exc


class PipelineRun(models.Model):
    class TriggerType(models.TextChoices):
        MANUAL = "manual", "Manual"
        SCHEDULED = "scheduled", "Programada"
        RETRY = "retry", "Reintento"
        REPROCESS = "reprocess", "Reproceso"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        RUNNING = "running", "En curso"
        PARTIAL = "partial", "Parcial"
        FAILED = "failed", "Fallida"
        COMPLETED = "completed", "Completa"
        PUBLISHED = "published", "Publicada"
        CANCELLED = "cancelled", "Cancelada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scheduled_job = models.ForeignKey(
        ScheduledJob, null=True, blank=True, on_delete=models.PROTECT, related_name="runs"
    )
    profile_version = models.ForeignKey(
        PipelineProfileVersion, on_delete=models.PROTECT, related_name="runs"
    )
    trigger_type = models.CharField(max_length=16, choices=TriggerType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pipeline_runs",
    )
    error_summary = models.TextField(blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-started_at", "-id")
        indexes = [models.Index(fields=("status", "-started_at"), name="pipe_run_status_time")]

    def __str__(self) -> str:
        return f"Pipeline {self.pk or 'nuevo'} · {self.get_status_display()}"


class ProviderRun(models.Model):
    pipeline_run = models.ForeignKey(
        PipelineRun, on_delete=models.CASCADE, related_name="provider_runs"
    )
    provider = models.ForeignKey(
        "market.Provider", on_delete=models.PROTECT, related_name="pipeline_runs"
    )
    sequence = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=PipelineRun.Status.choices, default="pending")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    is_complete = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    error_summary = models.TextField(blank=True)

    class Meta:
        ordering = ("sequence", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("pipeline_run", "provider"), name="uq_pipe_run_provider"
            )
        ]
        indexes = [
            models.Index(fields=("provider", "-published_at"), name="pipe_provider_published")
        ]

    def __str__(self) -> str:
        provider = cached_relation_value(
            self, "provider", "name", f"competidor #{self.provider_id or '—'}"
        )
        return f"{provider} · {self.get_status_display()}"


class StageRun(models.Model):
    class Stage(models.TextChoices):
        PLANS = "plans", "Planes"
        FEATURES = "features", "Características"
        REVIEWS = "reviews", "Reseñas"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        RUNNING = "running", "En curso"
        SUCCEEDED = "succeeded", "Correcta"
        FAILED = "failed", "Fallida"
        SKIPPED = "skipped", "Omitida"

    provider_run = models.ForeignKey(
        ProviderRun, on_delete=models.CASCADE, related_name="stage_runs"
    )
    stage = models.CharField(max_length=16, choices=Stage.choices)
    sequence = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    input_row_count = models.PositiveIntegerField(default=0)
    output_row_count = models.PositiveIntegerField(default=0)
    rejected_row_count = models.PositiveIntegerField(default=0)
    error_type = models.CharField(max_length=120, blank=True)
    error_message = models.TextField(blank=True)
    diagnostics_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("sequence", "id")
        constraints = [
            models.UniqueConstraint(fields=("provider_run", "stage"), name="uq_pipe_provider_stage")
        ]

    def __str__(self) -> str:
        return (
            f"{self.get_stage_display()} · ejecución de competidor #{self.provider_run_id or '—'}"
        )


class SourceRun(models.Model):
    status = models.CharField(max_length=16, choices=StageRun.Status.choices, default="pending")
    stage_run = models.ForeignKey(StageRun, on_delete=models.CASCADE, related_name="source_runs")
    market_source = models.ForeignKey(
        MarketSource, on_delete=models.PROTECT, related_name="source_runs"
    )
    sequence = models.PositiveIntegerField()
    attempt_count = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    rows_scraped = models.PositiveIntegerField(default=0)
    rows_cleaned = models.PositiveIntegerField(default=0)
    rows_normalized = models.PositiveIntegerField(default=0)
    content_sha256 = models.CharField(max_length=64, blank=True)
    error_type = models.CharField(max_length=120, blank=True)
    error_message = models.TextField(blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("sequence", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("stage_run", "market_source"), name="uq_pipe_stage_source"
            )
        ]

    def __str__(self) -> str:
        source = cached_relation_value(
            self, "market_source", "code", f"fuente #{self.market_source_id or '—'}"
        )
        return f"{source} · {self.get_status_display()}"


class MarketPlan(models.Model):
    provider = models.ForeignKey(
        "market.Provider", on_delete=models.PROTECT, related_name="pipeline_plans"
    )
    external_key = models.CharField(max_length=240)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "external_key"), name="uq_pipe_plan_external"
            )
        ]
        indexes = [models.Index(fields=("provider", "external_key"), name="pipe_plan_lookup")]

    def __str__(self) -> str:
        provider = cached_relation_value(
            self, "provider", "name", f"competidor #{self.provider_id or '—'}"
        )
        return f"{provider} · {self.external_key or 'plan sin clave'}"


class PlanSnapshot(models.Model):
    market_plan = models.ForeignKey(MarketPlan, on_delete=models.PROTECT, related_name="snapshots")
    provider_run = models.ForeignKey(
        ProviderRun, on_delete=models.PROTECT, related_name="plan_snapshots"
    )
    source_run = models.ForeignKey(
        SourceRun, null=True, blank=True, on_delete=models.PROTECT, related_name="plan_snapshots"
    )
    observed_at = models.DateTimeField()
    plan_name = models.CharField(max_length=240)
    normalized_name = models.CharField(max_length=240, blank=True)
    product_code = models.CharField(max_length=160, blank=True)
    source_url = models.URLField(max_length=2048, blank=True)
    promotion_text = models.TextField(null=True, blank=True)
    is_offer_active = models.BooleanField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ("add", "change", "delete")
        permissions = [("view_pipeline_plan_snapshot", "Puede ver snapshots del pipeline")]
        constraints = [
            models.UniqueConstraint(
                fields=("provider_run", "market_plan"), name="uq_pipe_run_plan_snapshot"
            )
        ]
        indexes = [models.Index(fields=("market_plan", "-observed_at"), name="pipe_plan_observed")]

    def __str__(self) -> str:
        return f"{self.plan_name or 'Plan sin nombre'} · ejecución #{self.provider_run_id or '—'}"


class PlanPriceSnapshot(models.Model):
    class BillingPeriod(models.TextChoices):
        MONTHLY = "monthly", "Mensual"
        ANNUAL = "annual", "Anual"
        QUARTERLY = "quarterly", "Trimestral"
        ONE_TIME = "one_time", "Única"
        OTHER = "other", "Otra"

    class SourceKind(models.TextChoices):
        SCRAPED = "scraped", "Observado"
        CALCULATED = "calculated", "Calculado"

    plan_snapshot = models.ForeignKey(PlanSnapshot, on_delete=models.CASCADE, related_name="prices")
    billing_period = models.CharField(max_length=16, choices=BillingPeriod.choices)
    currency_code = models.CharField(max_length=3)
    amount = models.DecimalField(max_digits=18, decimal_places=4)
    effective_monthly_amount = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    discount_percentage = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    is_promotional = models.BooleanField(default=False)
    source_kind = models.CharField(max_length=16, choices=SourceKind.choices)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("plan_snapshot", "billing_period", "source_kind"),
                name="uq_pipe_plan_price_kind",
            )
        ]

    def __str__(self) -> str:
        return f"{self.currency_code or '—'} {self.amount} · {self.get_billing_period_display()}"


class PlanFeatureSource(models.Model):
    plan_snapshot = models.ForeignKey(
        PlanSnapshot, on_delete=models.CASCADE, related_name="feature_sources"
    )
    source_run = models.ForeignKey(
        SourceRun, null=True, blank=True, on_delete=models.PROTECT, related_name="feature_sources"
    )
    source_row_key = models.CharField(max_length=160)
    category = models.CharField(max_length=160, null=True, blank=True)
    raw_name = models.TextField()
    normalized_name = models.CharField(max_length=240)
    included = models.BooleanField(null=True, blank=True)
    position = models.PositiveIntegerField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("plan_snapshot", "source_row_key"), name="uq_pipe_feature_source_row"
            )
        ]

    def __str__(self) -> str:
        return (self.normalized_name or self.raw_name or "Característica sin nombre")[:120]


class FeatureDefinition(models.Model):
    class DataType(models.TextChoices):
        BOOLEAN = "boolean", "Booleano"
        INTEGER = "integer", "Entero"
        DECIMAL = "decimal", "Decimal"
        STRING = "string", "Texto"
        STRING_LIST = "string_list", "Lista de textos"

    class Scope(models.TextChoices):
        CANONICAL = "canonical", "Canónica"
        PROVIDER = "provider", "Por proveedor"

    class Origin(models.TextChoices):
        CONFIGURED = "configured", "Configurada"
        FALLBACK = "fallback", "Fallback"

    code = models.SlugField(max_length=160)
    display_name = models.CharField(max_length=200)
    data_type = models.CharField(max_length=16, choices=DataType.choices)
    unit = models.CharField(max_length=40, null=True, blank=True)
    category = models.CharField(max_length=120, null=True, blank=True)
    scope = models.CharField(max_length=16, choices=Scope.choices)
    provider = models.ForeignKey(
        "market.Provider",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="feature_definitions",
    )
    origin = models.CharField(max_length=16, choices=Origin.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(scope="canonical", provider__isnull=True)
                    | models.Q(scope="provider", provider__isnull=False)
                ),
                name="pipe_feature_scope_provider",
            ),
            models.UniqueConstraint(
                fields=("code",),
                condition=models.Q(scope="canonical"),
                name="uq_pipe_canonical_feature",
            ),
            models.UniqueConstraint(
                fields=("provider", "code"),
                condition=models.Q(scope="provider"),
                name="uq_pipe_provider_feature",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.scope == self.Scope.CANONICAL and self.provider_id is not None:
            raise ValidationError({"provider": "Una característica canónica no tiene proveedor"})
        if self.scope == self.Scope.PROVIDER and self.provider_id is None:
            raise ValidationError({"provider": "El scope provider requiere proveedor"})

    def __str__(self) -> str:  # noqa: DJ012
        return f"{self.display_name or self.code or 'Característica'} · {self.code or 'sin código'}"


class PlanFeatureValue(models.Model):
    class Availability(models.TextChoices):
        PRESENT = "present", "Presente"
        EXCLUDED = "excluded", "Excluida"
        UNKNOWN = "unknown", "Desconocida"
        NOT_APPLICABLE = "not_applicable", "No aplica"

    class Origin(models.TextChoices):
        RULE = "rule", "Regla"
        FALLBACK = "fallback", "Fallback"
        DERIVED = "derived", "Derivada"
        DEFAULT = "default", "Default"

    plan_snapshot = models.ForeignKey(
        PlanSnapshot, on_delete=models.CASCADE, related_name="feature_values"
    )
    feature_definition = models.ForeignKey(
        FeatureDefinition, on_delete=models.PROTECT, related_name="values"
    )
    value_boolean = models.BooleanField(null=True, blank=True)
    value_integer = models.BigIntegerField(null=True, blank=True)
    value_decimal = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    value_text = models.TextField(null=True, blank=True)
    value_json = models.JSONField(null=True, blank=True)
    availability = models.CharField(max_length=20, choices=Availability.choices)
    origin = models.CharField(max_length=16, choices=Origin.choices)
    source_rule_id = models.CharField(max_length=240, null=True, blank=True)
    is_derived = models.BooleanField(default=False)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("plan_snapshot", "feature_definition"),
                name="uq_pipe_plan_feature_value",
            ),
            models.CheckConstraint(
                condition=(
                    ~(models.Q(value_boolean__isnull=False) & models.Q(value_integer__isnull=False))
                    & ~(
                        models.Q(value_boolean__isnull=False)
                        & models.Q(value_decimal__isnull=False)
                    )
                    & ~(models.Q(value_boolean__isnull=False) & models.Q(value_text__isnull=False))
                    & ~(models.Q(value_boolean__isnull=False) & models.Q(value_json__isnull=False))
                    & ~(
                        models.Q(value_integer__isnull=False)
                        & models.Q(value_decimal__isnull=False)
                    )
                    & ~(models.Q(value_integer__isnull=False) & models.Q(value_text__isnull=False))
                    & ~(models.Q(value_integer__isnull=False) & models.Q(value_json__isnull=False))
                    & ~(models.Q(value_decimal__isnull=False) & models.Q(value_text__isnull=False))
                    & ~(models.Q(value_decimal__isnull=False) & models.Q(value_json__isnull=False))
                    & ~(models.Q(value_text__isnull=False) & models.Q(value_json__isnull=False))
                ),
                name="pipe_feature_at_most_one_value",
            ),
        ]
        indexes = [
            models.Index(fields=("plan_snapshot", "feature_definition"), name="pipe_feature_lookup")
        ]

    def clean(self) -> None:
        super().clean()
        populated = {
            "boolean": self.value_boolean,
            "integer": self.value_integer,
            "decimal": self.value_decimal,
            "string": self.value_text,
            "string_list": self.value_json,
        }
        non_null = [name for name, value in populated.items() if value is not None]
        if len(non_null) > 1:
            raise ValidationError("Sólo una columna value_* puede contener datos")
        if (
            non_null
            and self.feature_definition_id
            and non_null[0] != self.feature_definition.data_type
        ):
            raise ValidationError("El valor no coincide con FeatureDefinition.data_type")
        if (
            self.feature_definition_id
            and self.feature_definition.data_type == "string_list"
            and self.value_json is not None
            and not isinstance(self.value_json, list)
        ):
            raise ValidationError({"value_json": "string_list requiere un arreglo JSON"})

    def __str__(self) -> str:  # noqa: DJ012
        definition = cached_relation_value(
            self,
            "feature_definition",
            "display_name",
            f"característica #{self.feature_definition_id or '—'}",
        )
        return f"{definition} · {self.get_availability_display()}"


class PlanFeatureValueSource(models.Model):
    plan_feature_value = models.ForeignKey(
        PlanFeatureValue, on_delete=models.CASCADE, related_name="source_links"
    )
    plan_feature_source = models.ForeignKey(
        PlanFeatureSource, on_delete=models.PROTECT, related_name="value_links"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("plan_feature_value", "plan_feature_source"),
                name="uq_pipe_feature_value_source",
            )
        ]

    def __str__(self) -> str:
        return (
            f"Valor #{self.plan_feature_value_id or '—'} · "
            f"fuente #{self.plan_feature_source_id or '—'}"
        )


class MarketReview(models.Model):
    provider = models.ForeignKey(
        "market.Provider", on_delete=models.PROTECT, related_name="pipeline_reviews"
    )
    platform_code = models.SlugField(max_length=40)
    external_review_id = models.CharField(max_length=500)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        default_permissions = ("add", "change", "delete")
        permissions = [("view_pipeline_market_review", "Puede ver reseñas del pipeline")]
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "platform_code", "external_review_id"),
                name="uq_pipe_review_external",
            )
        ]
        indexes = [
            models.Index(
                fields=("provider", "platform_code", "external_review_id"),
                name="pipe_review_lookup",
            )
        ]

    def __str__(self) -> str:
        provider = cached_relation_value(
            self, "provider", "name", f"competidor #{self.provider_id or '—'}"
        )
        identifier = (self.external_review_id or "reseña sin identificador")[:80]
        return f"{provider} · {identifier}"


class ReviewSnapshot(models.Model):
    market_review = models.ForeignKey(
        MarketReview, on_delete=models.PROTECT, related_name="snapshots"
    )
    provider_run = models.ForeignKey(
        ProviderRun, on_delete=models.PROTECT, related_name="review_snapshots"
    )
    source_run = models.ForeignKey(
        SourceRun, null=True, blank=True, on_delete=models.PROTECT, related_name="review_snapshots"
    )
    country_code = models.CharField(max_length=2, null=True, blank=True)
    user_name = models.TextField(null=True, blank=True)
    rating_stars = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    customer_comment = models.TextField(null=True, blank=True)
    has_developer_response = models.BooleanField(null=True, blank=True)
    developer_response = models.TextField(null=True, blank=True)
    ingested_at = models.DateTimeField()
    review_published_at = models.DateTimeField(null=True, blank=True)
    review_updated_at = models.DateTimeField(null=True, blank=True)
    response_published_at = models.DateTimeField(null=True, blank=True)
    sentiment_from_rating = models.CharField(max_length=16, null=True, blank=True)
    days_to_respond = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    content_sha256 = models.CharField(max_length=64)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("provider_run", "market_review"), name="uq_pipe_run_review_snapshot"
            ),
        ]
        indexes = [
            models.Index(fields=("market_review", "-ingested_at"), name="pipe_review_ingested"),
            models.Index(fields=("rating_stars",), name="pipe_review_rating"),
        ]

    def __str__(self) -> str:
        user = (self.user_name or "Usuario anónimo").strip()[:80]
        return f"{user} · {self.rating_stars or 'sin calificación'}"


class RunArtifact(models.Model):
    class ArtifactType(models.TextChoices):
        RAW = "raw", "Raw"
        CLEAN = "clean", "Clean"
        NORMALIZED = "normalized", "Normalizado"
        QUALITY_REPORT = "quality_report", "Reporte de calidad"
        FEATURE_RULES_REPORT = "feature_rules_report", "Reporte de reglas"
        WIDE_EXPORT = "wide_export", "Exportación ancha"
        LOG = "log", "Log"

    pipeline_run = models.ForeignKey(
        PipelineRun, on_delete=models.CASCADE, related_name="artifacts"
    )
    provider_run = models.ForeignKey(
        ProviderRun, null=True, blank=True, on_delete=models.CASCADE, related_name="artifacts"
    )
    stage_run = models.ForeignKey(
        StageRun, null=True, blank=True, on_delete=models.CASCADE, related_name="artifacts"
    )
    artifact_type = models.CharField(max_length=32, choices=ArtifactType.choices)
    relative_path = models.CharField(max_length=500, validators=[validate_relative_artifact_path])
    content_sha256 = models.CharField(max_length=64)
    size_bytes = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("pipeline_run", "relative_path"), name="uq_pipe_artifact_path"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_artifact_type_display()} · {self.relative_path or 'sin ruta'}"


class QualityIssue(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "Información"
        WARNING = "warning", "Advertencia"
        ERROR = "error", "Error"

    pipeline_run = models.ForeignKey(
        PipelineRun, on_delete=models.CASCADE, related_name="quality_issues"
    )
    provider_run = models.ForeignKey(
        ProviderRun, null=True, blank=True, on_delete=models.CASCADE, related_name="quality_issues"
    )
    stage_run = models.ForeignKey(
        StageRun, null=True, blank=True, on_delete=models.CASCADE, related_name="quality_issues"
    )
    source_run = models.ForeignKey(
        SourceRun, null=True, blank=True, on_delete=models.CASCADE, related_name="quality_issues"
    )
    severity = models.CharField(max_length=16, choices=Severity.choices)
    code = models.SlugField(max_length=100)
    message = models.TextField()
    dataset_type = models.CharField(max_length=32)
    column_name = models.CharField(max_length=160, null=True, blank=True)
    row_reference = models.CharField(max_length=160, null=True, blank=True)
    value_json = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=("pipeline_run", "severity", "created_at"), name="pipe_issue_run_severity"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_severity_display()} · {self.code or 'sin código'}"
