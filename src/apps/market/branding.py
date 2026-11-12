from __future__ import annotations

from django.templatetags.static import static
from django.urls import reverse

from .models import DashboardSettings

DEFAULT_BRAND_IMAGE = "images/dashboard-brand-default.svg"
BRAND_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}


def get_application_branding(request=None) -> DashboardSettings:
    cache_attribute = "_application_branding"
    if request is not None and hasattr(request, cache_attribute):
        return getattr(request, cache_attribute)
    branding = DashboardSettings.load()
    if request is not None:
        setattr(request, cache_attribute, branding)
    return branding


def application_branding_context(request) -> dict[str, DashboardSettings]:
    return {"application_branding": get_application_branding(request)}


def branding_asset_url(asset: str, request=None) -> str:
    branding = get_application_branding(request)
    configured = getattr(branding, asset, None)
    if configured:
        return reverse("application_brand_asset", kwargs={"asset": asset})
    return static(DEFAULT_BRAND_IMAGE)


def branding_asset_content_type(asset: str, request=None) -> str:
    branding = get_application_branding(request)
    configured = getattr(branding, asset, None)
    if not configured:
        return "image/svg+xml"
    suffix = configured.name.rsplit(".", 1)[-1].casefold()
    return BRAND_CONTENT_TYPES.get(suffix, "application/octet-stream")


def admin_site_title(request) -> str:
    return get_application_branding(request).application_name


def admin_site_logo(request) -> str:
    return branding_asset_url("application_logo", request)


def admin_site_icon(request) -> str:
    branding = get_application_branding(request)
    if branding.compact_logo:
        return branding_asset_url("compact_logo", request)
    return admin_site_logo(request)


def admin_site_favicons(request) -> list[dict[str, str]]:
    return [
        {
            "href": branding_asset_url("favicon", request),
            "rel": "icon",
            "type": branding_asset_content_type("favicon", request),
        }
    ]
