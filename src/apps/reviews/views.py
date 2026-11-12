from statistics import median

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.market.dashboard_service import resolve_dashboard_selection
from apps.market.models import DashboardPreset, Provider
from apps.pipeline.application.queries import latest_published_provider_runs
from apps.pipeline.models import ReviewSnapshot
from apps.reviews.application.export import (
    export_reviews_csv,
    export_reviews_json,
)
from apps.reviews.application.published import (
    published_reviews,
    review_source_label,
    sentiment_label,
)
from apps.reviews.application.services import process_pending_enrichments
from apps.reviews.forms import ReviewFilterForm, ReviewSourceForm
from apps.reviews.models import (
    ManualReviewRequest,
    ReviewRun,
    ReviewSource,
)


def legacy_ingestion_unavailable(request, *args, **kwargs):
    raise Http404("La ingesta heredada de reseñas no está disponible")


def _selection(request, params=None):
    params = params.copy() if params is not None else request.GET.copy()
    if not params.getlist("provider") and params.get("competidor"):
        params.setlist("provider", [params["competidor"]])
        params.pop("competidor", None)
    return resolve_dashboard_selection(params, strict=False)


def _review_filter_form(request, selection):
    data = request.GET.copy()
    data["preset"] = selection.preset.slug
    data["period"] = str(selection.period_months)
    data.setlist("provider", [provider.code for provider in selection.providers])
    presets = DashboardPreset.objects.filter(is_active=True).order_by(
        "data_scope", "is_system", "name"
    )
    return ReviewFilterForm(
        data,
        presets=presets,
        providers=selection.available_providers,
    ), presets


def _redirect_normalized(request, selection, view_name):
    if not selection.warnings:
        return None
    for warning in selection.warnings:
        messages.warning(request, warning)
    return redirect(f"{view_name}?{selection.canonical_query}")


@login_required
@permission_required("reviews.view_marketreview", raise_exception=True)
def review_list(request):
    selection = _selection(request)
    if response := _redirect_normalized(request, selection, "/reviews/"):
        return response
    form, presets = _review_filter_form(request, selection)
    filters = form.cleaned_data if form.is_valid() else {}
    queryset = published_reviews(selection, filters)
    page = Paginator(queryset, 50).get_page(request.GET.get("page"))
    pagination_params = request.GET.copy()
    pagination_params.pop("page", None)
    for review in page.object_list:
        review.source_label = review_source_label(review)
        review.sentiment_label = sentiment_label(review.sentiment_from_rating)
    return render(
        request,
        "reviews/list.html",
        {
            "page": page,
            "filter_form": form,
            "querystring": pagination_params.urlencode(),
            "selection": selection,
            "presets": presets,
        },
    )


@login_required
@permission_required("reviews.view_marketreview", raise_exception=True)
def review_detail(request, review_id: int):
    current_runs = latest_published_provider_runs(data_scope=Provider.DataScope.REAL)
    review = get_object_or_404(
        ReviewSnapshot.objects.filter(provider_run_id__in=current_runs.values("id")).select_related(
            "market_review__provider", "provider_run__provider", "source_run__market_source"
        ),
        pk=review_id,
    )
    review.source_label = review_source_label(review)
    review.sentiment_label = sentiment_label(review.sentiment_from_rating)
    return render(request, "reviews/detail.html", {"review": review})


@login_required
@permission_required("reviews.view_marketreview", raise_exception=True)
def review_summary(request, provider_code: str | None = None):
    params = request.GET.copy()
    if provider_code:
        params.setlist("provider", [provider_code])
    selection = _selection(request, params)
    if response := _redirect_normalized(request, selection, "/reviews/summary/"):
        return response
    form, _presets = _review_filter_form(request, selection)
    filters = form.cleaned_data if form.is_valid() else {}
    queryset = published_reviews(selection, filters)
    rows = list(queryset)
    ratings = []
    response_times = []
    with_response = pending = 0
    distribution = {value: 0 for value in range(1, 6)}
    for review in rows:
        if review.rating_stars:
            ratings.append(review.rating_stars)
            distribution[review.rating_stars] += 1
        if review.has_developer_response is True:
            with_response += 1
        if review.days_to_respond is not None:
            response_times.append(float(review.days_to_respond))
        if review.sentiment_from_rating is None:
            pending += 1
    context = {
        "provider": (selection.providers[0] if len(selection.providers) == 1 else None),
        "total": len(rows),
        "average_rating": sum(ratings) / len(ratings) if ratings else None,
        "distribution": distribution.items(),
        "response_percentage": (with_response / len(rows) * 100) if rows else None,
        "average_response_days": (
            sum(response_times) / len(response_times) if response_times else None
        ),
        "median_response_days": median(response_times) if response_times else None,
        "unclassified_sentiment": pending,
    }
    return render(request, "reviews/summary.html", context)


