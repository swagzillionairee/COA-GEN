"""Validated scenario and shared result models.

Passwords are deliberately absent from every serializable model. They are
accepted only by the transient protected-export function.
"""

from __future__ import annotations

import base64
import hashlib
import math
import re
import string
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .constants import (
    ALLOWED_WATERMARK_VARIABLES,
    APP_VERSION,
    BUILD_IDENTIFIER,
    CALCULATION_MODEL_VERSION,
    MAX_PROCESSED_IMAGE_BYTES,
    MAX_WATERMARK_LENGTH,
    SCHEMA_VERSION,
    TEMPLATE_VERSION,
)


HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class StrictModel(BaseModel):
    """Base model with a documented reject-unknown-fields policy."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class PortableImage(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    content_base64: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    caption: str | None = Field(default=None, max_length=240)
    crop_position: Literal["center", "top", "bottom", "left", "right"] = "center"

    @model_validator(mode="after")
    def validate_embedded_content(self) -> "PortableImage":
        try:
            payload = base64.b64decode(self.content_base64, validate=True)
        except Exception as exc:
            raise ValueError("Embedded image content is not valid base64") from exc
        if len(payload) > MAX_PROCESSED_IMAGE_BYTES:
            raise ValueError("Processed image exceeds the 1 MB portable-scenario limit")
        if hashlib.sha256(payload).hexdigest() != self.sha256:
            raise ValueError("Embedded image hash does not match its content")
        if self.width * self.height > 20_000_000:
            raise ValueError("Embedded image exceeds the 20 megapixel limit")
        return self

    def bytes(self) -> bytes:
        return base64.b64decode(self.content_base64, validate=True)


class BrandingSettings(StrictModel):
    organization_display_name: str = Field(default="Northstar Analytical", min_length=1, max_length=120)
    address: str = Field(default="100 Fictional Way, Raleigh, NC 27601", max_length=240)
    website: str = Field(default="https://example.invalid", max_length=240)
    phone: str = Field(default="+1 (555) 010-2026", max_length=80)
    email: str = Field(default="reports@example.invalid", max_length=160)
    primary_color: str = "#173F4F"
    accent_color: str = "#D8A43B"
    title_color: str = "#173F4F"
    purity_highlight_color: str = "#F6E7A5"
    trace_color: str = "#153B50"
    peak_fill_color: str = "#7FB3C8"
    title_font: Literal["DejaVu Serif", "DejaVu Sans"] = "DejaVu Serif"
    body_font: Literal["DejaVu Sans", "DejaVu Serif"] = "DejaVu Serif"
    table_font: Literal["DejaVu Sans", "DejaVu Serif"] = "DejaVu Serif"
    certificate_underline: Literal["none", "single", "double"] = "single"
    footer_disclaimer: str = Field(
        default=(
            "This report applies only to the identified sample. Interpretation and use of the "
            "results remain the responsibility of the client. Reproduce only in full."
        ),
        min_length=1,
        max_length=900,
    )
    quality_statement: str | None = Field(
        default=None,
        max_length=300,
    )
    logo: PortableImage | None = None
    logo_use_authorized: bool = False

    @field_validator(
        "primary_color",
        "accent_color",
        "title_color",
        "purity_highlight_color",
        "trace_color",
        "peak_fill_color",
    )
    @classmethod
    def validate_colors(cls, value: str) -> str:
        if not HEX_COLOR_RE.fullmatch(value):
            raise ValueError("Colors must use #RRGGBB form")
        return value.upper()


class TemplateSettings(StrictModel):
    preset: Literal["Reference COA", "Reference COA with Sample Image"] = "Reference COA"
    header_date_format: Literal["%b. %d, %Y", "%B %d, %Y", "%m/%d/%Y"] = "%b. %d, %Y"
    body_date_format: Literal["%m/%d/%Y", "%Y-%m-%d", "%b %d, %Y"] = "%m/%d/%Y"
    sample_label: str = Field(default="Sample Name:", min_length=1, max_length=32)
    batch_label: str = Field(default="Lot #:", min_length=1, max_length=24)
    page_number_format: Literal["1", "1 of 1"] = "1 of 1"
    append_strength_to_sample: bool = True
    preserve_blank_instrument_rows: bool = False
    max_displayed_peaks: int = Field(default=8, ge=1, le=12)
    result_text_min_pt: float = Field(default=10.0, ge=9.0, le=14.0)
    metadata_text_min_pt: float = Field(default=7.2, ge=6.8, le=9.0)
    footer_text_min_pt: float = Field(default=6.2, ge=6.0, le=8.0)


class CustomMetadataRow(StrictModel):
    label: str = Field(min_length=1, max_length=80)
    value: str = Field(default="", max_length=300)
    visible: bool = True


class InstrumentMetadata(StrictModel):
    data_file: str = Field(
        default="260604_RETATRUTIDE_001_PURITY.d",
        min_length=1,
        max_length=160,
    )
    instrument_sample_name: str = Field(
        default="RETATRUTIDE_001_PURITY", min_length=1, max_length=160
    )
    sample_type: str = Field(default="Sample", max_length=80)
    instrument: str = Field(default="Instrument 2", max_length=160)
    position: str = Field(default="P1-B2", max_length=80)
    acquisition_method: str = Field(default="Purity Method 1", max_length=160)
    analysis_method: str = Field(default="Area Percent Review 1", max_length=160)
    calibration_status: str = Field(default="Not Applicable", max_length=200)
    operator: str = Field(default="Analytical User", max_length=160)
    acquired_at: datetime = datetime.fromisoformat("2026-06-04T15:26:57-04:00")
    sample_group: str = Field(default="Samples", max_length=160)
    stream_name: str = Field(default="LC 1", max_length=80)
    software_version: str = Field(default="6400 Series Triple B.09.00", max_length=120)
    comment: str | None = Field(default=None, max_length=240)
    information: str | None = Field(default=None, max_length=240)
    custom_rows: list[CustomMetadataRow] = Field(default_factory=list, max_length=8)

    @field_validator("acquired_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Acquisition timestamp must include a UTC offset")
        return value


class DetectorSettings(StrictModel):
    trace_name: str = Field(default="DAD1", min_length=1, max_length=40)
    channel: str = Field(default="A", max_length=40)
    signal_wavelength_nm: int = Field(default=254, ge=100, le=2000)
    signal_bandwidth_nm: int = Field(default=4, ge=0, le=1000)
    reference_enabled: bool = True
    reference_wavelength_nm: int | None = Field(default=400, ge=100, le=2000)
    reference_bandwidth_nm: int | None = Field(default=100, ge=0, le=1000)
    processing_label: str | None = Field(default="Subtract", max_length=80)

    @model_validator(mode="after")
    def validate_reference(self) -> "DetectorSettings":
        if self.reference_enabled and (
            self.reference_wavelength_nm is None or self.reference_bandwidth_nm is None
        ):
            raise ValueError("Reference wavelength and bandwidth are required when reference is enabled")
        return self


class ManualPeak(StrictModel):
    retention_time: float = Field(ge=0)
    area: float = Field(ge=0)
    width: float = Field(default=0.045, gt=0, le=2)
    tailing: float = Field(default=0.0, ge=0, le=5)
    is_main: bool = False
    include_in_table: bool = True
    annotate: bool = True
    annotation_prefix: str = Field(default="", max_length=8)
    marker: str | None = Field(default=None, max_length=4)

    @field_validator("retention_time", "area", "width", "tailing")
    @classmethod
    def require_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Peak values must be finite")
        return value


class AnalyticalSettings(StrictModel):
    purity_percent: float = Field(default=99.6, ge=0, le=100)
    purity_display_decimals: int = Field(default=1, ge=0, le=3)
    retention_time_start: float = Field(default=0.0, ge=0)
    retention_time_end: float = Field(default=5.0, gt=0)
    retention_time_decimals: int = Field(default=3, ge=1, le=5)
    main_peak_time: float = Field(default=2.061, ge=0)
    secondary_peak_times: list[float] = Field(default_factory=lambda: [0.908], max_length=11)
    secondary_peak_percent_areas: list[float] | None = None
    default_peak_width: float = Field(default=0.045, gt=0, le=2)
    tailing: float = Field(default=0.0, ge=0, le=5)
    baseline_noise: float = Field(default=0.003, ge=0, le=0.25)
    baseline_level: float = Field(default=0.0, ge=-1, le=1)
    baseline_drift: float = Field(default=0.0, ge=-0.25, le=0.25)
    injection_disturbance: bool = True
    injection_disturbance_amplitude: float = Field(default=0.05, ge=-1, le=1)
    absolute_area_scale: float = Field(default=1_000_000.0, gt=0)
    random_seed: int = Field(default=42017, ge=0, le=2_147_483_647)
    chart_label_threshold_percent: float = Field(default=0.25, ge=0, le=100)
    percent_area_decimals: int = Field(default=2, ge=1, le=4)
    raw_area_decimals: int = Field(default=2, ge=0, le=6)
    manual_peaks: list[ManualPeak] = Field(default_factory=list, max_length=12)

    @field_validator(
        "purity_percent",
        "retention_time_start",
        "retention_time_end",
        "main_peak_time",
        "default_peak_width",
        "tailing",
        "baseline_noise",
        "baseline_level",
        "baseline_drift",
        "injection_disturbance_amplitude",
        "absolute_area_scale",
        "chart_label_threshold_percent",
    )
    @classmethod
    def finite_numbers(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Analytical values must be finite")
        return value

    @model_validator(mode="after")
    def validate_peak_inputs(self) -> "AnalyticalSettings":
        if self.retention_time_end <= self.retention_time_start:
            raise ValueError("Retention-time end must be greater than start")
        if not self.retention_time_start <= self.main_peak_time <= self.retention_time_end:
            raise ValueError("Main peak must fall within the retention-time range")

        if self.manual_peaks:
            if len([p for p in self.manual_peaks if p.is_main]) != 1:
                raise ValueError("Manual peak mode requires exactly one main peak")
            times = [p.retention_time for p in self.manual_peaks]
            if any(not self.retention_time_start <= t <= self.retention_time_end for t in times):
                raise ValueError("All manual peaks must fall within the retention-time range")
            if sum(p.area for p in self.manual_peaks if p.include_in_table) <= 0:
                raise ValueError("Included manual peak area total must be greater than zero")
        else:
            times = [self.main_peak_time, *self.secondary_peak_times]
            if any(not self.retention_time_start <= t <= self.retention_time_end for t in times):
                raise ValueError("All peak times must fall within the retention-time range")
            if self.purity_percent == 0 and not self.secondary_peak_times:
                raise ValueError("A 0% main peak requires at least one secondary analytical peak")
            if self.secondary_peak_percent_areas is not None:
                if len(self.secondary_peak_percent_areas) != len(self.secondary_peak_times):
                    raise ValueError("Secondary percent areas must match secondary peak times")
                if any((not math.isfinite(v) or v < 0) for v in self.secondary_peak_percent_areas):
                    raise ValueError("Secondary percent areas must be finite and nonnegative")
                expected = 100.0 - self.purity_percent
                if abs(sum(self.secondary_peak_percent_areas) - expected) > 1e-6:
                    raise ValueError("Secondary percent areas must total 100 minus the requested purity")

        rounded = [round(t, self.retention_time_decimals + 2) for t in times]
        if len(rounded) != len(set(rounded)):
            raise ValueError("Analytical retention times must be unique at stored precision")
        return self


class ChromatogramSettings(StrictModel):
    show_peak_fill: bool = True
    show_detector_descriptor: bool = True
    show_processing_label: bool = True
    y_axis_mode: Literal["auto", "fixed"] = "auto"
    y_axis_min: float | None = None
    y_axis_max: float | None = None
    y_axis_scale_multiplier: float | None = Field(default=None, gt=0)
    x_major_tick_interval: float = Field(default=1.0, gt=0, le=10)
    response_units: str = Field(default="Response units", min_length=1, max_length=60)
    dpi: int = Field(default=220, ge=150, le=400)

    @model_validator(mode="after")
    def validate_fixed_range(self) -> "ChromatogramSettings":
        if self.y_axis_mode == "fixed":
            if self.y_axis_min is None or self.y_axis_max is None:
                raise ValueError("Fixed y-axis mode requires minimum and maximum")
            if self.y_axis_max <= self.y_axis_min:
                raise ValueError("Fixed y-axis maximum must exceed minimum")
        return self


class ApprovalSettings(StrictModel):
    heading: str = Field(default="Reviewed and Approved By:", min_length=1, max_length=100)
    approver: str = Field(default="Analytical Reviewer", min_length=1, max_length=120)
    approver_title: str = Field(default="Quality Review", min_length=1, max_length=120)
    approval_date: date = date(2026, 6, 4)
    approval_mark: str = Field(default="REVIEWED", max_length=80)
    show_rule: bool = True
    signature_image: PortableImage | None = None
    signature_image_use_authorized: bool = False


class WatermarkSettings(StrictModel):
    enabled: bool = False
    text: str = Field(default="CONFIDENTIAL - {client} - {report_no}", max_length=MAX_WATERMARK_LENGTH)
    font: Literal["DejaVu Sans", "DejaVu Serif"] = "DejaVu Sans"
    size: float = Field(default=30, ge=14, le=54)
    color: str = "#64748B"
    opacity: float = Field(default=0.12, ge=0.05, le=0.22)
    rotation_degrees: float = Field(default=35, ge=-60, le=60)
    placement: Literal["center", "upper", "lower"] = "center"
    repeat: bool = False

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        if not HEX_COLOR_RE.fullmatch(value):
            raise ValueError("Watermark color must use #RRGGBB form")
        return value.upper()

    @model_validator(mode="after")
    def validate_template_variables(self) -> "WatermarkSettings":
        formatter = string.Formatter()
        try:
            variables = {name for _, name, _, _ in formatter.parse(self.text) if name}
        except ValueError as exc:
            raise ValueError("Watermark template contains unmatched braces") from exc
        unknown = variables - ALLOWED_WATERMARK_VARIABLES
        if unknown:
            raise ValueError(f"Unsupported watermark variables: {', '.join(sorted(unknown))}")
        return self


class EditingRestrictionSettings(StrictModel):
    enabled: bool = False
    allow_document_changes: bool = False
    allow_annotations: bool = False
    allow_form_filling: bool = False
    allow_page_assembly: bool = False
    allow_printing: bool = True
    allow_copying: bool = False
    allow_accessibility: Literal[True] = True
    password_source: Literal["prompt_on_export"] = "prompt_on_export"


class DocumentProtection(StrictModel):
    watermark: WatermarkSettings = Field(default_factory=WatermarkSettings)
    editing_restriction: EditingRestrictionSettings = Field(default_factory=EditingRestrictionSettings)


class ExportAudit(StrictModel):
    application_version: str = APP_VERSION
    build_identifier: str = BUILD_IDENTIFIER
    template_version: str = TEMPLATE_VERSION
    calculation_model_version: str = CALCULATION_MODEL_VERSION
    generation_identifier: str | None = None


class COAConfig(StrictModel):
    schema_version: Literal["1.1"] = SCHEMA_VERSION
    report_no: str = Field(default="2026-000042", min_length=1, max_length=80)
    client: str = Field(default="Vitum Lab", min_length=1, max_length=160)
    sample_name: str = Field(default="Retatrutide", min_length=1, max_length=180)
    strength_or_presentation: str | None = Field(default="20 mg", max_length=80)
    batch_no: str | None = Field(default="001", max_length=100)
    receipt_date: date = date(2026, 6, 4)
    analysis_date: date = date(2026, 6, 4)
    report_date: date = date(2026, 6, 4)
    document_issue_date: date = date(2026, 6, 4)
    test: str = Field(default="Purity", min_length=1, max_length=120)
    matrix: str = Field(default="Lyophilized Powder", min_length=1, max_length=120)
    number_of_samples: int = Field(default=1, ge=1, le=10_000)
    notes: str | None = Field(default=None, max_length=600)
    purity_qualifier: str | None = Field(default=None, max_length=80)
    result_note: str | None = Field(
        default="Purity is calculated by area percent.",
        max_length=400,
    )
    result_note_marker: str | None = Field(default="*", max_length=4)
    purity_basis_description: str | None = Field(default="Area percent", max_length=160)
    excluded_component_text: str | None = Field(default=None, max_length=240)
    branding: BrandingSettings = Field(default_factory=BrandingSettings)
    template: TemplateSettings = Field(default_factory=TemplateSettings)
    sample_image: PortableImage | None = None
    analytical: AnalyticalSettings = Field(default_factory=AnalyticalSettings)
    instrument_metadata: InstrumentMetadata = Field(default_factory=InstrumentMetadata)
    detector: DetectorSettings = Field(default_factory=DetectorSettings)
    chromatogram: ChromatogramSettings = Field(default_factory=ChromatogramSettings)
    approval: ApprovalSettings = Field(default_factory=ApprovalSettings)
    document_protection: DocumentProtection = Field(default_factory=DocumentProtection)
    audit: ExportAudit = Field(default_factory=ExportAudit)
    strict_identifier_matching: bool = False
    preserved_warnings: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_dates_and_preset(self) -> "COAConfig":
        if not (
            self.receipt_date
            <= self.analysis_date
            <= self.report_date
            <= self.document_issue_date
        ):
            raise ValueError(
                "Dates must satisfy receipt_date <= analysis_date <= report_date <= document_issue_date"
            )
        if self.template.preset == "Reference COA with Sample Image" and self.sample_image is None:
            raise ValueError("The sample-image preset requires a submitted-sample image")
        if self.result_note and not self.result_note_marker:
            raise ValueError("A result-note marker is required when a result note is present")
        if self.result_note_marker and not self.result_note:
            raise ValueError("A result note is required when a result-note marker is present")
        return self


class PeakResult(StrictModel):
    retention_time: float
    area: float
    unrounded_percent_area: float
    displayed_percent_area: str
    width: float
    tailing: float
    is_main: bool
    include_in_table: bool
    annotate: bool
    annotation_prefix: str = ""
    marker: str | None = None


class AnalyticalResult(StrictModel):
    peaks: list[PeakResult]
    purity_percent_unrounded: float
    purity_display: str
    included_area_total: float
    random_seed: int

    @model_validator(mode="after")
    def validate_shared_result(self) -> "AnalyticalResult":
        if len([p for p in self.peaks if p.is_main]) != 1:
            raise ValueError("A shared result must contain exactly one main peak")
        if self.included_area_total <= 0:
            raise ValueError("Included peak area total must be greater than zero")
        total = sum(p.unrounded_percent_area for p in self.peaks if p.include_in_table)
        if abs(total - 100.0) > 0.000001:
            raise ValueError("Unrounded included percent areas must total 100%")
        return self
