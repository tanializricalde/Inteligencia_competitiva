from pathlib import Path

from django.contrib import admin

ROOT = Path(__file__).resolve().parents[1]
MANUALS = ROOT / "docs" / "manuales"


def test_admin_manual_covers_every_registered_model():
    manual = (MANUALS / "manual-django-admin.md").read_text(encoding="utf-8")

    registered_labels = {model._meta.label for model in admin.site._registry}
    documented_labels = {label for label in registered_labels if f"`{label}`" in manual}

    assert documented_labels == registered_labels


def test_portal_manual_covers_functional_screens_and_core_paths():
    manual = (MANUALS / "manual-portal-principal.md").read_text(encoding="utf-8")
    expected_sections = {
        "## Ingreso, contraseña y cierre de sesión",
        "## Resumen: dashboard competitivo",
        "## Configuración de la aplicación",
        "## Comparación de planes",
        "## Historial de un plan",
        "## Reseñas",
        "## Detalle de reseña",
        "## Resumen de reseñas",
        "## Pipeline de mercado",
        "## Notificaciones",
    }
    core_paths = {
        "/accounts/login/",
        "/accounts/password/reset/",
        "/accounts/password/change/",
        "/application/settings/",
        "/comparison/",
        "/plans/ID/history/",
        "/reviews/",
        "/reviews/summary/",
        "/pipeline-runs/",
        "/settings/",
    }

    assert all(section in manual for section in expected_sections)
    assert all(path in manual for path in core_paths)


def test_user_manuals_are_cross_linked_and_mark_sensitive_screenshots():
    portal = (MANUALS / "manual-portal-principal.md").read_text(encoding="utf-8")
    admin_manual = (MANUALS / "manual-django-admin.md").read_text(encoding="utf-8")
    index = (MANUALS / "README.md").read_text(encoding="utf-8")

    assert "manual-django-admin.md" in portal
    assert "manual-portal-principal.md" in admin_manual
    assert "manual-portal-principal.md" in index
    assert "manual-django-admin.md" in index
    assert "CAPTURA" in portal
    assert "CAPTURA" in admin_manual
    assert "datos productivos" in admin_manual
