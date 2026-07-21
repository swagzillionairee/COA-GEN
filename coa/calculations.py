"""Deterministic analytical calculations shared by charts, tables, and PDFs."""

from __future__ import annotations

import math
import random
from decimal import Decimal, ROUND_FLOOR

from .models import AnalyticalResult, AnalyticalSettings, PeakResult


def largest_remainder_percentages(values: list[float], decimals: int = 2) -> list[str]:
    """Format percentages so their displayed total is exactly 100.

    The input values must already represent unrounded percentages totaling 100.
    Integer display units are distributed by largest fractional remainder with a
    stable index tie-break, making the output deterministic.
    """

    if not values:
        return []
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("Percentages must be finite and nonnegative")
    if abs(sum(values) - 100.0) > 0.000001:
        raise ValueError("Unrounded percentages must total 100% within 0.000001")

    scale = 10**decimals
    raw_units = [Decimal(str(value)) * scale for value in values]
    units = [int(value.to_integral_value(rounding=ROUND_FLOOR)) for value in raw_units]
    target = 100 * scale
    missing = target - sum(units)
    order = sorted(
        range(len(values)),
        key=lambda index: (raw_units[index] - units[index], -index),
        reverse=True,
    )
    for index in order[:missing]:
        units[index] += 1

    return [f"{value / scale:.{decimals}f}" for value in units]


def compact_number(value: float, decimals: int) -> str:
    rendered = f"{value:.{decimals}f}"
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _automatic_peak_rows(settings: AnalyticalSettings) -> list[dict[str, object]]:
    total_area = settings.absolute_area_scale
    main_area = total_area * settings.purity_percent / 100.0
    secondary_total = total_area - main_area
    rows: list[dict[str, object]] = [
        {
            "retention_time": settings.main_peak_time,
            "area": main_area,
            "width": settings.default_peak_width,
            "tailing": settings.tailing,
            "is_main": True,
            "include_in_table": True,
            "annotate": settings.purity_percent >= settings.chart_label_threshold_percent,
            "annotation_prefix": "",
            "marker": settings.result_note_marker if hasattr(settings, "result_note_marker") else None,
        }
    ]

    if secondary_total <= 0:
        return rows

    times = settings.secondary_peak_times
    if not times:
        raise ValueError("Non-100% purity requires at least one secondary peak")

    if settings.secondary_peak_percent_areas is not None:
        secondary_areas = [total_area * value / 100.0 for value in settings.secondary_peak_percent_areas]
    else:
        rng = random.Random(settings.random_seed)
        weights = [0.5 + rng.random() for _ in times]
        weight_total = sum(weights)
        secondary_areas = [secondary_total * weight / weight_total for weight in weights]
        secondary_areas[-1] = secondary_total - sum(secondary_areas[:-1])

    rng = random.Random(settings.random_seed ^ 0x5A17)
    for index, (retention_time, area) in enumerate(zip(times, secondary_areas, strict=True)):
        percent = area / total_area * 100.0
        if area <= 0:
            # Zero-area secondary controls are not analytical peaks and must not
            # create phantom rows or chart labels.
            continue
        rows.append(
            {
                "retention_time": retention_time,
                "area": area,
                "width": settings.default_peak_width * (0.75 + 0.45 * rng.random()),
                "tailing": settings.tailing,
                "is_main": False,
                "include_in_table": True,
                "annotate": percent >= settings.chart_label_threshold_percent,
                "annotation_prefix": "",
                "marker": None,
            }
        )
    return rows


def _manual_peak_rows(settings: AnalyticalSettings) -> list[dict[str, object]]:
    rows = [peak.model_dump() for peak in settings.manual_peaks]
    total = sum(float(row["area"]) for row in rows if bool(row["include_in_table"]))
    if total <= 0:
        raise ValueError("Included manual area total must be greater than zero")
    main = next(row for row in rows if bool(row["is_main"]))
    if not bool(main["include_in_table"]):
        raise ValueError("The designated purity peak must be included in the peak table")
    calculated_purity = float(main["area"]) / total * 100.0
    if abs(calculated_purity - settings.purity_percent) > 0.000001:
        raise ValueError(
            "Manual main-peak area does not agree with requested purity within 0.000001"
        )
    return rows


def build_analytical_result(settings: AnalyticalSettings) -> AnalyticalResult:
    """Create the single source of truth for purity, chart, and peak list."""

    rows = _manual_peak_rows(settings) if settings.manual_peaks else _automatic_peak_rows(settings)
    rows.sort(key=lambda row: float(row["retention_time"]))
    if len([row for row in rows if bool(row["is_main"])]) != 1:
        raise ValueError("Exactly one analytical peak must be designated as main")

    included_total = sum(float(row["area"]) for row in rows if bool(row["include_in_table"]))
    if not math.isfinite(included_total) or included_total <= 0:
        raise ValueError("Included peak area total must be finite and greater than zero")

    unrounded: list[float] = []
    included_indexes: list[int] = []
    for index, row in enumerate(rows):
        area = float(row["area"])
        if not math.isfinite(area) or area < 0:
            raise ValueError("Integrated peak areas must be finite and nonnegative")
        percent = area / included_total * 100.0
        row["unrounded_percent_area"] = percent
        if bool(row["include_in_table"]):
            included_indexes.append(index)
            unrounded.append(percent)

    displayed = largest_remainder_percentages(unrounded, settings.percent_area_decimals)
    display_by_index = dict(zip(included_indexes, displayed, strict=True))

    peaks: list[PeakResult] = []
    for index, row in enumerate(rows):
        percent = float(row["unrounded_percent_area"])
        display_value = display_by_index.get(
            index, f"{percent:.{settings.percent_area_decimals}f}"
        )
        peaks.append(
            PeakResult(
                retention_time=float(row["retention_time"]),
                area=float(row["area"]),
                unrounded_percent_area=percent,
                displayed_percent_area=display_value,
                width=float(row["width"]),
                tailing=float(row["tailing"]),
                is_main=bool(row["is_main"]),
                include_in_table=bool(row["include_in_table"]),
                annotate=bool(row["annotate"]),
                annotation_prefix=str(row.get("annotation_prefix", "")),
                marker=row.get("marker"),
            )
        )

    main = next(peak for peak in peaks if peak.is_main)
    purity_display = f"{main.unrounded_percent_area:.{settings.purity_display_decimals}f}"
    return AnalyticalResult(
        peaks=peaks,
        purity_percent_unrounded=main.unrounded_percent_area,
        purity_display=purity_display,
        included_area_total=included_total,
        random_seed=settings.random_seed,
    )


def peak_table_rows(result: AnalyticalResult, settings: AnalyticalSettings) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for peak in sorted(result.peaks, key=lambda value: value.retention_time):
        if not peak.include_in_table:
            continue
        rows.append(
            (
                f"{peak.retention_time:.{settings.retention_time_decimals}f}",
                compact_number(peak.area, settings.raw_area_decimals),
                peak.displayed_percent_area,
            )
        )
    return rows
