class ScrapeError(Exception):
    error_type = "scrape_error"


class TransportError(ScrapeError):
    error_type = "transport"


class HttpResponseError(ScrapeError):
    error_type = "http_response"


class ScrapeTimeoutError(ScrapeError):
    error_type = "timeout"


class StructureChangedError(ScrapeError):
    error_type = "structure_changed"


class NormalizationError(ScrapeError):
    error_type = "normalization"


class AccessBlockedError(ScrapeError):
    error_type = "access_blocked"


class SuspiciousEmptyResultError(ScrapeError):
    error_type = "suspicious_empty_result"


class ResponseTooLargeError(ScrapeError):
    error_type = "response_too_large"


class UnsafeSourceUrlError(ScrapeError):
    error_type = "unsafe_source_url"


class ReviewScrapeError(Exception):
    error_type = "review_scrape_error"


class ReviewConfigurationError(ReviewScrapeError):
    error_type = "review_configuration"


class ReviewTransportError(ReviewScrapeError):
    error_type = "review_transport"


class ReviewStructureChangedError(ReviewScrapeError):
    error_type = "review_structure_changed"


class ReviewValidationError(ReviewScrapeError):
    error_type = "review_validation"


class ReviewSourceBusyError(ReviewScrapeError):
    error_type = "review_source_busy"
