import logging
from collections.abc import Iterable

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import NotificationOutbox, NotificationRecipient

logger = logging.getLogger(__name__)


def recipient_emails(event_type: str) -> list[str]:
    field_by_event = {
        NotificationOutbox.EventType.SCRAPE_FAILED: "notify_errors",
        NotificationOutbox.EventType.DATA_CHANGED: "notify_changes",
        NotificationOutbox.EventType.SCRAPE_RECOVERED: "notify_recovery",
    }
    field = field_by_event[event_type]
    return list(
        NotificationRecipient.objects.filter(is_active=True, **{field: True}).values_list(
            "email", flat=True
        )
    )


def enqueue_notification(
    event_type: str,
    idempotency_key: str,
    subject: str,
    context: dict,
    recipients: Iterable[str] | None = None,
) -> NotificationOutbox | None:
    from apps.market.branding import get_application_branding

    addresses = sorted(set(recipients if recipients is not None else recipient_emails(event_type)))
    if not addresses:
        return None
    application_name = get_application_branding().application_name
    notification, _ = NotificationOutbox.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "event_type": event_type,
            "recipients": addresses,
            "subject": f"[{application_name}] {subject}",
            "context": {**context, "application_name": application_name},
        },
    )
    return notification


def send_pending_notifications(limit: int = 20) -> int:
    from apps.market.branding import get_application_branding

    sent = 0
    pending = NotificationOutbox.objects.filter(
        status__in=(NotificationOutbox.Status.PENDING, NotificationOutbox.Status.FAILED)
    ).order_by("created_at")[:limit]
    for notification in pending:
        notification.attempts += 1
        try:
            context = {
                "application_name": get_application_branding().application_name,
                **notification.context,
                "app_base_url": settings.APP_BASE_URL,
            }
            text = render_to_string("notifications/event.txt", context)
            html = render_to_string("notifications/event.html", context)
            message = EmailMultiAlternatives(
                notification.subject,
                text,
                settings.DEFAULT_FROM_EMAIL,
                notification.recipients,
            )
            message.attach_alternative(html, "text/html")
            message.send(fail_silently=False)
        except Exception as exc:  # boundary: email backends raise heterogeneous errors
            logger.warning("notification_send_failed id=%s", notification.id)
            notification.status = NotificationOutbox.Status.FAILED
            notification.last_error = type(exc).__name__[:500]
            notification.save(update_fields=("attempts", "status", "last_error"))
            continue
        notification.status = NotificationOutbox.Status.SENT
        notification.sent_at = timezone.now()
        notification.last_error = ""
        notification.save(update_fields=("attempts", "status", "sent_at", "last_error"))
        sent += 1
    return sent
