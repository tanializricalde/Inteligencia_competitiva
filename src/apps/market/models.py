from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .validators import validate_brand_image

DEFAULT_APPLICATION_NAME = "Market Watch"


class Provider(models.Model):
    class DataScope(models.TextChoices):
        REAL = "real", "Real"
        DEMO = "demo", "Demostración"

    name = models.CharField(max_length=160)
    code = models.SlugField(max_length=80, unique=True)
    homepage_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    execution_order = models.PositiveIntegerField(default=0)
    data_scope = models.CharField(max_length=8, choices=DataScope.choices, default=DataScope.REAL)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("execution_order", "name")
        indexes = [
            models.Index(
                fields=("data_scope", "is_active", "execution_order"),
                name="provider_scope_active",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Plan(models.Model):
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name="plans")
    external_id = models.CharField(max_length=160, blank=True)
    name = models.CharField(max_length=240)
    product = models.CharField(max_length=160, blank=True)
    stable_key = models.SlugField(max_length=180)
    is_active = models.BooleanField(default=True)
    missing_successes = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("provider__name", "name")
        constraints = [
            models.UniqueConstraint(fields=("provider", "stable_key"), name="uq_plan_stable_key")
        ]
        indexes = [models.Index(fields=("provider", "is_active"), name="plan_provider_active")]

    def __str__(self) -> str:
        return f"{self.provider}: {self.product + ' · ' if self.product else ''}{self.name}"


class PlanSnapshot(models.Model):
    class Periodicity(models.TextChoices):
        MONTHLY = "monthly", "Mensual"
        YEARLY = "yearly", "Anual"
        ONE_TIME = "one_time", "Única"
        CUSTOM = "custom", "Personalizada"
        UNKNOWN = "unknown", "Desconocida"

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="snapshots")
    observed_at = models.DateTimeField()
    observed_name = models.CharField(max_length=240)
    observed_product = models.CharField(max_length=160, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="PEN")
    periodicity = models.CharField(
        max_length=16, choices=Periodicity.choices, default=Periodicity.UNKNOWN
    )
    price_text = models.CharField(max_length=240, blank=True)
    features = models.JSONField(default=dict)
    raw_data = models.JSONField(default=dict)
    content_hash = models.CharField(max_length=67)
    run = models.ForeignKey(
        "scraping.ScrapeRun", on_delete=models.PROTECT, related_name="snapshots"
    )

    class Meta:
        ordering = ("-observed_at",)
        constraints = [
            models.UniqueConstraint(fields=("plan", "content_hash"), name="uq_snapshot_content")
        ]
        indexes = [
            models.Index(fields=("plan", "-observed_at"), name="snapshot_plan_time"),
            models.Index(fields=("run",), name="snapshot_run"),
        ]

    def __str__(self) -> str:
        observed = self.observed_at.strftime("%Y-%m-%d %H:%M") if self.observed_at else "sin fecha"
        return f"{self.observed_name or 'Plan sin nombre'} · {observed}"


class DataChange(models.Model):
    class Kind(models.TextChoices):
        PLAN_ADDED = "plan_added", "Plan agregado"
        PLAN_RETIRED = "plan_retired", "Plan retirado"
        PRICE_CHANGED = "price_changed", "Precio modificado"
        FEATURE_ADDED = "feature_added", "Característica agregada"
        FEATURE_CHANGED = "feature_changed", "Característica modificada"
        FEATURE_REMOVED = "feature_removed", "Característica retirada"
        DETAILS_CHANGED = "details_changed", "Detalles modificados"

    kind = models.CharField(max_length=32, choices=Kind.choices)
    previous_snapshot = models.ForeignKey(
        PlanSnapshot,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="changes_as_previous",
    )
    new_snapshot = models.ForeignKey(
        PlanSnapshot,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="changes_as_new",
    )
    diff = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("-created_at",), name="change_created")]

    def __str__(self) -> str:
        created = self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "sin fecha"
        return f"{self.get_kind_display()} · {created}"


