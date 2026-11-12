from datetime import time

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.market.models import Plan, Provider
from apps.notifications.models import NotificationRecipient
from apps.scraping.models import ScheduleConfig, ScrapeSource


@pytest.mark.django_db
def test_plan_key_is_unique_per_provider():
    provider = Provider.objects.create(name="Proveedor", code="provider")
    Plan.objects.create(provider=provider, stable_key="pro", name="Pro")

    with pytest.raises(IntegrityError), transaction.atomic():
        Plan.objects.create(provider=provider, stable_key="pro", name="Pro duplicado")


@pytest.mark.django_db
def test_source_adapter_is_controlled_choice():
    provider = Provider.objects.create(name="Proveedor", code="provider")
    source = ScrapeSource(
        provider=provider,
        name="Planes",
        target_url="https://example.test/plans",
        adapter_key="arbitrary.module.Class",
    )

    with pytest.raises(ValidationError):
        source.full_clean()


@pytest.mark.django_db
def test_schedule_rejects_invalid_timezone():
    config = ScheduleConfig(daily_time=time(7), timezone="Mars/Olympus")

    with pytest.raises(ValidationError):
        config.save()


@pytest.mark.django_db
def test_notification_recipient_email_is_unique():
    NotificationRecipient.objects.create(name="Ops", email="ops@example.test")

    with pytest.raises(IntegrityError), transaction.atomic():
        NotificationRecipient.objects.create(name="Other", email="ops@example.test")