@login_required
@permission_required("reviews.view_reviewsource", raise_exception=True)
def source_list(request):
    return render(
        request,
        "reviews/sources.html",
        {
            "sources": ReviewSource.objects.filter(
                provider__data_scope=Provider.DataScope.REAL
            ).select_related("provider"),
            "requests": ManualReviewRequest.objects.select_related(
                "source", "provider", "requested_by"
            )[:20],
        },
    )


@login_required
@permission_required("reviews.add_reviewsource", raise_exception=True)
def source_create(request):
    form = ReviewSourceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        source = form.save(commit=False)
        source.full_clean()
        source.save()
        messages.success(request, "Fuente de reseñas creada.")
        return redirect("reviews:sources")
    return render(request, "reviews/source_form.html", {"form": form, "source": None})


@login_required
@permission_required("reviews.change_reviewsource", raise_exception=True)
def source_edit(request, source_id: int):
    source = get_object_or_404(
        ReviewSource, pk=source_id, provider__data_scope=Provider.DataScope.REAL
    )
    form = ReviewSourceForm(request.POST or None, instance=source)
    if request.method == "POST" and form.is_valid():
        source = form.save(commit=False)
        source.full_clean()
        source.save()
        messages.success(request, "Fuente de reseñas actualizada.")
        return redirect("reviews:sources")
    return render(request, "reviews/source_form.html", {"form": form, "source": source})


@require_POST
@login_required
@permission_required("reviews.run_reviews", raise_exception=True)
def request_reviews(request, source_id: int | None = None, provider_id: int | None = None):
    source = (
        get_object_or_404(
            ReviewSource,
            pk=source_id,
            enabled=True,
            provider__data_scope=Provider.DataScope.REAL,
        )
        if source_id
        else None
    )
    provider = (
        get_object_or_404(Provider, pk=provider_id, data_scope=Provider.DataScope.REAL)
        if provider_id
        else None
    )
    pending = ManualReviewRequest.objects.filter(
        source=source,
        provider=provider,
        status__in=(ManualReviewRequest.Status.PENDING, ManualReviewRequest.Status.RUNNING),
    ).exists()
    if pending:
        messages.warning(request, "Ya existe una solicitud pendiente para ese alcance.")
    else:
        ManualReviewRequest.objects.create(
            source=source, provider=provider, requested_by=request.user
        )
        messages.success(request, "Solicitud registrada; el programador la procesará.")
    return redirect("reviews:sources")


@require_POST
@login_required
@permission_required("reviews.enrich_reviews", raise_exception=True)
def enrich_reviews(request):
    completed = process_pending_enrichments(limit=100)
    messages.success(request, f"Se enriquecieron {completed} observaciones.")
    return redirect("reviews:list")


@login_required
@permission_required("reviews.export_reviews", raise_exception=True)
def export_reviews(request, format_name: str = "csv"):
    selection = _selection(request)
    if response := _redirect_normalized(
        request,
        selection,
        "/reviews/export.json" if format_name == "json" else "/reviews/export.csv",
    ):
        return response
    form, _presets = _review_filter_form(request, selection)
    filters = form.cleaned_data if form.is_valid() else {}
    queryset = published_reviews(selection, filters)
    if format_name == "json":
        content = export_reviews_json(queryset)
        response = HttpResponse(content, content_type="application/json; charset=utf-8")
        filename = "resenas.json"
    else:
        content = export_reviews_csv(queryset)
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        filename = "resenas.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@permission_required("reviews.view_reviewrun", raise_exception=True)
def review_runs(request):
    return render(request, "reviews/runs.html", {"runs": ReviewRun.objects.all()[:100]})


@login_required
@permission_required("reviews.view_reviewrun", raise_exception=True)
def review_run_detail(request, run_id: int):
    run = get_object_or_404(ReviewRun, pk=run_id)
    results = run.source_results.select_related("source__provider")
    return render(request, "reviews/run_detail.html", {"run": run, "results": results})
