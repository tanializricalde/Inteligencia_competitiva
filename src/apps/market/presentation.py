from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Prefetch
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.market.dashboard_service import (
    PERIOD_OPTIONS,
    build_comparison_data,
    build_dashboard_data,
    resolve_dashboard_selection,
)
from apps.market.forms import (
    DashboardPresetForm,
    DashboardSettingsForm,
    NotificationRecipientForm,
)
from apps.market.models import (
    DashboardPreset,
    DashboardSettings,
    DataChange,
    Plan,
)
from apps.notifications.models import NotificationRecipient
from apps.pipeline.application.manual_queue import (
    PipelineQueueUnavailable,
    enqueue_manual_pipeline,
)
from apps.pipeline.application.orchestrator import provider_failure_summary
from apps.pipeline.models import MarketSource, PipelineRun, ProviderRun, SourceRun, StageRun
from apps.scraping.models import (
    ManualScrapeRequest,
    ScrapeRun,
    ScrapeSource,
)

from .branding import BRAND_CONTENT_TYPES, get_application_branding


def legacy_ingestion_unavailable(request, *args, **kwargs):
    raise Http404("La ingesta heredada no está disponible")


@login_required
def dashboard(request):
    selection = resolve_dashboard_selection(request.GET, strict=False)
    if selection.warnings:
        for warning in selection.warnings:
            messages.warning(request, warning)
        return redirect(f"{reverse('dashboard')}?{selection.canonical_query}#dashboard-results")
    for notice in selection.notices:
        messages.info(request, notice)
    dashboard_data = build_dashboard_data(selection)
    settings = get_application_branding(request)
    context = {
        "dashboard_settings": settings,
        "selection": selection,
        "dashboard_data": dashboard_data,
        "filters_applied": bool(request.GET),
        "period_options": PERIOD_OPTIONS,
        "presets": DashboardPreset.objects.filter(is_active=True).order_by(
            "data_scope", "is_system", "name"
        ),
        "can_add_dashboard_preset": request.user.has_perm("market.add_dashboardpreset"),
        "can_change_dashboard_preset": request.user.has_perm("market.change_dashboardpreset"),
        "can_delete_dashboard_preset": request.user.has_perm("market.delete_dashboardpreset"),
        "preset_form": DashboardPresetForm(
            initial={
                "plan_selection": DashboardPreset.PlanSelection.EXPLICIT,
                "providers": [provider.id for provider in selection.providers],
                "plans": [plan.id for plan in selection.plans],
                "feature_selection": (
                    DashboardPreset.FeatureSelection.EXPLICIT
                    if selection.feature_filter_active
                    or selection.preset.feature_selection
                    == DashboardPreset.FeatureSelection.EXPLICIT
                    else DashboardPreset.FeatureSelection.ALL_CURRENT
                ),
                "features": [feature.id for feature in selection.features],
            }
        ),
        "current_preset_form": (
            DashboardPresetForm(instance=selection.preset)
            if not selection.preset.is_system
            else None
        ),
    }
    return render(request, "market/dashboard.html", context)


def application_brand_asset(request, asset: str):
    allowed_assets = {"application_logo", "compact_logo", "favicon", "header_image"}
    if asset not in allowed_assets:
        raise Http404
    settings = DashboardSettings.load()
    configured = getattr(settings, asset)
    if not configured:
        raise Http404
    suffix = configured.name.rsplit(".", 1)[-1].casefold()
    content_type = BRAND_CONTENT_TYPES.get(suffix)
    if content_type is None:
        raise Http404
    try:
        handle = configured.storage.open(configured.name, "rb")
    except OSError:
        return redirect(static("images/dashboard-brand-default.svg"))
    response = FileResponse(handle, content_type=content_type)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if content_type == "image/svg+xml":
        response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@login_required
def dashboard_brand_image(request):
    return application_brand_asset(request, "header_image")