class DashboardPreset(models.Model):
    class PlanSelection(models.TextChoices):
        ALL_CURRENT = "all_current", "Todos los planes vigentes"
        EXPLICIT = "explicit", "Selección explícita"

    class FeatureSelection(models.TextChoices):
        ALL_CURRENT = "all_current", "Todas las características disponibles"
        EXPLICIT = "explicit", "Selección explícita"

    SYSTEM_ALL_SLUG = "all"
    SYSTEM_DEMO_SLUG = "demo"

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    data_scope = models.CharField(
        max_length=8, choices=Provider.DataScope.choices, default=Provider.DataScope.REAL
    )
    plan_selection = models.CharField(
        max_length=16, choices=PlanSelection.choices, default=PlanSelection.ALL_CURRENT
    )
    feature_selection = models.CharField(
        max_length=16, choices=FeatureSelection.choices, default=FeatureSelection.ALL_CURRENT
    )
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_dashboard_presets",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="updated_dashboard_presets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    providers = models.ManyToManyField(
        Provider, through="DashboardPresetProvider", related_name="dashboard_presets"
    )
    plans = models.ManyToManyField(
        "pipeline.MarketPlan",
        through="DashboardPresetPlan",
        related_name="dashboard_presets",
    )
    features = models.ManyToManyField(
        "pipeline.FeatureDefinition",
        through="DashboardPresetFeature",
        related_name="dashboard_presets",
    )

    class Meta:
        ordering = ("is_system", "name", "id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(is_system=False)
                    | models.Q(
                        slug__in=("all", "demo"),
                        plan_selection="all_current",
                        feature_selection="all_current",
                    )
                ),
                name="dashboard_system_preset_shape",
            ),
            models.CheckConstraint(
                condition=(~models.Q(slug="all") | models.Q(is_system=True, data_scope="real")),
                name="dashboard_all_scope",
            ),
            models.CheckConstraint(
                condition=(~models.Q(slug="demo") | models.Q(is_system=True, data_scope="demo")),
                name="dashboard_demo_scope",
            ),
            models.CheckConstraint(
                condition=models.Q(is_system=True) | models.Q(data_scope="real"),
                name="dashboard_custom_real_scope",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_system:
            raise ValidationError("Las vistas del sistema no se pueden eliminar")
        return super().delete(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if not self.is_system and self.data_scope != Provider.DataScope.REAL:
            raise ValidationError("Las vistas personalizadas sólo pueden usar datos reales")
        if self.is_system and self.pk:
            previous = (
                type(self)
                .objects.filter(pk=self.pk)
                .values(
                    "name",
                    "slug",
                    "data_scope",
                    "plan_selection",
                    "feature_selection",
                    "is_active",
                    "is_system",
                )
                .first()
            )
            current = {
                "name": self.name,
                "slug": self.slug,
                "data_scope": self.data_scope,
                "plan_selection": self.plan_selection,
                "feature_selection": self.feature_selection,
                "is_active": self.is_active,
                "is_system": self.is_system,
            }
            if previous and previous != current:
                raise ValidationError("Las vistas del sistema no se pueden modificar")


class DashboardPresetProvider(models.Model):
    preset = models.ForeignKey(DashboardPreset, on_delete=models.CASCADE)
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("preset", "provider"), name="uq_dashboard_preset_provider"
            ),
            models.UniqueConstraint(
                fields=("preset", "position"), name="uq_dashboard_provider_position"
            ),
        ]

    def __str__(self) -> str:
        return f"Vista #{self.preset_id} · competidor #{self.provider_id}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if (
            self.preset_id
            and self.provider_id
            and self.preset.data_scope != self.provider.data_scope
        ):
            raise ValidationError("El competidor y la vista deben pertenecer al mismo ámbito")


class DashboardPresetPlan(models.Model):
    preset = models.ForeignKey(DashboardPreset, on_delete=models.CASCADE)
    plan = models.ForeignKey("pipeline.MarketPlan", on_delete=models.PROTECT)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(fields=("preset", "plan"), name="uq_dashboard_preset_plan"),
            models.UniqueConstraint(
                fields=("preset", "position"), name="uq_dashboard_plan_position"
            ),
        ]

    def __str__(self) -> str:
        return f"Vista #{self.preset_id} · plan #{self.plan_id}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if not self.preset_id or not self.plan_id:
            return
        if self.preset.plan_selection != DashboardPreset.PlanSelection.EXPLICIT:
            raise ValidationError("Sólo una vista explícita puede relacionar planes")
        if self.plan.provider.data_scope != self.preset.data_scope:
            raise ValidationError("El plan y la vista deben pertenecer al mismo ámbito")
        if not DashboardPresetProvider.objects.filter(
            preset=self.preset, provider=self.plan.provider
        ).exists():
            raise ValidationError("El plan debe pertenecer a un competidor incluido en la vista")


