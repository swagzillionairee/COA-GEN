"""Create fictional bundled assets and three representative example reports."""

from __future__ import annotations

import io
from datetime import date, datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from coa.image_processing import process_image_upload
from coa.instrument_metadata import derive_data_file_name, derive_instrument_sample_identifier
from coa.models import COAConfig
from coa.pdf_generator import generate_pdf
from coa.scenarios import load_default_config, scenario_json


ROOT = Path(__file__).resolve().parents[1]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(str(ROOT / "assets" / "fonts" / filename), size=size)
    except OSError:
        return ImageFont.load_default()


def build_logo() -> bytes:
    image = Image.new("RGBA", (960, 260), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 34, 208, 224), radius=32, fill="#173F4F")
    draw.polygon([(113, 64), (170, 129), (113, 194), (56, 129)], fill="#D8A43B")
    draw.text((242, 58), "NORTHSTAR", font=_font(70, True), fill="#173F4F")
    draw.text((246, 145), "ANALYTICAL REPORT", font=_font(35), fill="#52616B")
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def build_sample_image() -> bytes:
    image = Image.new("RGB", (1200, 900), "#E9EEF1")
    draw = ImageDraw.Draw(image)
    for y in range(image.height):
        shade = int(238 - 28 * y / image.height)
        draw.line((0, y, image.width, y), fill=(shade, shade + 5, min(255, shade + 9)))
    draw.ellipse((365, 665, 835, 785), fill="#A9B5BA")
    draw.rounded_rectangle((430, 155, 770, 720), radius=58, fill="#F9FCFD", outline="#7D919A", width=8)
    draw.rectangle((455, 90, 745, 230), fill="#D5DDE0", outline="#71838B", width=7)
    draw.rounded_rectangle((465, 365, 735, 590), radius=18, fill="#F6E7A5", outline="#173F4F", width=5)
    draw.text((475, 405), "SAMPLE", font=_font(52, True), fill="#173F4F")
    draw.text((488, 482), "IMAGE", font=_font(38), fill="#173F4F")
    draw.text((400, 820), "Submitted-sample photograph", font=_font(30), fill="#42545C")
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()


def _linked_identifiers(config: COAConfig) -> None:
    config.instrument_metadata.instrument_sample_name = derive_instrument_sample_identifier(
        config.sample_name, config.batch_no, config.test
    )
    config.instrument_metadata.data_file = derive_data_file_name(
        config.sample_name, config.batch_no, config.analysis_date, config.test
    )


def main() -> None:
    (ROOT / "generated").mkdir(exist_ok=True)
    (ROOT / "examples" / "images").mkdir(parents=True, exist_ok=True)
    logo_bytes = build_logo()
    sample_bytes = build_sample_image()
    (ROOT / "assets" / "placeholder_logo.png").write_bytes(logo_bytes)
    (ROOT / "examples" / "images" / "sample-vial.jpg").write_bytes(sample_bytes)
    logo = process_image_upload(logo_bytes, "placeholder_logo.png", "logo")
    sample = process_image_upload(
        sample_bytes,
        "sample-vial.jpg",
        "sample",
        caption="Sample as received",
        crop_position="center",
    )

    first = load_default_config()
    first.branding.logo = logo
    first.branding.logo_use_authorized = True
    first.audit.generation_identifier = None

    second = load_default_config()
    second.report_no = "COA-2026-000043"
    second.client = "Arcadia Research"
    second.sample_name = "GHK-Cu"
    second.strength_or_presentation = "50 mg"
    second.batch_no = "LOT-043"
    second.document_issue_date = date(2026, 7, 12)
    second.report_date = date(2026, 7, 12)
    second.analysis_date = date(2026, 7, 11)
    second.receipt_date = date(2026, 7, 10)
    second.approval.approval_date = date(2026, 7, 12)
    second.instrument_metadata.acquired_at = datetime(2026, 7, 11, 15, 14, tzinfo=timezone.utc)
    second.analytical.purity_percent = 98.73
    second.analytical.purity_display_decimals = 2
    second.analytical.main_peak_time = 2.412
    second.analytical.secondary_peak_times = [0.741, 3.188]
    second.analytical.secondary_peak_percent_areas = [0.72, 0.55]
    second.analytical.random_seed = 43002
    second.sample_image = sample
    second.template.preset = "Reference COA with Sample Image"
    second.branding.logo = logo
    second.branding.logo_use_authorized = True
    second.document_protection.watermark.enabled = True
    second.document_protection.watermark.text = "COPY - {report_no}"
    _linked_identifiers(second)

    third = load_default_config()
    third.report_no = "SG 096-109T"
    third.client = "Summit Formulation Sandbox"
    third.sample_name = "Retatrutide"
    third.strength_or_presentation = "20 mg"
    third.batch_no = "RND-109"
    third.analytical.purity_percent = 97.5
    third.analytical.purity_display_decimals = 1
    third.analytical.main_peak_time = 2.774
    third.analytical.secondary_peak_times = [0.612, 1.184, 4.126]
    third.analytical.secondary_peak_percent_areas = [0.4, 0.9, 1.2]
    third.analytical.baseline_level = -0.025
    third.analytical.baseline_drift = 0.018
    third.analytical.random_seed = 109096
    third.branding.logo = logo
    third.branding.logo_use_authorized = True
    third.document_protection.watermark.enabled = True
    third.document_protection.watermark.text = "{client} · {report_no}"
    third.document_protection.watermark.repeat = True
    third.document_protection.watermark.size = 22
    _linked_identifiers(third)

    protected_demo = third.model_copy(deep=True)
    protected_demo.report_no = "PROTECTED-EXPORT-DEMO"
    protected_demo.document_protection.editing_restriction.enabled = True

    for index, config in enumerate((first, second, third), start=1):
        generated = generate_pdf(
            config,
            apply_editing_restriction=False,
            generation_identifier=f"COA-EXAMPLE{index:08d}",
        )
        stem = f"example-{index}-{config.report_no.replace(' ', '-').replace('/', '-') }"
        pdf_path = ROOT / "generated" / f"{stem}.pdf"
        pdf_path.write_bytes(generated.pdf_bytes)
        (ROOT / "examples" / f"{stem}.json").write_bytes(scenario_json(config))
        try:
            import fitz

            golden_dir = ROOT / "tests" / "golden"
            golden_dir.mkdir(parents=True, exist_ok=True)
            document = fitz.open(stream=generated.pdf_bytes, filetype="pdf")
            pixmap = document[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            pixmap.save(golden_dir / f"{stem}.png")
            document.close()
        except ImportError:
            pass

    (ROOT / "examples" / "protected-export-example.json").write_bytes(
        scenario_json(protected_demo)
    )


if __name__ == "__main__":
    main()
