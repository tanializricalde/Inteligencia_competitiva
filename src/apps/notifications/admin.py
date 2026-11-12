from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import NotificationOutbox, NotificationRecipient


@admin.register(NotificationRecipient, NotificationOutbox)
class NotificationModelAdmin(ModelAdmin):
    list_per_page = 30
