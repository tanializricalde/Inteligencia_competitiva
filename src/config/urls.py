from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from apps.market.health import readiness


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("accounts/", include("apps.accounts.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("pipeline/", include("apps.pipeline.urls")),
    path("", include("apps.market.web_urls")),
    path("admin/", admin.site.urls),
    path("public/health", health, name="health"),
    path("public/ready", readiness, name="ready"),
]
