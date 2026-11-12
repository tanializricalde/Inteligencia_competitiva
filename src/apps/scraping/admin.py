from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import SchedulerHeartbeat


@admin.register(SchedulerHeartbeat)
class ScrapingModelAdmin(ModelAdmin):
    list_per_page = 30
