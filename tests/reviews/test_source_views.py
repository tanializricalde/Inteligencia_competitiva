import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse


@pytest.mark.django_db
def test_legacy_source_and_run_views_are_hidden(client, django_user_model, sources):
    user = django_user_model.objects.create_user("review-ops@example.test", "password")
    user.user_permissions.add(
        Permission.objects.get(codename="view_reviewsource"),
        Permission.objects.get(codename="view_reviewrun"),
    )
    client.force_login(user)

    assert client.get(reverse("reviews:sources")).status_code == 404
    assert client.get(reverse("reviews:runs")).status_code == 404


@pytest.mark.django_db
def test_source_creation_is_hidden(client, django_user_model):
    user = django_user_model.objects.create_user("reader2@example.test", "password")
    client.force_login(user)
    assert client.get(reverse("reviews:source_create")).status_code == 404
