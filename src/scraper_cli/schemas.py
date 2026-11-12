"""Backward-compatible imports for shared public scraping schemas."""

from data_pipeline.scraping_schemas import (
    PLAN_FEATURE_FIELDS,
    PLAN_FEATURES_SCHEMA,
    PLAN_FIELDS,
    PLANS_SCHEMA,
    REVIEW_FIELDS,
    REVIEWS_SCHEMA,
    map_plan,
    map_review,
)

__all__ = [
    "PLAN_FEATURE_FIELDS",
    "PLAN_FEATURES_SCHEMA",
    "PLAN_FIELDS",
    "PLANS_SCHEMA",
    "REVIEW_FIELDS",
    "REVIEWS_SCHEMA",
    "map_plan",
    "map_review",
]
