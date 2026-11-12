"""Shared contracts for the post-scraping tabular pipeline."""

from data_pipeline.detection import detect_dataset_type
from data_pipeline.errors import (
    DatasetDetectionError,
    DatasetIOError,
    PipelineIssue,
    PipelineValidationError,
)
from data_pipeline.policies import NumericPolicy, NumericStrategy, PolicyApplication
from data_pipeline.profiles import DatasetProfile, DatasetType, get_profile
from data_pipeline.reporting import QualityReport

__all__ = [
    "DatasetDetectionError",
    "DatasetIOError",
    "DatasetProfile",
    "DatasetType",
    "PipelineIssue",
    "PipelineValidationError",
    "NumericPolicy",
    "NumericStrategy",
    "PolicyApplication",
    "QualityReport",
    "detect_dataset_type",
    "get_profile",
]
