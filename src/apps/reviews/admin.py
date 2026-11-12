from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import (
    MarketReview,
    ReviewEnrichment,
    ReviewObservation,
)


@admin.register(MarketReview)
class MarketReviewAdmin(ModelAdmin):
    list_display = ("review_id", "source", "last_seen_at", "is_visible")
    list_filter = ("source__platform", "is_visible")
    search_fields = ("review_id", "external_review_id", "source__provider__code")
    list_select_related = ("source", "source__provider")


@admin.register(ReviewObservation)
class ReviewObservationAdmin(ModelAdmin):
    list_display = ("review", "published_at", "rating", "helpful_votes", "observed_at")
    list_filter = ("rating", "response_known")
    search_fields = ("review__review_id", "author_name", "review_text")
    list_select_related = ("review", "review__source", "review__source__provider", "run")


@admin.register(ReviewEnrichment)
class ReviewEnrichmentAdmin(ModelAdmin):
    list_display = ("observation", "status", "category", "sentiment", "analyzer_version")
    list_filter = ("status", "sentiment", "analyzer", "analyzer_version")
    search_fields = ("observation__review__review_id", "category")
    list_select_related = ("observation", "observation__review")
