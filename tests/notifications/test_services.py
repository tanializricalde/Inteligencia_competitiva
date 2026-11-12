import pytest
from django.core import mail

from apps.market.models import DashboardSettings
from apps.notifications.models import NotificationOutbox
from apps.notifications.services import enqueue_notification, send_pending_notifications


@pytest.mark.django_db
def test_outbox_idempotency_and_multipart_email():
    branding = DashboardSettings.load()
    branding.application_name = "Radar de prueba"
    branding.save()
    first = enqueue_notification(
        NotificationOutbox.EventType.DATA_CHANGED,
        "event:1",
        "[TEST] Cambio",
        {"title": "Cambio", "summary": "Precio modificado"},
        ["ops@example.test"],
    )
    second = enqueue_notification(
        NotificationOutbox.EventType.DATA_CHANGED,
        "event:1",
        "ignored",
        {},
        ["ops@example.test"],
    )

    assert first.pk == second.pk
    assert first.subject == "[Radar de prueba] [TEST] Cambio"
    assert first.context["application_name"] == "Radar de prueba"
    assert send_pending_notifications() == 1
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "[Radar de prueba] [TEST] Cambio"
    assert mail.outbox[0].alternatives[0].mimetype == "text/html"
    assert "Radar de prueba" in mail.outbox[0].alternatives[0].content
