from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import (
    FeatureDefinition,
    MarketPlan,
    MarketReview,
    MarketSource,
    PipelineConfig,
    PipelineConfigVersion,
    PipelineProfile,
    PipelineProfileStage,
    PipelineProfileVersion,
    PipelineRun,
    PlanFeatureSource,
    PlanFeatureValue,
    PlanFeatureValueSource,
    PlanPriceSnapshot,
    PlanSnapshot,
    ProviderRun,
    QualityIssue,
    ReviewSnapshot,
    RunArtifact,
    ScheduledJob,
    SourceRun,
    StageRun,
)


@admin.register(MarketSource)
class MarketSourceAdmin(ModelAdmin):
    list_display = ("code", "provider", "data_type", "adapter_key", "is_active")
    list_filter = ("data_type", "is_active", "is_required", "provider")
    search_fields = ("code", "name", "adapter_key", "url")


@admin.register(PipelineConfigVersion)
class PipelineConfigVersionAdmin(ModelAdmin):
    list_display = ("pipeline_config", "version", "status", "content_sha256", "published_at")
    list_filter = ("status", "pipeline_config__stage")
    search_fields = ("pipeline_config__code", "content_sha256")

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == obj.Status.PUBLISHED:
            return tuple(field.name for field in obj._meta.fields)
        return ("content_sha256", "published_at")

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status == obj.Status.PUBLISHED:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(PipelineProfileVersion)
class PipelineProfileVersionAdmin(ModelAdmin):
    list_display = ("profile", "version", "status", "published_at")
    list_filter = ("status",)
    search_fields = ("profile__code",)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == obj.Status.PUBLISHED:
            return tuple(field.name for field in obj._meta.fields)
        return ("published_at",)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status == obj.Status.PUBLISHED:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(PipelineRun)
class PipelineRunAdmin(ModelAdmin):
    list_display = ("id", "profile_version", "trigger_type", "status", "started_at", "finished_at")
    list_filter = ("status", "trigger_type", "profile_version__profile")
    search_fields = ("id", "error_summary")
    readonly_fields = tuple(field.name for field in PipelineRun._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProviderRun)
class ProviderRunAdmin(ModelAdmin):
    list_display = ("pipeline_run", "provider", "sequence", "status", "is_complete", "published_at")
    list_filter = ("status", "is_complete", "provider")
    search_fields = ("pipeline_run__id", "provider__code", "error_summary")


@admin.register(StageRun)
class StageRunAdmin(ModelAdmin):
    list_display = ("provider_run", "stage", "sequence", "status", "attempt_count")
    list_filter = ("stage", "status")
    search_fields = ("provider_run__pipeline_run__id", "provider_run__provider__code")


@admin.register(SourceRun)
class SourceRunAdmin(ModelAdmin):
    list_display = ("stage_run", "market_source", "sequence", "status", "attempt_count")
    list_filter = ("status", "market_source__data_type")
    search_fields = ("stage_run__provider_run__pipeline_run__id", "market_source__code")


@admin.register(QualityIssue)
class QualityIssueAdmin(ModelAdmin):
    list_display = ("pipeline_run", "severity", "code", "dataset_type", "created_at")
    list_filter = ("severity", "dataset_type", "code")
    search_fields = ("pipeline_run__id", "message", "row_reference")


@admin.register(RunArtifact)
class RunArtifactAdmin(ModelAdmin):
    list_display = ("pipeline_run", "artifact_type", "relative_path", "size_bytes", "created_at")
    list_filter = ("artifact_type",)
    search_fields = ("pipeline_run__id", "relative_path", "content_sha256")


@admin.register(
    PipelineConfig,
    PipelineProfile,
    PipelineProfileStage,
    ScheduledJob,
    MarketPlan,
    PlanSnapshot,
    PlanPriceSnapshot,
    PlanFeatureSource,
    FeatureDefinition,
    PlanFeatureValue,
    PlanFeatureValueSource,
    MarketReview,
    ReviewSnapshot,
)
class PipelineCatalogAdmin(ModelAdmin):
    list_per_page = 30
    list_select_related = True
