from pathlib import Path

import pytest
from django.urls import reverse

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.django_db
def test_login_uses_shared_controls_and_theme_toggle(client):
    response = client.get(reverse("login"))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'class="form-control"' in content
    assert 'class="btn btn-primary w-100"' in content
    assert "data-theme-toggle" in content


@pytest.mark.django_db
def test_password_reset_uses_shared_controls(client):
    response = client.get(reverse("password_reset"))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'class="stacked-form"' in content
    assert 'class="form-control"' in content
    assert 'class="btn btn-primary w-100"' in content


@pytest.mark.django_db
def test_staff_can_return_to_admin_from_site(client, django_user_model):
    user = django_user_model.objects.create_superuser(
        "admin@example.test", "safe-test-password"
    )
    client.force_login(user)

    response = client.get(reverse("dashboard"))
    content = response.content.decode()

    assert response.status_code == 200
    assert f'href="{reverse("admin:index")}"' in content
    assert "Volver a administración" in content
    assert "data-theme-toggle" in content


@pytest.mark.django_db
def test_generated_settings_forms_use_shared_controls(client, django_user_model):
    user = django_user_model.objects.create_superuser(
        "admin@example.test", "safe-test-password"
    )
    client.force_login(user)

    response = client.get(reverse("functional_settings"))
    content = response.content.decode()

    assert response.status_code == 200
    assert content.count('class="stacked-form"') == 1
    assert 'class="form-control"' in content
    assert 'class="form-check-input"' in content


def test_sidebar_styles_preserve_expanded_mobile_name_and_collapsed_icon():
    styles = (ROOT / "frontend/src/app.scss").read_text(encoding="utf-8")

    assert ".sidebar-brand-full { display: flex;" in styles
    assert ".sidebar-brand-name { min-width: 0; white-space: normal;" in styles
    assert (
        ".sidebar-collapsed .sidebar-label, .sidebar-collapsed .sidebar-brand-full "
        "{ display: none; }"
        in styles
    )
    assert ".app-shell.sidebar-collapsed .sidebar-brand-full { display: flex; }" in styles
    assert ".sidebar-collapsed .sidebar-brand-short { display: inline; }" in styles
