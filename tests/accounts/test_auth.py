import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from apps.accounts.signals import ensure_default_groups


@pytest.mark.django_db
def test_user_logs_in_with_case_insensitive_email(client):
    get_user_model().objects.create_user("analista@example.test", "safe-test-password")

    response = client.post(
        reverse("login"),
        {"username": "Analista@Example.Test", "password": "safe-test-password"},
    )

    assert response.status_code == 302
    assert response.url == reverse("dashboard")


@pytest.mark.django_db
def test_logout_requires_post(client):
    user = get_user_model().objects.create_user("user@example.test", "safe-test-password")
    client.force_login(user)

    assert client.get(reverse("logout")).status_code == 405
    assert client.post(reverse("logout")).status_code == 302


@pytest.mark.django_db
def test_login_error_does_not_disclose_account(client):
    response = client.post(
        reverse("login"), {"username": "missing@example.test", "password": "wrong"}
    )

    assert response.status_code == 200
    assert "No fue posible iniciar sesión" in response.content.decode()


@pytest.mark.django_db
def test_operator_group_excludes_hidden_legacy_ingestion_permissions():
    ensure_default_groups()

    codenames = set(
        Group.objects.get(name="Operador").permissions.values_list("codename", flat=True)
    )

    assert {"add_pipelinerun", "view_pipelinerun", "view_marketsource"} <= codenames
    assert not {"run_scrape", "run_reviews", "view_scrapesource", "view_reviewsource"} & codenames
