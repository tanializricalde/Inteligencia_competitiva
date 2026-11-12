"""Configurable, deterministic feature-equivalence engine."""

from data_transformation.feature_rules.contracts import (
    FeatureFlattenResult,
    FeatureRulesConfig,
    FeatureRulesConfigError,
    FeatureRulesExecutionError,
    FeatureRulesReport,
)
from data_transformation.feature_rules.engine import flatten_features
from data_transformation.feature_rules.loader import load_feature_rules, parse_feature_rules

__all__ = [
    "FeatureFlattenResult",
    "FeatureRulesConfig",
    "FeatureRulesConfigError",
    "FeatureRulesExecutionError",
    "FeatureRulesReport",
    "flatten_features",
    "load_feature_rules",
    "parse_feature_rules",
]
