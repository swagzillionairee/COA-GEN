"""Application-wide constants and release identifiers."""

from __future__ import annotations

APP_NAME = "COA Generator"
APP_VERSION = "0.3.0"
SCHEMA_VERSION = "1.1"
TEMPLATE_VERSION = "1.0.0"
CALCULATION_MODEL_VERSION = "1.0.0"
BUILD_IDENTIFIER = "source-2026-07-21-web-r1"

RESULT_STATUS_NOTICE = (
    "Software-generated COA - verify results against original instrument source data."
)

# Backwards-compatible import aliases for older integrations.
PROVENANCE_NOTICE = RESULT_STATUS_NOTICE
DEVELOPMENT_NOTICE = RESULT_STATUS_NOTICE

MAX_ORIGINAL_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PROCESSED_IMAGE_BYTES = 1 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_BATCH_SIZE = 100
MAX_WATERMARK_LENGTH = 200
ALLOWED_WATERMARK_VARIABLES = {
    "client",
    "report_no",
    "sample_name",
    "document_issue_date",
}
