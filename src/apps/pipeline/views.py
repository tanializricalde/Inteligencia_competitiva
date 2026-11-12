from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.pipeline.application.queries import latest_feature_matrix


def _requested_at(request):
    raw = request.GET.get("at")
    if not raw:
        return None, None
    parsed = parse_datetime(raw)
    if parsed is None or timezone.is_naive(parsed):
        return None, JsonResponse(
            {"error": "at debe ser una fecha ISO-8601 con zona horaria"}, status=400
        )
    return parsed, None


@login_required
def features_wide(request):
    at, error = _requested_at(request)
    if error is not None:
        return error
    frame = latest_feature_matrix(at=at)
    frame = frame.astype(object).where(frame.notna(), None)
    return JsonResponse(
        {
            "at": at.isoformat() if at else None,
            "columns": list(frame.columns),
            "rows": frame.to_dict(orient="records"),
        },
        json_dumps_params={"ensure_ascii": False},
    )
