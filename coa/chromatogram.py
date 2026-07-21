"""Deterministic chromatogram geometry and high-resolution rendering."""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

if os.name == "nt":
    local_base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
    cache_dir = local_base / "COAGenerator" / "cache" / "matplotlib"
else:
    cache_dir = Path(tempfile.gettempdir()) / "coa-matplotlib-cache"
cache_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.ticker import MultipleLocator  # noqa: E402

from .models import AnalyticalResult, COAConfig, PeakResult


def _peak_curve(x: np.ndarray, peak: PeakResult, maximum_area: float) -> np.ndarray:
    sigma = max(peak.width, 0.0005)
    relative_area = 0.0 if maximum_area <= 0 else peak.area / maximum_area
    gaussian = np.exp(-0.5 * ((x - peak.retention_time) / sigma) ** 2)
    if peak.tailing > 0:
        right = np.clip(x - peak.retention_time, 0, None)
        tail = np.exp(-right / max(sigma * (1.2 + peak.tailing), 0.0005))
        gaussian = gaussian * (1 - min(peak.tailing * 0.12, 0.45)) + tail * min(
            peak.tailing * 0.12, 0.45
        )
    return relative_area * gaussian


def generate_trace(config: COAConfig, result: AnalyticalResult, points: int = 2800) -> tuple[np.ndarray, np.ndarray]:
    settings = config.analytical
    x = np.linspace(settings.retention_time_start, settings.retention_time_end, points)
    rng = np.random.default_rng(settings.random_seed)
    y = np.full_like(x, settings.baseline_level, dtype=float)
    y += np.linspace(0.0, settings.baseline_drift, points)
    if settings.baseline_noise:
        y += rng.normal(0, settings.baseline_noise, points)

    maximum_area = max((peak.area for peak in result.peaks), default=1.0)
    for peak in result.peaks:
        y += _peak_curve(x, peak, maximum_area)

    if settings.injection_disturbance:
        location = settings.retention_time_start + 0.055 * (
            settings.retention_time_end - settings.retention_time_start
        )
        width = 0.012 * (settings.retention_time_end - settings.retention_time_start)
        y += settings.injection_disturbance_amplitude * np.exp(
            -0.5 * ((x - location) / max(width, 0.0005)) ** 2
        )
    return x, y


def render_chromatogram(config: COAConfig, result: AnalyticalResult) -> bytes:
    """Render a print-ready chart without instrument-origin claims."""

    x, y = generate_trace(config, result)
    chart = config.chromatogram
    branding = config.branding
    figure, axis = plt.subplots(figsize=(7.35, 2.25), dpi=chart.dpi)
    figure.patch.set_alpha(0)
    axis.set_facecolor("white")
    axis.plot(x, y, color=branding.trace_color, linewidth=0.75, zorder=3)

    maximum_area = max((peak.area for peak in result.peaks), default=1.0)
    if chart.show_peak_fill:
        for peak in result.peaks:
            if peak.area <= 0:
                continue
            curve = _peak_curve(x, peak, maximum_area)
            local_base = config.analytical.baseline_level + np.linspace(
                0.0, config.analytical.baseline_drift, len(x)
            )
            axis.fill_between(
                x,
                local_base,
                local_base + curve,
                where=curve > max(curve.max() * 0.003, 1e-8),
                color=branding.peak_fill_color,
                alpha=0.28,
                linewidth=0,
                zorder=2,
            )

    annotated = [peak for peak in result.peaks if peak.annotate and peak.area > 0]
    annotated.sort(key=lambda peak: peak.retention_time)
    last_x = -10.0
    tier = 0
    x_span = config.analytical.retention_time_end - config.analytical.retention_time_start
    for peak in annotated:
        index = int(np.argmin(np.abs(x - peak.retention_time)))
        peak_y = float(y[index])
        if peak.retention_time - last_x < 0.08 * x_span:
            tier = (tier + 1) % 3
        else:
            tier = 0
        last_x = peak.retention_time
        marker = peak.marker or ""
        label = (
            f"{peak.annotation_prefix}{peak.retention_time:.{config.analytical.retention_time_decimals}f}{marker}"
        )
        axis.annotate(
            label,
            xy=(peak.retention_time, peak_y),
            xytext=(0, 6 + tier * 9),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=6.7,
            color="#111827",
            arrowprops={"arrowstyle": "-", "linewidth": 0.35, "color": "#475569"},
            clip_on=True,
            zorder=5,
        )

    detector = config.detector
    if chart.show_detector_descriptor:
        reference = (
            f"Ref {detector.reference_wavelength_nm}/{detector.reference_bandwidth_nm} nm"
            if detector.reference_enabled
            else "Reference off"
        )
        descriptor = (
            f"{detector.trace_name} {detector.channel} · "
            f"{detector.signal_wavelength_nm}/{detector.signal_bandwidth_nm} nm · {reference}"
        )
        axis.text(0, 1.08, descriptor, transform=axis.transAxes, fontsize=6.6, ha="left", va="bottom")
    if chart.show_processing_label and detector.processing_label:
        axis.text(
            1,
            1.08,
            detector.processing_label,
            transform=axis.transAxes,
            fontsize=6.6,
            ha="right",
            va="bottom",
        )

    axis.set_title(config.instrument_metadata.data_file, fontsize=7.2, loc="left", pad=14)
    axis.set_xlabel("Retention time (min)", fontsize=7.2, labelpad=2)
    multiplier = chart.y_axis_scale_multiplier
    y_label = chart.response_units if multiplier is None else f"{chart.response_units} (×{multiplier:g})"
    axis.set_ylabel(y_label, fontsize=7.2, labelpad=2)
    axis.xaxis.set_major_locator(MultipleLocator(chart.x_major_tick_interval))
    axis.set_xlim(config.analytical.retention_time_start, config.analytical.retention_time_end)
    if chart.y_axis_mode == "fixed":
        axis.set_ylim(chart.y_axis_min, chart.y_axis_max)
    else:
        lower = min(float(y.min()), 0.0)
        upper = max(float(y.max()) * 1.20, lower + 0.1)
        axis.set_ylim(lower - 0.04 * (upper - lower), upper)
    axis.tick_params(axis="both", labelsize=6.4, width=0.45, length=2.5, pad=1.5)
    axis.grid(False)
    for spine in axis.spines.values():
        spine.set_color("#111827")
        spine.set_linewidth(0.55)

    figure.subplots_adjust(left=0.085, right=0.988, top=0.79, bottom=0.25)
    output = io.BytesIO()
    figure.savefig(output, format="png", dpi=chart.dpi, transparent=True)
    plt.close(figure)
    return output.getvalue()