@login_required
@permission_required("market.change_dashboardsettings", raise_exception=True)
def application_settings(request):
    settings = DashboardSettings.load()
    form = DashboardSettingsForm(instance=settings)
    if request.method == "POST":
        form = DashboardSettingsForm(request.POST, request.FILES, instance=settings)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.updated_by = request.user
            form.save()
            messages.success(request, "Configuración de la aplicación actualizada.")
            return redirect("application_settings")
    return render(request, "market/dashboard_settings.html", {"form": form})


@login_required
@require_POST
def dashboard_preset_save(request):
    preset = None
    preset_id = request.POST.get("preset_id", "")
    if preset_id:
        if not request.user.has_perm("market.change_dashboardpreset"):
            raise PermissionDenied
        preset = get_object_or_404(DashboardPreset, pk=preset_id, is_system=False)
    elif not request.user.has_perm("market.add_dashboardpreset"):
        raise PermissionDenied
    form = DashboardPresetForm(request.POST, instance=preset)
    if not form.is_valid():
        selection = resolve_dashboard_selection(request.GET)
        return render(
            request,
            "market/dashboard.html",
            {
                "dashboard_settings": DashboardSettings.load(),
                "selection": selection,
                "dashboard_data": build_dashboard_data(selection),
                "filters_applied": bool(request.GET),
                "period_options": PERIOD_OPTIONS,
                "presets": DashboardPreset.objects.filter(is_active=True),
                "can_add_dashboard_preset": request.user.has_perm("market.add_dashboardpreset"),
                "can_change_dashboard_preset": request.user.has_perm(
                    "market.change_dashboardpreset"
                ),
                "can_delete_dashboard_preset": request.user.has_perm(
                    "market.delete_dashboardpreset"
                ),
                "preset_form": form,
                "current_preset_form": None,
            },
            status=400,
        )
    saved = form.save_with_relations(request.user)
    messages.success(request, f"Vista “{saved.name}” guardada.")
    return redirect(f"/?preset={saved.slug}")


@login_required
@permission_required("market.delete_dashboardpreset", raise_exception=True)
@require_POST
def dashboard_preset_delete(request, preset_id: int):
    preset = get_object_or_404(DashboardPreset, pk=preset_id, is_system=False)
    try:
        preset.delete()
    except (ValidationError, ProtectedError):
        messages.error(request, "La vista está en uso y no puede eliminarse.")
    else:
        messages.success(request, "Vista eliminada.")
    return redirect("dashboard")


@login_required
def comparison(request):
    params = request.GET.copy()
    if not params.getlist("plan") and params.getlist("plans"):
        params.setlist("plan", params.getlist("plans"))
        params.pop("plans", None)
    selection = resolve_dashboard_selection(params, strict=False)
    if selection.warnings:
        for warning in selection.warnings:
            messages.warning(request, warning)
        return redirect(f"{reverse('comparison')}?{selection.canonical_query}")
    for notice in selection.notices:
        messages.info(request, notice)
    default_limit = not bool(params.getlist("plan"))
    comparison_data = build_comparison_data(selection, use_default_limit=default_limit)
    return render(
        request,
        "market/comparison.html",
        {
            "selection": selection,
            "comparison": comparison_data,
            "presets": DashboardPreset.objects.filter(is_active=True).order_by(
                "data_scope", "is_system", "name"
            ),
            "period_options": PERIOD_OPTIONS,
            "selected_plan_ids": {column["id"] for column in comparison_data["columns"]},
        },
    )


@login_required
def plan_history(request, plan_id: int):
    plan = get_object_or_404(Plan.objects.select_related("provider"), pk=plan_id)
    snapshots = list(plan.snapshots.order_by("observed_at"))
    changes = DataChange.objects.filter(new_snapshot__plan=plan).select_related(
        "previous_snapshot", "new_snapshot"
    )
    chart = {
        "labels": [item.observed_at.isoformat() for item in snapshots],
        "values": [float(item.amount) if item.amount is not None else None for item in snapshots],
    }
    return render(
        request,
        "market/history.html",
        {"plan": plan, "snapshots": reversed(snapshots), "changes": changes, "chart": chart},
    )


