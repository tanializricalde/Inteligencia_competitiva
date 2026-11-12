from django.db import models


class NotificationRecipient(models.Model):
    name = models.CharField(max_length=160)
    email = models.EmailField()
    is_active = models.BooleanField(default=True)
    notify_errors = models.BooleanField(default=True)
    notify_changes = models.BooleanField(default=True)
    notify_recovery = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=("email",), name="uq_notification_recipient_email")
        ]

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"


class NotificationOutbox(models.Model):
    class EventType(models.TextChoices):
        SCRAPE_FAILED = "SCRAPE_FAILED", "Scraping fallido"
        DATA_CHANGED = "DATA_CHANGED", "Datos modificados"
        SCRAPE_RECOVERED = "SCRAPE_RECOVERED", "Scraping recuperado"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        SENT = "sent", "Enviado"
        FAILED = "failed", "Fallido"

    event_type = models.CharField(max_length=32, choices=EventType.choices)
    recipients = models.JSONField(default=list)
    idempotency_key = models.CharField(max_length=160, unique=True)
    subject = models.CharField(max_length=255)
    context = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=("status", "created_at"), name="outbox_status_created")]

    def __str__(self) -> str:
        return f"{self.get_event_type_display()} · {self.subject or 'sin asunto'}"
