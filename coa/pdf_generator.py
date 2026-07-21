"""One-page Reference COA PDF renderer using native text and vector elements."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from reportlab.lib.colors import Color, HexColor, black, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .calculations import build_analytical_result, peak_table_rows
from .chromatogram import render_chromatogram
from .instrument_metadata import instrument_display_columns
from .metadata import config_for_export, pdf_metadata
from .models import COAConfig, PortableImage
from .pdf_security import ProtectionVerification, protect_pdf
from .validation import resolve_watermark_text, validate_for_export


PAGE_WIDTH, PAGE_HEIGHT = letter
MARGIN = 36.0


class LayoutOverflowError(ValueError):
    pass


@dataclass(frozen=True)
class PDFGenerationResult:
    pdf_bytes: bytes
    config: COAConfig
    protection: ProtectionVerification | None = None


_FONTS_REGISTERED = False


def _register_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    font_dir = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    files = {
        "DejaVuSans": "DejaVuSans.ttf",
        "DejaVuSans-Bold": "DejaVuSans-Bold.ttf",
        "DejaVuSerif": "DejaVuSerif.ttf",
        "DejaVuSerif-Bold": "DejaVuSerif-Bold.ttf",
    }
    if all((font_dir / filename).exists() for filename in files.values()):
        for internal_name, filename in files.items():
            if internal_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(internal_name, str(font_dir / filename)))
        pdfmetrics.registerFontFamily(
            "DejaVuSans", normal="DejaVuSans", bold="DejaVuSans-Bold"
        )
        pdfmetrics.registerFontFamily(
            "DejaVuSerif", normal="DejaVuSerif", bold="DejaVuSerif-Bold"
        )
    _FONTS_REGISTERED = True


def _font(config: COAConfig, role: str = "body", bold: bool = False) -> str:
    _register_fonts()
    requested = {
        "body": config.branding.body_font,
        "title": config.branding.title_font,
        "table": config.branding.table_font,
    }[role]
    base = "DejaVuSerif" if requested == "DejaVu Serif" else "DejaVuSans"
    name = f"{base}-Bold" if bold else base
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    return ("Times-Bold" if bold else "Times-Roman") if "Serif" in base else (
        "Helvetica-Bold" if bold else "Helvetica"
    )


def _named_font(family: str, bold: bool = False) -> str:
    _register_fonts()
    base = "DejaVuSerif" if family == "DejaVu Serif" else "DejaVuSans"
    name = f"{base}-Bold" if bold else base
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    return ("Times-Bold" if bold else "Times-Roman") if "Serif" in base else (
        "Helvetica-Bold" if bold else "Helvetica"
    )


def _wrap(text: str, font_name: str, size: float, width: float) -> list[str]:
    paragraphs = text.splitlines() or [""]
    lines: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if pdfmetrics.stringWidth(candidate, font_name, size) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _draw_wrapped(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    *,
    font_name: str,
    size: float,
    leading: float,
    max_lines: int,
    color=black,
) -> float:
    lines = _wrap(text, font_name, size, width)
    if len(lines) > max_lines:
        raise LayoutOverflowError(
            f"Text needs {len(lines)} lines in a region that allows {max_lines}: {text[:80]}"
        )
    pdf.setFont(font_name, size)
    pdf.setFillColor(color)
    for line in lines:
        pdf.drawString(x, y, line)
        y -= leading
    return y


def _fit_text(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    font_name: str,
    size: float,
    minimum_size: float,
) -> None:
    actual = size
    while actual > minimum_size and pdfmetrics.stringWidth(text, font_name, actual) > width:
        actual -= 0.2
    if pdfmetrics.stringWidth(text, font_name, actual) > width:
        raise LayoutOverflowError(f"Field does not fit its fixed region: {text[:80]}")
    pdf.setFont(font_name, actual)
    pdf.drawString(x, y, text)


def _draw_label_value(
    pdf: canvas.Canvas,
    config: COAConfig,
    label: str,
    value: str,
    x: float,
    y: float,
    width: float,
    *,
    size: float = 9.2,
) -> None:
    bold = _font(config, "body", True)
    regular = _font(config, "body", False)
    pdf.setFillColor(black)
    pdf.setFont(bold, size)
    pdf.drawString(x, y, label)
    label_width = pdfmetrics.stringWidth(label + " ", bold, size)
    _fit_text(pdf, value, x + label_width, y, width - label_width, regular, size, 7.8)


def _image_reader_for_frame(image: PortableImage, width: int, height: int, cover: bool) -> ImageReader:
    source = Image.open(io.BytesIO(image.bytes())).convert("RGBA")
    if cover:
        source_ratio = source.width / source.height
        target_ratio = width / height
        if source_ratio > target_ratio:
            crop_width = int(source.height * target_ratio)
            offsets = {
                "left": 0,
                "right": source.width - crop_width,
                "center": (source.width - crop_width) // 2,
                "top": (source.width - crop_width) // 2,
                "bottom": (source.width - crop_width) // 2,
            }
            left = offsets[image.crop_position]
            source = source.crop((left, 0, left + crop_width, source.height))
        elif source_ratio < target_ratio:
            crop_height = int(source.width / target_ratio)
            offsets = {
                "top": 0,
                "bottom": source.height - crop_height,
                "center": (source.height - crop_height) // 2,
                "left": (source.height - crop_height) // 2,
                "right": (source.height - crop_height) // 2,
            }
            top = offsets[image.crop_position]
            source = source.crop((0, top, source.width, top + crop_height))
        source = source.resize((width, height), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    source.save(output, format="PNG", optimize=True)
    return ImageReader(io.BytesIO(output.getvalue()))


def _draw_contained_image(
    pdf: canvas.Canvas,
    image: PortableImage,
    x: float,
    y: float,
    max_width: float,
    max_height: float,
) -> None:
    ratio = image.width / image.height
    box_ratio = max_width / max_height
    if ratio > box_ratio:
        width = max_width
        height = width / ratio
    else:
        height = max_height
        width = height * ratio
    pdf.drawImage(
        ImageReader(io.BytesIO(image.bytes())),
        x + (max_width - width) / 2,
        y + (max_height - height) / 2,
        width=width,
        height=height,
        preserveAspectRatio=True,
        mask="auto",
    )


def _draw_header(pdf: canvas.Canvas, config: COAConfig) -> None:
    accent = HexColor(config.branding.primary_color)
    if config.branding.logo is not None:
        _draw_contained_image(pdf, config.branding.logo, MARGIN, 742, 160, 36)
    else:
        pdf.setFillColor(accent)
        pdf.roundRect(MARGIN, 746, 24, 24, 4, fill=1, stroke=0)
        pdf.setFillColor(white)
        pdf.setFont(_font(config, "body", True), 13)
        pdf.drawCentredString(MARGIN + 12, 753, "N")
        pdf.setFillColor(accent)
        pdf.setFont(_font(config, "body", True), 12)
        _fit_text(
            pdf,
            config.branding.organization_display_name,
            MARGIN + 32,
            755,
            205,
            _font(config, "body", True),
            12,
            9,
        )
        pdf.setFont(_font(config), 7.2)
        pdf.drawString(MARGIN + 32, 744, "ANALYTICAL REPORT")

    rows = [
        ("Client:", config.client),
        ("Report #:", config.report_no),
        ("Issued:", config.document_issue_date.strftime(config.template.header_date_format)),
        ("Page:", config.template.page_number_format),
    ]
    x = 353
    y = 770
    for label, value in rows:
        _draw_label_value(pdf, config, label, value, x, y, 223, size=8.0)
        y -= 10.2
    pdf.setStrokeColor(accent)
    pdf.setLineWidth(1.2)
    pdf.line(MARGIN, 708, PAGE_WIDTH - MARGIN, 708)


def _draw_sample_information(pdf: canvas.Canvas, config: COAConfig) -> None:
    body_size = 8.2
    has_image = config.sample_image is not None
    sample_value = config.sample_name
    if config.template.append_strength_to_sample and config.strength_or_presentation:
        sample_value = f"{sample_value} ({config.strength_or_presentation})"
    if has_image:
        # The image variant gives the long sample identity a full-width row,
        # instead of shrinking it to fit a narrow two-column cell.
        _draw_label_value(pdf, config, "Client:", config.client, MARGIN, 696, 214, size=body_size)
        _draw_label_value(
            pdf,
            config,
            "Received:",
            config.receipt_date.strftime(config.template.body_date_format),
            260,
            696,
            154,
            size=body_size,
        )
        _draw_label_value(pdf, config, config.template.sample_label, sample_value, MARGIN, 682, 378, size=body_size)
        _draw_label_value(
            pdf, config, config.template.batch_label, config.batch_no or "Not assigned", MARGIN, 668, 214, size=body_size
        )
        _draw_label_value(
            pdf,
            config,
            "Analyzed:",
            config.analysis_date.strftime(config.template.body_date_format),
            260,
            668,
            154,
            size=body_size,
        )
        _draw_label_value(pdf, config, "Test:", config.test, MARGIN, 654, 214, size=body_size)
        _draw_label_value(
            pdf,
            config,
            "Reported:",
            config.report_date.strftime(config.template.body_date_format),
            260,
            654,
            154,
            size=body_size,
        )
        _draw_label_value(
            pdf, config, "Matrix / Samples:", f"{config.matrix} / {config.number_of_samples}", MARGIN, 640, 378, size=body_size
        )
    else:
        left_rows = [
            ("Client:", config.client),
            (config.template.sample_label, sample_value),
            (config.template.batch_label, config.batch_no or "Not assigned"),
            ("Test:", config.test),
        ]
        right_rows = [
            ("Received:", config.receipt_date.strftime(config.template.body_date_format)),
            ("Analyzed:", config.analysis_date.strftime(config.template.body_date_format)),
            ("Reported:", config.report_date.strftime(config.template.body_date_format)),
            ("Matrix / Samples:", f"{config.matrix} / {config.number_of_samples}"),
        ]
        for index, (label, value) in enumerate(left_rows):
            _draw_label_value(pdf, config, label, value, MARGIN, 696 - index * 14, 252, size=body_size)
        for index, (label, value) in enumerate(right_rows):
            _draw_label_value(pdf, config, label, value, 310, 696 - index * 14, 266, size=body_size)

    if has_image and config.sample_image is not None:
        frame_x, frame_y, frame_w, frame_h = 438, 644, 138, 49
        pdf.setStrokeColor(HexColor("#94A3B8"))
        pdf.setLineWidth(0.5)
        pdf.rect(frame_x, frame_y, frame_w, frame_h, fill=0, stroke=1)
        pdf.drawImage(
            _image_reader_for_frame(config.sample_image, 276, 98, cover=True),
            frame_x,
            frame_y,
            width=frame_w,
            height=frame_h,
            mask="auto",
        )
        pdf.setFillColor(HexColor("#334155"))
        pdf.setFont(_font(config, "body", True), 7.0)
        pdf.drawString(frame_x, 697, "SUBMITTED SAMPLE")
        if config.sample_image.caption:
            _draw_wrapped(
                pdf,
                config.sample_image.caption,
                frame_x,
                637,
                frame_w,
                font_name=_font(config),
                size=6.8,
                leading=7.2,
                max_lines=2,
                color=HexColor("#475569"),
            )


def _draw_title_and_result(pdf: canvas.Canvas, config: COAConfig, purity: str) -> None:
    title_font = _font(config, "title", True)
    title_color = HexColor(config.branding.title_color)
    pdf.setFillColor(title_color)
    pdf.setFont(title_font, 16)
    title = "Certificate of Analysis"
    title_width = pdfmetrics.stringWidth(title, title_font, 16)
    pdf.drawCentredString(PAGE_WIDTH / 2, 617, title)
    if config.branding.certificate_underline != "none":
        pdf.setStrokeColor(title_color)
        pdf.setLineWidth(0.7)
        pdf.line((PAGE_WIDTH - title_width) / 2, 614, (PAGE_WIDTH + title_width) / 2, 614)
        if config.branding.certificate_underline == "double":
            pdf.line((PAGE_WIDTH - title_width) / 2, 611.5, (PAGE_WIDTH + title_width) / 2, 611.5)

    marker = config.result_note_marker or ""
    result_text = f"Purity: {purity}%{marker}"
    result_font = _font(config, "body", True)
    result_width = pdfmetrics.stringWidth(result_text, result_font, 12.0) + 18
    pdf.setFillColor(HexColor(config.branding.purity_highlight_color))
    pdf.roundRect((PAGE_WIDTH - result_width) / 2, 584, result_width, 18, 2, fill=1, stroke=0)
    pdf.setFillColor(black)
    pdf.setFont(result_font, 12)
    pdf.drawCentredString(PAGE_WIDTH / 2, 589, result_text)
    if config.purity_qualifier:
        pdf.setFont(_font(config), 7.0)
        pdf.drawCentredString(PAGE_WIDTH / 2, 576, config.purity_qualifier)
    note_parts: list[str] = []
    if config.result_note:
        note_parts.append(f"{marker} {config.result_note}".strip())
    if config.purity_basis_description:
        note_parts.append(f"Basis: {config.purity_basis_description}")
    if config.excluded_component_text:
        note_parts.append(f"Excluded: {config.excluded_component_text}")
    if config.notes:
        note_parts.append(f"Notes: {config.notes}")
    if note_parts:
        note = " · ".join(note_parts)
        _draw_wrapped(
            pdf,
            note,
            76,
            569,
            460,
            font_name=_font(config),
            size=7.2,
            leading=7.8,
            max_lines=2,
            color=HexColor("#334155"),
        )


def _draw_instrument_block(pdf: canvas.Canvas, config: COAConfig) -> None:
    top = 548
    pdf.setStrokeColor(black)
    pdf.setLineWidth(0.7)
    pdf.line(MARGIN, top, PAGE_WIDTH - MARGIN, top)
    pdf.setFont(_font(config, "body", True), 7.6)
    pdf.drawString(MARGIN, top - 9, "Instrument and Acquisition Details")

    columns = instrument_display_columns(config.instrument_metadata)
    if not config.template.preserve_blank_instrument_rows:
        columns = tuple(
            [row for row in column if row.value]
            for column in columns
        )
    for column_index, column in enumerate(columns):
        x = MARGIN + column_index * 270
        width = 258
        y = 527
        for row_index, row in enumerate(column):
            _draw_label_value(
                pdf,
                config,
                f"{row.label}:",
                row.value or " ",
                x,
                y,
                width,
                size=config.template.metadata_text_min_pt,
            )
            y -= 8.4
            if y < 455 and row_index < len(column) - 1:
                raise LayoutOverflowError("Instrument metadata exceeds its fixed one-page region")


def _draw_chromatogram(pdf: canvas.Canvas, config: COAConfig, chart_bytes: bytes) -> None:
    pdf.setFillColor(black)
    pdf.setFont(_font(config, "body", True), 8.7)
    pdf.drawString(MARGIN, 451, "Chromatograms")
    pdf.setLineWidth(0.5)
    pdf.line(MARGIN, 446, PAGE_WIDTH - MARGIN, 446)
    pdf.drawImage(
        ImageReader(io.BytesIO(chart_bytes)),
        MARGIN,
        309,
        width=PAGE_WIDTH - 2 * MARGIN,
        height=132,
        preserveAspectRatio=False,
        mask="auto",
    )


def _draw_peak_table_and_approval(pdf: canvas.Canvas, config: COAConfig, rows: list[tuple[str, str, str]]) -> None:
    x, top, width = MARGIN, 298, 220
    pdf.setFont(_font(config, "body", True), 8.5)
    pdf.drawString(x, top, "Peak List")
    table_top = top - 6
    row_height = 9
    total_rows = len(rows) + 1
    bottom = table_top - total_rows * row_height
    if bottom < 182:
        raise LayoutOverflowError("Peak table exceeds its fixed one-page region")
    col_widths = (62, 90, 68)
    pdf.setFillColor(HexColor("#E8EEF1"))
    pdf.rect(x, table_top - row_height, width, row_height, fill=1, stroke=0)
    pdf.setFillColor(black)
    pdf.setStrokeColor(black)
    pdf.setLineWidth(0.45)
    pdf.rect(x, bottom, width, total_rows * row_height, fill=0, stroke=1)
    cursor = x
    for col_width in col_widths[:-1]:
        cursor += col_width
        pdf.line(cursor, bottom, cursor, table_top)
    for index in range(1, total_rows):
        y = table_top - index * row_height
        pdf.line(x, y, x + width, y)

    headers = ("Time", "Area", "%Area")
    cursor = x
    for header, col_width in zip(headers, col_widths, strict=True):
        pdf.setFont(_font(config, "table", True), 7.0)
        pdf.drawCentredString(cursor + col_width / 2, table_top - 6.8, header)
        cursor += col_width
    for row_index, row in enumerate(rows, start=1):
        cursor = x
        baseline = table_top - row_index * row_height - 6.8
        for value, col_width in zip(row, col_widths, strict=True):
            pdf.setFont(_font(config, "table"), 7.0)
            pdf.drawRightString(cursor + col_width - 5, baseline, value)
            cursor += col_width

    approval_x = 308
    pdf.setFillColor(black)
    pdf.setFont(_font(config, "body", True), 8.5)
    pdf.drawString(approval_x, top, config.approval.heading)
    if config.approval.signature_image is not None:
        _draw_contained_image(pdf, config.approval.signature_image, approval_x, 235, 150, 42)
    else:
        pdf.setFillColor(HexColor(config.branding.primary_color))
        pdf.setFont(_font(config, "body", True), 8.8)
        pdf.drawString(approval_x, 254, config.approval.approval_mark)
    if config.approval.show_rule:
        pdf.setStrokeColor(black)
        pdf.setLineWidth(0.55)
        pdf.line(approval_x, 230, 566, 230)
    pdf.setFillColor(black)
    pdf.setFont(_font(config, "body", True), 8.0)
    pdf.drawString(approval_x, 218, config.approval.approver)
    pdf.setFont(_font(config), 7.2)
    pdf.drawString(approval_x, 207, config.approval.approver_title)
    pdf.drawString(
        approval_x,
        196,
        f"Approval date: {config.approval.approval_date.strftime(config.template.body_date_format)}",
    )
    pdf.setFont(_font(config), 6.4)
    pdf.setFillColor(HexColor("#475569"))
    pdf.drawString(approval_x, 185, "Presentational approval only - not a digital signature.")


def _draw_footer(pdf: canvas.Canvas, config: COAConfig) -> None:
    top, bottom = 169, 36
    pdf.setStrokeColor(HexColor(config.branding.primary_color))
    pdf.setLineWidth(0.8)
    pdf.line(MARGIN, top, PAGE_WIDTH - MARGIN, top)

    left_x, left_width = MARGIN, 246
    pdf.setFillColor(HexColor(config.branding.primary_color))
    pdf.setFont(_font(config, "body", True), 8.5)
    pdf.drawString(left_x, 156, config.branding.organization_display_name)
    pdf.setFillColor(black)
    contact_lines = [
        config.branding.address,
        config.branding.phone,
        config.branding.website,
        config.branding.email,
    ]
    y = 144
    for line in contact_lines:
        _fit_text(pdf, line, left_x, y, left_width, _font(config), 7.2, config.template.footer_text_min_pt)
        if line == config.branding.website and line.startswith(("http://", "https://")):
            pdf.linkURL(line, (left_x, y - 2, left_x + min(left_width, 230), y + 7), relative=0)
        if line == config.branding.email and "@" in line:
            pdf.linkURL(f"mailto:{line}", (left_x, y - 2, left_x + min(left_width, 230), y + 7), relative=0)
        y -= 10
    if config.branding.quality_statement:
        _draw_wrapped(
            pdf,
            config.branding.quality_statement,
            left_x,
            y - 1,
            left_width,
            font_name=_font(config),
            size=7.2,
            leading=7.8,
            max_lines=3,
            color=HexColor("#334155"),
        )

    box_x, box_y, box_width, box_height = 300, 76, 276, 82
    pdf.setStrokeColor(HexColor("#64748B"))
    pdf.setLineWidth(0.55)
    pdf.rect(box_x, box_y, box_width, box_height, fill=0, stroke=1)
    pdf.setFillColor(black)
    pdf.setFont(_font(config, "body", True), 7.2)
    pdf.drawString(box_x + 7, box_y + box_height - 11, "REPORT NOTICE")
    pdf.setFillColor(HexColor("#475569"))
    pdf.setFont(_font(config), 5.9)
    pdf.drawRightString(
        box_x + box_width - 7,
        box_y + box_height - 11,
        "SOURCE VERIFICATION REQUIRED",
    )
    _draw_wrapped(
        pdf,
        config.branding.footer_disclaimer,
        box_x + 7,
        box_y + box_height - 22,
        box_width - 14,
        font_name=_font(config),
        size=7.2,
        leading=7.8,
        max_lines=8,
        color=HexColor("#1F2937"),
    )

def _draw_watermark(pdf: canvas.Canvas, config: COAConfig) -> None:
    watermark = config.document_protection.watermark
    if not watermark.enabled:
        return
    text = resolve_watermark_text(config)
    pdf.saveState()
    try:
        pdf.setFillColor(HexColor(watermark.color))
        if hasattr(pdf, "setFillAlpha"):
            pdf.setFillAlpha(watermark.opacity)
        pdf.setFont(_named_font(watermark.font, True), watermark.size)
        if watermark.repeat:
            for y in (145, 395, 645):
                for x in (165, 447):
                    pdf.saveState()
                    pdf.translate(x, y)
                    pdf.rotate(watermark.rotation_degrees)
                    pdf.drawCentredString(0, 0, text)
                    pdf.restoreState()
        else:
            y = {"upper": 565, "center": 396, "lower": 230}[watermark.placement]
            pdf.translate(PAGE_WIDTH / 2, y)
            pdf.rotate(watermark.rotation_degrees)
            pdf.drawCentredString(0, 0, text)
    finally:
        pdf.restoreState()


def _render_unprotected(config: COAConfig) -> bytes:
    analytical_result = build_analytical_result(config.analytical)
    chart = render_chromatogram(config, analytical_result)
    metadata = pdf_metadata(config)
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter, pageCompression=1)
    pdf.setTitle(metadata["title"])
    pdf.setAuthor(metadata["author"])
    pdf.setSubject(metadata["subject"])
    pdf.setKeywords(metadata["keywords"])
    pdf.setCreator(metadata["creator"])
    _draw_header(pdf, config)
    _draw_sample_information(pdf, config)
    _draw_title_and_result(pdf, config, analytical_result.purity_display)
    _draw_instrument_block(pdf, config)
    _draw_chromatogram(pdf, config, chart)
    _draw_peak_table_and_approval(pdf, config, peak_table_rows(analytical_result, config.analytical))
    _draw_footer(pdf, config)
    _draw_watermark(pdf, config)
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def generate_pdf(
    config: COAConfig,
    *,
    apply_editing_restriction: bool | None = None,
    owner_password: str | None = None,
    owner_password_confirm: str | None = None,
    open_password: str | None = None,
    generation_identifier: str | None = None,
) -> PDFGenerationResult:
    """Validate, render one static page, then optionally protect and verify it."""

    validation = validate_for_export(config)
    validation.raise_for_errors()
    export_config = config_for_export(config, generation_identifier)
    unprotected = _render_unprotected(export_config)
    protect = (
        export_config.document_protection.editing_restriction.enabled
        if apply_editing_restriction is None
        else apply_editing_restriction
    )
    if not protect:
        return PDFGenerationResult(unprotected, export_config, None)

    protected, verification = protect_pdf(
        unprotected,
        export_config.document_protection.editing_restriction,
        owner_password=owner_password,
        owner_password_confirm=owner_password_confirm,
        open_password=open_password,
    )
    return PDFGenerationResult(protected, export_config, verification)
