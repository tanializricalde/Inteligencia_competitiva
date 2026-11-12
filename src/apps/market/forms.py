from django import forms
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify

from apps.form_styling import StyledFormMixin
from apps.notifications.models import NotificationRecipient
from apps.pipeline.models import FeatureDefinition, MarketPlan, PipelineRun, PlanFeatureValue

from .models import (
    DashboardPreset,
    DashboardPresetFeature,
    DashboardPresetPlan,
    DashboardPresetProvider,
    DashboardSettings,
    Provider,
)

BRAND_FILE_FIELDS = ("application_logo", "compact_logo", "favicon", "header_image")


class NotificationRecipientForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = NotificationRecipient
        fields = (
            "name",
            "email",
            "is_active",
            "notify_errors",
            "notify_changes",
            "notify_recovery",
        )
        labels = {
            "name": "Nombre",
            "email": "Correo electrónico",
            "is_active": "Activo",
            "notify_errors": "Notificar errores",
            "notify_changes": "Notificar cambios",
            "notify_recovery": "Notificar recuperación",
        }


class DashboardSettingsForm(StyledFormMixin, forms.ModelForm):
    BRAND_FILE_FIELDS = BRAND_FILE_FIELDS

    class Meta:
        model = DashboardSettings
        fields = (
            "application_name",
            "application_logo",
            "application_logo_alt",
            "compact_logo",
            "compact_logo_alt",
            "favicon",
            "header_title",
            "header_image",
            "header_image_alt",
            "default_preset",
        )
        widgets = {
            field: forms.ClearableFileInput(
                attrs={
                    "accept": (
                        ".png,.jpg,.jpeg,.webp,.svg,image/png,image/jpeg,image/webp,image/svg+xml"
                    )
                }
            )
            for field in BRAND_FILE_FIELDS
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._previous_file_names = {
            field: getattr(self.instance, field).name if self.instance.pk else ""
            for field in self.BRAND_FILE_FIELDS
        }
        self.fields["default_preset"].queryset = DashboardPreset.objects.filter(
            data_scope=Provider.DataScope.REAL,
            is_active=True,
        ).order_by("is_system", "name")

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if not commit:
            return instance
        for field in self.BRAND_FILE_FIELDS:
            old_name = self._previous_file_names[field]
            current_file = getattr(instance, field)
            current_name = current_file.name if current_file else ""
            if not old_name or old_name == current_name:
                continue
            storage = instance._meta.get_field(field).storage

            def delete_unreferenced_image(old_name=old_name, storage=storage):
                references = Q()
                for candidate in self.BRAND_FILE_FIELDS:
                    references |= Q(**{candidate: old_name})
                if not DashboardSettings.objects.filter(references).exists():
                    storage.delete(old_name)

            transaction.on_commit(delete_unreferenced_image)
        return instance


class DashboardPresetForm(StyledFormMixin, forms.ModelForm):
    providers = forms.ModelMultipleChoiceField(
        label="Competidores",
        queryset=Provider.objects.none(),
        required=True,
        help_text="Sólo proveedores reales con una publicación vigente.",
    )
    plans = forms.ModelMultipleChoiceField(
        label="Planes",
        queryset=MarketPlan.objects.none(),
        required=False,
        help_text="Obligatorio únicamente para una selección explícita.",
    )
    features = forms.ModelMultipleChoiceField(
        label="Características",
        queryset=FeatureDefinition.objects.none(),
        required=False,
        help_text=(
            "En selección explícita, sólo se mostrarán estas características canónicas. "
            "Una selección vacía no muestra ninguna."
        ),
    )

    class Meta:
        model = DashboardPreset
        fields = (
            "name",
            "slug",
            "description",
            "plan_selection",
            "feature_selection",
            "is_active",
        )
        labels = {
            "name": "Nombre",
            "slug": "Identificador",
            "description": "Descripción",
            "plan_selection": "Selección de planes",
            "feature_selection": "Selección de características",
            "is_active": "Activa",
        }
        help_texts = {
            "slug": "Se usa en la URL. Emplea letras, números y guiones.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["feature_selection"].required = False
        published = PipelineRun.Status.PUBLISHED
        self.fields["providers"].queryset = (
            Provider.objects.filter(
                data_scope=Provider.DataScope.REAL,
                is_active=True,
                pipeline_runs__status=published,
                pipeline_runs__published_at__isnull=False,
            )
            .distinct()
            .order_by("execution_order", "name")
        )
        self.fields["plans"].queryset = (
            MarketPlan.objects.filter(
                provider__data_scope=Provider.DataScope.REAL,
                provider__is_active=True,
                is_active=True,
                snapshots__provider_run__status=published,
                snapshots__provider_run__published_at__isnull=False,
            )
            .select_related("provider")
            .distinct()
            .order_by("provider__execution_order", "provider__name", "external_key")
        )
        self.fields["features"].queryset = (
            FeatureDefinition.objects.filter(
                scope=FeatureDefinition.Scope.CANONICAL,
                is_active=True,
                values__plan_snapshot__provider_run__provider__data_scope=Provider.DataScope.REAL,
                values__plan_snapshot__provider_run__status=published,
                values__plan_snapshot__provider_run__published_at__isnull=False,
            )
            .distinct()
            .order_by("category", "display_name", "code")
        )
        if self.instance.pk:
            self.fields["providers"].initial = self.instance.providers.all()
            self.fields["plans"].initial = self.instance.plans.all()
            self.fields["features"].initial = self.instance.features.filter(is_active=True)

    def clean_slug(self):
        value = slugify(self.cleaned_data["slug"])
        if value in {DashboardPreset.SYSTEM_ALL_SLUG, DashboardPreset.SYSTEM_DEMO_SLUG}:
            raise forms.ValidationError("Ese identificador está reservado por el sistema")
        return value

    def clean(self):
        cleaned = super().clean()
        providers = cleaned.get("providers")
        plans = cleaned.get("plans")
        features = cleaned.get("features")
        strategy = cleaned.get("plan_selection")
        feature_strategy = (
            cleaned.get("feature_selection") or DashboardPreset.FeatureSelection.ALL_CURRENT
        )
        cleaned["feature_selection"] = feature_strategy
        if providers is None or plans is None or features is None:
            return cleaned
        provider_ids = set(providers.values_list("id", flat=True))
        if any(plan.provider_id not in provider_ids for plan in plans):
            self.add_error("plans", "Cada plan debe pertenecer a un proveedor seleccionado")
        if strategy == DashboardPreset.PlanSelection.EXPLICIT and not plans:
            self.add_error("plans", "Selecciona al menos un plan para el modo explícito")
        if strategy == DashboardPreset.PlanSelection.ALL_CURRENT and plans:
            self.add_error("plans", "No selecciones planes en el modo todos los vigentes")
        if feature_strategy == DashboardPreset.FeatureSelection.ALL_CURRENT and features:
            self.add_error(
                "features", "No selecciones características en el modo todas las disponibles"
            )
        if feature_strategy == DashboardPreset.FeatureSelection.EXPLICIT:
            values = PlanFeatureValue.objects.filter(
                feature_definition_id__in=features.values_list("id", flat=True),
                plan_snapshot__provider_run__provider_id__in=provider_ids,
                plan_snapshot__provider_run__status=PipelineRun.Status.PUBLISHED,
                plan_snapshot__provider_run__published_at__isnull=False,
            )
            if strategy == DashboardPreset.PlanSelection.EXPLICIT:
                values = values.filter(
                    plan_snapshot__market_plan_id__in=plans.values_list("id", flat=True)
                )
            available_feature_ids = set(values.values_list("feature_definition_id", flat=True))
            if any(feature.id not in available_feature_ids for feature in features):
                self.add_error(
                    "features",
                    "Cada característica debe estar publicada para los competidores "
                    "y planes seleccionados",
                )
        return cleaned

    @transaction.atomic
    def save_with_relations(self, user):
        preset = super().save(commit=False)
        if preset.is_system:
            raise forms.ValidationError("Las vistas del sistema no se pueden modificar")
        preset.data_scope = Provider.DataScope.REAL
        preset.created_by = preset.created_by or user
        preset.updated_by = user
        preset.save()
        DashboardPresetPlan.objects.filter(preset=preset).delete()
        DashboardPresetFeature.objects.filter(preset=preset).delete()
        DashboardPresetProvider.objects.filter(preset=preset).delete()
        for position, provider in enumerate(self.cleaned_data["providers"]):
            DashboardPresetProvider.objects.create(
                preset=preset, provider=provider, position=position
            )
        if preset.plan_selection == DashboardPreset.PlanSelection.EXPLICIT:
            for position, plan in enumerate(self.cleaned_data["plans"]):
                DashboardPresetPlan.objects.create(preset=preset, plan=plan, position=position)
        if preset.feature_selection == DashboardPreset.FeatureSelection.EXPLICIT:
            for position, feature in enumerate(self.cleaned_data["features"]):
                DashboardPresetFeature.objects.create(
                    preset=preset,
                    feature_definition=feature,
                    position=position,
                )
        return preset
