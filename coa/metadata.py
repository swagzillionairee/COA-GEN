"""Report-specific metadata and generation identifiers."""

from __future__ import annotations

import uuid

from .constants import APP_NAME, RESULT_STATUS_NOTICE
from .models import COAConfig


def new_generation_identifier() -> str:
    return f"COA-{uuid.uuid4().hex[:16].upper()}"


def config_for_export(config: COAConfig, generation_identifier: str | None = None) -> COAConfig:
    updated = config.model_copy(deep=True)
    updated.audit.generation_identifier = generation_identifier or new_generation_identifier()
    if not updated.strict_identifier_matching:
        from .instrument_metadata import identifier_warnings

        updated.preserved_warnings = identifier_warnings(updated)
    return updated


def pdf_metadata(config: COAConfig) -> dict[str, str]:
    generation_id = config.audit.generation_identifier or new_generation_identifier()
    title = f"Certificate of Analysis {config.report_no}"
    return {
        "title": title,
        "author": config.branding.organization_display_name,
        "subject": RESULT_STATUS_NOTICE,
        "keywords": f"certificate of analysis, software-generated, {RESULT_STATUS_NOTICE}",
        "creator": f"{APP_NAME} {config.audit.application_version}",
        "generation_identifier": generation_id,
    }
