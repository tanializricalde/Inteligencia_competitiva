import base64
import importlib

import pytest
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from playwright.sync_api import expect, sync_playwright

from apps.market.models import DashboardSettings

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.mark.playwright
@pytest.mark.django_db(transaction=True)
def test_sidebar_brand_is_responsive_and_preserves_expanded_name(
    live_server, django_user_model, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    user = django_user_model.objects.create_user("sidebar@example.test", "safe-test-password")
    branding = DashboardSettings.load()
    branding.application_name = "Observatorio competitivo regional de productos digitales"
    branding.application_logo = SimpleUploadedFile("sidebar.png", PNG_1X1, content_type="image/png")
    branding.application_logo_alt = "Logo del observatorio"
    branding.save()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(f"{live_server.url}/accounts/login/")
        page.locator('input[name="username"]').fill(user.email)
        page.locator('input[name="password"]').fill("safe-test-password")
        page.locator('button[type="submit"]').click()

        full_brand = page.locator(".sidebar-brand-full")
        assert full_brand.is_visible()
        assert full_brand.locator(".sidebar-brand-name").inner_text() == branding.application_name
        assert full_brand.locator("img").get_attribute("alt") == "Logo del observatorio"
        assert not page.locator(".sidebar-brand-short").is_visible()
        assert "Configuración de la aplicación" not in page.locator("body").inner_text()

        page.locator("[data-sidebar-toggle]").click()
        assert not full_brand.is_visible()
        assert page.locator(".sidebar-brand-short").is_visible()

        page.set_viewport_size({"width": 390, "height": 844})
        page.reload()
        assert not page.locator("#app-sidebar").is_visible()
        page.locator("[data-sidebar-toggle]").click()
        assert page.locator("#app-sidebar").is_visible()
        assert full_brand.is_visible()
        assert full_brand.locator(".sidebar-brand-name").inner_text() == branding.application_name
        browser.close()


@pytest.mark.playwright
@pytest.mark.django_db(transaction=True)
def test_feature_filter_supports_keyboard_focus_search_and_escape(live_server, django_user_model):
    importlib.import_module(
        "apps.market.migrations.0006_seed_dashboard_system_presets"
    ).seed_system_presets(apps, None)
    importlib.import_module("apps.market.migrations.0007_seed_dashboard_demo_data").seed_demo(
        apps, None
    )
    user = django_user_model.objects.create_user(
        "feature-keyboard@example.test", "safe-test-password"
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(f"{live_server.url}/accounts/login/")
        page.locator('input[name="username"]').fill(user.email)
        page.locator('input[name="password"]').fill("safe-test-password")
        page.locator('button[type="submit"]').click()
        page.goto(f"{live_server.url}/?preset=demo&period=6")

        summary = page.locator("[data-feature-filter] > summary")
        summary.focus()
        page.keyboard.press("Enter")
        search = page.locator("[data-feature-search]")
        expect(search).to_be_focused()
        search.fill("facturación")
        assert page.locator("[data-feature-option]:visible").count() >= 1
        page.keyboard.press("Escape")
        assert not page.locator("[data-feature-filter]").get_attribute("open")
        expect(summary).to_be_focused()
        browser.close()