class DashboardPresetFeature(models.Model):
    preset = models.ForeignKey(DashboardPreset, on_delete=models.CASCADE)
    feature_definition = models.ForeignKey("pipeline.FeatureDefinition", on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("preset", "feature_definition"),
                name="uq_dashboard_preset_feature",
            ),
            models.UniqueConstraint(
                fields=("preset", "position"),
                name="uq_dashboard_feature_position",
            ),
        ]

    def __str__(self) -> str:
        return f"Vista #{self.preset_id} · característica #{self.feature_definition_id}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if not self.preset_id or not self.feature_definition_id:
            return
        if self.preset.feature_selection != DashboardPreset.FeatureSelection.EXPLICIT:
            raise ValidationError("Sólo una vista explícita puede relacionar características")
        if self.feature_definition.scope != "canonical":
            raise ValidationError("La vista sólo puede usar características canónicas")
        provider_ids = DashboardPresetProvider.objects.filter(preset=self.preset).values(
            "provider_id"
        )
        if not self.feature_definition.values.filter(
            plan_snapshot__provider_run__provider_id__in=provider_ids,
            plan_snapshot__provider_run__status="published",
            plan_snapshot__provider_run__published_at__isnull=False,
        ).exists():
            raise ValidationError(
                "La característica no pertenece al ámbito publicado de los competidores"
            )


class DashboardSettings(models.Model):
    application_name = models.CharField(
        "nombre de la aplicación", max_length=120, default=DEFAULT_APPLICATION_NAME
    )
    application_logo = models.FileField(
        "logo principal",
        upload_to="application/branding/%Y/%m/",
        blank=True,
        validators=(validate_brand_image,),
    )
    application_logo_alt = models.CharField(
        "texto alternativo del logo principal", max_length=180, blank=True
    )
    compact_logo = models.FileField(
        "logo compacto",
        upload_to="application/branding/%Y/%m/",
        blank=True,
        validators=(validate_brand_image,),
    )
    compact_logo_alt = models.CharField(
        "texto alternativo del logo compacto", max_length=180, blank=True
    )
    favicon = models.FileField(
        "favicon",
        upload_to="application/branding/%Y/%m/",
        blank=True,
        validators=(validate_brand_image,),
    )
    header_title = models.CharField(
        "título del encabezado",
        max_length=240,
        default="Dashboard de inteligencia competitiva",
    )
    header_image = models.FileField(
        "logo del encabezado",
        upload_to="dashboard/branding/%Y/%m/",
        blank=True,
        validators=(validate_brand_image,),
    )
    header_image_alt = models.CharField(
        "texto alternativo del logo del encabezado", max_length=180, blank=True
    )
    default_preset = models.ForeignKey(
        DashboardPreset,
        verbose_name="vista predeterminada",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="default_for_settings",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="updated_dashboard_settings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuración de la aplicación"
        verbose_name_plural = "configuración de la aplicación"

    def __str__(self) -> str:
        return self.application_name or DEFAULT_APPLICATION_NAME

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("La configuración global no se elimina")

    def clean(self) -> None:
        super().clean()
        if self.pk not in (None, 1):
            raise ValidationError("Sólo puede existir una configuración global")
        self.application_name = self.application_name.strip()
        if not self.application_name:
            raise ValidationError({"application_name": "Escribe el nombre de la aplicación"})
        for image_field, alt_field in (
            ("application_logo", "application_logo_alt"),
            ("compact_logo", "compact_logo_alt"),
            ("header_image", "header_image_alt"),
        ):
            if getattr(self, image_field) and not getattr(self, alt_field).strip():
                raise ValidationError(
                    {alt_field: "Describe la imagen para usuarios de tecnologías de asistencia"}
                )
        if self.default_preset_id and (
            not self.default_preset.is_active
            or self.default_preset.data_scope != Provider.DataScope.REAL
        ):
            raise ValidationError(
                {"default_preset": "La vista predeterminada debe usar datos reales y estar activa"}
            )

    @classmethod
    def load(cls):
        return cls.objects.select_related("default_preset").filter(pk=1).first() or cls(pk=1)

    @property
    def compact_name(self) -> str:
        words = [word for word in self.application_name.split() if word]
        return "".join(word[0] for word in words[:3]).upper() or "APP"
