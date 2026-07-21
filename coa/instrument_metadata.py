"""Instrument-display helpers and canonical identifier linkage checks."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

from .models import COAConfig, InstrumentMetadata


def _token(value: str | None, fallback: str = "NA") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value or "").strip("_").upper()
    return cleaned or fallback


def _sample_token(value: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", value.upper())
    ignored = {"DEVELOPMENT", "SAMPLE", "DEMO", "TEST"}
    retained = [token for token in tokens if token not in ignored]
    return "_".join(retained) or "SAMPLE"


def _batch_token(value: str | None) -> str:
    without_prefix = re.sub(r"^BETA[\s_-]*", "", value or "", flags=re.IGNORECASE)
    return re.sub(r"[^A-Za-z0-9]+", "", without_prefix).upper() or "NA"


def derive_instrument_sample_identifier(sample_name: str, batch_no: str | None, test: str) -> str:
    return "_".join((_sample_token(sample_name), _batch_token(batch_no), _token(test)))[:160]


def derive_data_file_name(
    sample_name: str,
    batch_no: str | None,
    analysis_date: date,
    test: str,
) -> str:
    core = derive_instrument_sample_identifier(sample_name, batch_no, test)
    return f"{analysis_date:%y%m%d}_{core}.d"[:160]


def randomized_acquisition_time(
    analysis_date: date,
    timezone_info: tzinfo,
    *,
    offset_seconds: int | None = None,
) -> datetime:
    """Return a stable-in-config random local time from 1:00 PM through 5:00 PM."""

    span_seconds = 4 * 60 * 60
    offset = secrets.randbelow(span_seconds + 1) if offset_seconds is None else offset_seconds
    if not 0 <= offset <= span_seconds:
        raise ValueError("Acquisition-time offset must be between 0 and four hours")
    start = datetime.combine(analysis_date, time(13, 0), tzinfo=timezone_info)
    return start + timedelta(seconds=offset)


def identifier_warnings(config: COAConfig) -> list[str]:
    expected_sample = derive_instrument_sample_identifier(
        config.sample_name, config.batch_no, config.test
    )
    expected_file = derive_data_file_name(
        config.sample_name, config.batch_no, config.analysis_date, config.test
    )
    warnings: list[str] = []
    if config.instrument_metadata.instrument_sample_name != expected_sample:
        warnings.append(
            "Instrument sample identifier differs from the deterministic canonical value "
            f"({expected_sample})."
        )
    if config.instrument_metadata.data_file != expected_file:
        warnings.append(
            "Data-file display name differs from the deterministic canonical value "
            f"({expected_file})."
        )
    return warnings


def format_acquisition_time(value: datetime) -> str:
    return value.strftime("%m/%d/%Y %I:%M:%S %p UTC%z")[:-2] + ":" + value.strftime("%z")[-2:]


@dataclass(frozen=True)
class DisplayRow:
    label: str
    value: str


def instrument_display_rows(metadata: InstrumentMetadata) -> list[DisplayRow]:
    left, right = instrument_display_columns(metadata)
    return [*left, *right]


def instrument_display_columns(
    metadata: InstrumentMetadata,
) -> tuple[list[DisplayRow], list[DisplayRow]]:
    acquired = format_acquisition_time(metadata.acquired_at)
    left_rows = [
        DisplayRow("Data File", metadata.data_file),
        DisplayRow("Sample Type", metadata.sample_type),
        DisplayRow("Instrument Name", metadata.instrument),
        DisplayRow("Acq. Method", metadata.acquisition_method),
        DisplayRow("IRM Calibration Status", metadata.calibration_status),
        DisplayRow("Comment", metadata.comment or ""),
        DisplayRow("Sample Group", metadata.sample_group),
        DisplayRow("Stream Name", metadata.stream_name),
        DisplayRow("Acquisition SW Version", metadata.software_version),
    ]
    right_rows = [
        DisplayRow("Sample Name", metadata.instrument_sample_name),
        DisplayRow("Position", metadata.position),
        DisplayRow("User Name", metadata.operator),
        DisplayRow("Acquired Time", acquired),
        DisplayRow("DA Method", metadata.analysis_method),
        DisplayRow("Info.", metadata.information or ""),
        DisplayRow("Acquisition Time (Local)", acquired),
    ]
    right_rows.extend(
        DisplayRow(row.label, row.value) for row in metadata.custom_rows if row.visible
    )
    return left_rows, right_rows