@login_required
@permission_required("scraping.view_scrapesource", raise_exception=True)
def sources(request):
    return render(
        request,
        "market/sources.html",
        {
            "sources": ScrapeSource.objects.filter(provider__data_scope="real").select_related(
                "provider"
            ),
            "requests": ManualScrapeRequest.objects.select_related("source", "requested_by")[:10],
        },
    )


@login_required
@permission_required("pipeline.view_pipelinerun", raise_exception=True)
def pipeline_runs(request):
    provider_runs = ProviderRun.objects.select_related("provider").prefetch_related(
        Prefetch(
            "stage_runs",
            queryset=StageRun.objects.prefetch_related(
                Prefetch(
                    "source_runs",
                    queryset=SourceRun.objects.select_related("market_source"),
                )
            ),
        )
    )
    runs = list(
        PipelineRun.objects.select_related(
            "profile_version__profile", "requested_by"
        ).prefetch_related(Prefetch("provider_runs", queryset=provider_runs))[:50]
    )
    for run in runs:
        for provider_run in run.provider_runs.all():
            provider_run.display_error_summary = provider_run.error_summary
            if provider_run.status == PipelineRun.Status.FAILED and not provider_run.error_summary:
                provider_run.display_error_summary = provider_failure_summary(provider_run)
    return render(
        request,
        "market/pipeline_runs.html",
        {
            "sources": MarketSource.objects.filter(provider__data_scope="real")
            .select_related("provider")
            .order_by("provider__execution_order", "data_type", "execution_order"),
            "runs": runs,
        },
    )


@require_POST
@login_required
@permission_required("pipeline.add_pipelinerun", raise_exception=True)
def request_pipeline_run(request):
    try:
        run, created = enqueue_manual_pipeline(requested_by=request.user)
    except PipelineQueueUnavailable as exc:
        messages.error(request, str(exc))
    else:
        if created:
            messages.success(
                request,
                "Pipeline completo encolado; el programador ejecutará planes, "
                "características y reseñas.",
            )
        else:
            messages.warning(request, f"Ya existe una ejecución manual pendiente: {run.id}.")
    return redirect("pipeline_runs")


@require_POST
@login_required
@permission_required("scraping.run_scrape", raise_exception=True)
def request_scrape(request, source_id: int | None = None):
    source = None
    if source_id is not None:
        source = get_object_or_404(
            ScrapeSource, pk=source_id, is_active=True, provider__data_scope="real"
        )
    pending = ManualScrapeRequest.objects.filter(
        source=source,
        status__in=(ManualScrapeRequest.Status.PENDING, ManualScrapeRequest.Status.RUNNING),
    ).exists()
    if pending:
        messages.warning(request, "Ya existe una solicitud pendiente para esta fuente.")
    else:
        ManualScrapeRequest.objects.create(source=source, requested_by=request.user)
        messages.success(
            request, "Solicitud registrada; el programador la procesará en segundo plano."
        )
    return redirect("sources")


@login_required
@permission_required("scraping.view_scraperun", raise_exception=True)
def runs(request):
    return render(request, "market/runs.html", {"runs": ScrapeRun.objects.all()[:100]})


@login_required
@permission_required("scraping.view_scraperun", raise_exception=True)
def run_detail(request, run_id: int):
    run = get_object_or_404(ScrapeRun, pk=run_id)
    return render(
        request,
        "market/run_detail.html",
        {"run": run, "results": run.source_results.select_related("source__provider")},
    )


@login_required
@permission_required("notifications.view_notificationrecipient", raise_exception=True)
def functional_settings(request):
    recipient_form = NotificationRecipientForm(prefix="recipient")
    if request.method == "POST":
        kind = request.POST.get("kind")
        if kind == "recipient":
            if not request.user.has_perm("notifications.add_notificationrecipient"):
                raise Http404
            recipient_form = NotificationRecipientForm(request.POST, prefix="recipient")
            if recipient_form.is_valid():
                recipient_form.save()
                messages.success(request, "Destinatario agregado.")
                return redirect("functional_settings")
    return render(
        request,
        "market/settings.html",
        {
            "recipient_form": recipient_form,
            "recipients": NotificationRecipient.objects.all(),
        },
    )
