"""Export-time validation and actionable one-page-layout diagnostics."""

from __future__ import annotations

import os
import re
import string
from dataclasses import dataclass, field
from pathlib import Path

from .calculations import build_analytical_result
from .image_processing import ImageValidationError, validate_portable_image
from .instrument_metadata import identifier_warnings, instrument_display_rows
from .models import COAConfig


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    message: str


@dataclass
class ValidationReport:
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def raise_for_errors(self) -> None:
        if self.errors:
            details = "; ".join(f"{issue.field}: {issue.message}" for issue in self.errors)
            raise ValueError(details)


def resolve_watermark_text(config: COAConfig) -> str:
    watermark = config.document_protection.watermark
    values = {
        "client": config.client,
        "report_no": config.report_no,
        "sample_name": config.sample_name,
        "document_issue_date": config.document_issue_date.isoformat(),
    }
    try:
        # Formatter receives only the four validated literal values. No eval,
        # expressions, conversion attributes, or markup interpretation occurs.
        formatter = string.Formatter()
        pieces: list[str] = []
        for literal, field_name, format_spec, conversion in formatter.parse(watermark.text):
            pieces.append(literal)
            if field_name:
                if conversion or format_spec or "." in field_name or "[" in field_name:
                    raise ValueError("Watermark variables cannot use conversions, formats, or attribute access")
                pieces.append(values[field_name])
        return "".join(pieces)
    except KeyError as exc:
        raise ValueError(f"Missing watermark variable: {exc.args[0]}") from exc


def _font_supports_text(font_name: str, text: str) -> bool:
    if any(ord(character) < 32 and character not in "\t\n" for character in text):
        return False
    root = Path(__file__).resolve().parents[1]
    family = "DejaVuSerif.ttf" if font_name == "DejaVu Serif" else "DejaVuSans.ttf"
    font_path = root / "assets" / "fonts" / family
    if not font_path.exists():
        return all(ord(character) < 128 for character in text)
    try:
        from fontTools.ttLib import TTFont

        font = TTFont(font_path, lazy=True)
        cmap = set()
        for table in font["cmap"].tables:
            cmap.update(table.cmap.keys())
        font.close()
        return all(ord(character) in cmap or character in "\n\t" for character in text)
    except Exception:
        # DejaVu's broad Unicode coverage is used when fontTools is unavailable;
        # reject only control characters in that fallback.
        return True


def validate_for_export(config: COAConfig) -> ValidationReport:
    report = ValidationReport()
    try:
        result = build_analytical_result(config.analytical)
    except ValueError as exc:
        report.errors.append(ValidationIssue("analytical", str(exc)))
        result = None

    if result is not None:
        displayed = [
            peak for peak in result.peaks if peak.include_in_table
        ]
        if len(displayed) > config.template.max_displayed_peaks:
            report.errors.append(
                ValidationIssue(
                    "analytical.peaks",
                    f"{len(displayed)} peaks exceed the {config.template.max_displayed_peaks}-peak "
                    "limit for this one-page template; reduce the peak count or select a larger template.",
                )
            )

    assets = (
        ("branding.logo", config.branding.logo, config.branding.logo_use_authorized, "logo"),
        ("sample_image", config.sample_image, True, "sample"),
        (
            "approval.signature_image",
            config.approval.signature_image,
            config.approval.signature_image_use_authorized,
            "signature",
        ),
    )
    for field_name, image, authorized, purpose in assets:
        if image is None:
            continue
        if not authorized:
            report.errors.append(
                ValidationIssue(field_name, "Ownership or use authorization must be confirmed before preview or export")
            )
            continue
        try:
            validate_portable_image(image, purpose)  # type: ignore[arg-type]
        except ImageValidationError as exc:
            report.errors.append(ValidationIssue(field_name, str(exc)))

    mismatch_messages = identifier_warnings(config)
    for message in mismatch_messages:
        target = report.errors if config.strict_identifier_matching else report.warnings
        target.append(ValidationIssue("instrument_metadata", message))

    data_file = config.instrument_metadata.data_file
    if os.path.isabs(data_file) or re.match(r"^[A-Za-z]:[\\/]", data_file):
        report.errors.append(
            ValidationIssue("instrument_metadata.data_file", "Use a display filename, not an absolute filesystem path")
        )

    watermark = config.document_protection.watermark
    if watermark.enabled:
        try:
            resolved = resolve_watermark_text(config)
        except ValueError as exc:
            report.errors.append(ValidationIssue("document_protection.watermark.text", str(exc)))
        else:
            if not resolved.strip():
                report.errors.append(
                    ValidationIssue("document_protection.watermark.text", "Resolved watermark text cannot be blank")
                )
            elif not _font_supports_text(watermark.font, resolved):
                report.errors.append(
                    ValidationIssue(
                        "document_protection.watermark.font",
                        "The bundled font cannot render every resolved watermark character",
                    )
                )
            estimated_width = len(resolved) * watermark.size * 0.55
            maximum_width = 660 if watermark.repeat else 920
            if estimated_width > maximum_width:
                report.errors.append(
                    ValidationIssue(
                        "document_protection.watermark.text",
                        "Resolved watermark is too wide for the selected size and placement; "
                        "shorten the text or reduce its size.",
                    )
                )
        if watermark.repeat and (watermark.opacity > 0.16 or watermark.size > 38):
            report.errors.append(
                ValidationIssue(
                    "document_protection.watermark",
                    "Repeated watermark size or opacity would impair required-text legibility",
                )
            )

    instrument_rows = instrument_display_rows(config.instrument_metadata)
    visible_rows = [row for row in instrument_rows if row.value or config.template.preserve_blank_instrument_rows]
    if len(visible_rows) > 16:
        report.errors.append(
            ValidationIssue(
                "instrument_metadata.custom_rows",
                f"{len(visible_rows)} visible instrument rows exceed the 16-row one-page limit.",
            )
        )

    length_limits = {
        "client": (config.client, 92),
        "sample_name": (config.sample_name, 110),
        "branding.footer_disclaimer": (config.branding.footer_disclaimer, 620),
        "notes": (config.notes or "", 160),
        "result_note": (config.result_note or "", 180),
    }
    for field_name, (value, practical_limit) in length_limits.items():
        if len(value) > practical_limit:
            report.errors.append(
                ValidationIssue(
                    field_name,
                    f"Text is too long for the fixed one-page region ({len(value)} characters; "
                    f"tested limit {practical_limit}). Shorten this field before export.",
                )
            )

    result_context = " · ".join(
        value
        for value in (
            config.result_note or "",
            config.purity_basis_description or "",
            config.excluded_component_text or "",
            config.notes or "",
        )
        if value
    )
    if len(result_context) > 300:
        report.errors.append(
            ValidationIssue(
                "result_context",
                "Combined result note, basis, excluded-component text, and report notes exceed "
                "the tested two-line result region.",
            )
        )

    if config.sample_image and config.sample_image.caption and len(config.sample_image.caption) > 110:
        report.errors.append(
            ValidationIssue(
                "sample_image.caption",
                "Caption exceeds the tested two-line sample-image limit (110 characters)",
            )
        )

    existing_messages = {issue.message for issue in report.errors + report.warnings}
    for warning in config.preserved_warnings:
        if warning not in existing_messages:
            report.warnings.append(ValidationIssue("scenario", warning))
    return report
