import pytest
from django.contrib.auth.models import Permission
from django.core import mail
from django.urls import reverse

from apps.market.models import Provider
from apps.scraping.models import ScrapeSource


@pytest.fixture
def operator(django_user_model):
    return django_user_model.objects.create_user("operator@example.test", "password")


@pytest.fixture
def source(db):
    provider = Provider.objects.create(name="Provider", code="provider")
    return ScrapeSource.objects.create(
        provider=provider,
        name="Plans",
        target_url="https://example.test/plans",
        adapter_key="example_httpx",
    )


@pytest.mark.django_db
def test_source_toggle_is_hidden_even_with_legacy_permission(client, operator, source):
    client.force_login(operator)
    url = reverse("toggle_source", args=(source.id,))
    assert client.post(url).status_code == 404
    operator.user_permissions.add(Permission.objects.get(codename="change_scrapesource"))

    assert client.post(url).status_code == 404
    source.refresh_from_db()
    assert source.is_active


@pytest.mark.django_db
def test_email_configuration_is_permission_protected(client, operator):
    client.force_login(operator)
    url = reverse("test_email_configuration")
    assert client.post(url).status_code == 403
    operator.user_permissions.add(Permission.objects.get(codename="change_notificationrecipient"))

    assert client.post(url).status_code == 302
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [operator.email]
