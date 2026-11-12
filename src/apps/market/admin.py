from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .forms import DashboardSettingsForm
from .models import (
    DashboardPreset,
    DashboardPresetFeature,
    DashboardPresetPlan,
    DashboardPresetProvider,
    DashboardSettings,
    DataChange,
    Plan,
    PlanSnapshot,
    Provider,
)


@admin.register(Provider, Plan, PlanSnapshot, DataChange)
class MarketModelAdmin(ModelAdmin):
    list_per_page = 30
    list_select_related = True


class DashboardPresetProviderInline(TabularInline):
    model = DashboardPresetProvider
    extra = 0


class DashboardPresetPlanInline(TabularInline):
    model = DashboardPresetPlan
    extra = 0


class DashboardPresetFeatureInline(TabularInline):
    model = DashboardPresetFeature
    extra = 0


@admin.register(DashboardPreset)
class DashboardPresetAdmin(ModelAdmin):
    list_display = (
        "name",
        "slug",
        "data_scope",
        "plan_selection",
        "feature_selection",
        "is_active",
        "is_system",
    )
    list_filter = (
        "data_scope",
        "plan_selection",
        "feature_selection",
        "is_active",
        "is_system",
    )
    search_fields = ("name", "slug", "description")
    inlines = (
        DashboardPresetProviderInline,
        DashboardPresetPlanInline,
        DashboardPresetFeatureInline,
    )

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_system:
            return tuple(field.name for field in obj._meta.fields)
        return ("data_scope", "is_system", "created_by", "updated_by", "created_at", "updated_at")

    def get_inline_instances(self, request, obj=None):
        if obj and obj.is_system:
            return []
        return super().get_inline_instances(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        obj.data_scope = Provider.DataScope.REAL
        obj.created_by = obj.created_by or request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(DashboardSettings)
class DashboardSettingsAdmin(ModelAdmin):
    form = DashboardSettingsForm
    list_display = ("application_name", "header_title", "default_preset", "updated_at")
    readonly_fields = ("created_at", "updated_at", "updated_by")

    def has_add_permission(self, request):
        return not DashboardSettings.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
