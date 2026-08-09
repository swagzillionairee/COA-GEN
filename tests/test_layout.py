from __future__ import annotations

import io
import unittest

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
from pypdf import PdfReader

from coa.models import COAConfig
from coa.pdf_generator import generate_pdf
from coa.validation import validate_for_export
from tests.helpers import portable_sample

PAGE_HEIGHT_POINTS = 792


def _image_bounds(page) -> list[tuple[float, float, float, float]]:
    """Return each image object's (left, bottom, right, top) in PDF user space."""

    return [
        obj.get_bounds()
        for obj in page.get_objects()
        if obj.type == pdfium_raw.FPDF_PAGEOBJ_IMAGE
    ]


def _first_text_bounds(page, needle: str) -> tuple[float, float, float, float]:
    """Return the first match's (left, bottom, right, top) in PDF user space."""

    textpage = page.get_textpage()
    try:
        match = textpage.search(needle).get_next()
        if match is None:
            raise AssertionError(f"{needle!r} was not found on the rendered page")
        char_index, char_count = match
        if textpage.count_rects(char_index, char_count) < 1:
            raise AssertionError(f"{needle!r} matched no drawable rectangle")
        return textpage.get_rect(0)
    finally:
        textpage.close()


class LayoutTests(unittest.TestCase):
    def test_no_image_layout_has_no_placeholder_panel(self) -> None:
        generated = generate_pdf(COAConfig(), apply_editing_restriction=False)
        text = PdfReader(io.BytesIO(generated.pdf_bytes)).pages[0].extract_text()
        self.assertNotIn("SUBMITTED SAMPLE", text)

    def test_image_layout_is_one_page_and_labeled(self) -> None:
        config = COAConfig()
        config.sample_image = portable_sample()
        config.template.preset = "Reference COA with Sample Image"
        generated = generate_pdf(config, apply_editing_restriction=False)
        reader = PdfReader(io.BytesIO(generated.pdf_bytes))
        self.assertEqual(len(reader.pages), 1)
        self.assertIn("SUBMITTED SAMPLE", reader.pages[0].extract_text())

        # PDF user space puts the origin at the bottom-left, so the top-right
        # sample panel is the image starting right of x=400 and above y=612.
        document = pdfium.PdfDocument(generated.pdf_bytes)
        try:
            page = document[0]
            panel_bounds = [
                bounds
                for bounds in _image_bounds(page)
                if bounds[0] > 400 and bounds[1] > PAGE_HEIGHT_POINTS - 180
            ]
            self.assertEqual(len(panel_bounds), 1)
            sample_top = panel_bounds[0][3]
            label_bottom = _first_text_bounds(page, "SUBMITTED SAMPLE")[1]
            self.assertLessEqual(sample_top, label_bottom)
        finally:
            document.close()

    def test_rendered_page_has_letter_aspect_and_nonempty_pixels(self) -> None:
        generated = generate_pdf(COAConfig(), apply_editing_restriction=False)
        document = pdfium.PdfDocument(generated.pdf_bytes)
        try:
            bitmap = document[0].render(scale=1)
            self.assertEqual((bitmap.width, bitmap.height), (612, PAGE_HEIGHT_POINTS))
            self.assertGreater(len(bitmap.buffer), 100_000)
        finally:
            document.close()

    def test_excess_peak_count_blocks_export(self) -> None:
        config = COAConfig()
        config.analytical.purity_percent = 90
        config.analytical.secondary_peak_times = [0.2 + index * 0.35 for index in range(9)]
        config.analytical.secondary_peak_percent_areas = [10 / 9] * 8 + [10 - (10 / 9) * 8]
        report = validate_for_export(config)
        self.assertFalse(report.valid)
        self.assertTrue(any("peak" in issue.field for issue in report.errors))

    def test_long_footer_is_actionably_rejected(self) -> None:
        config = COAConfig()
        config.branding.footer_disclaimer = "word " * 150
        report = validate_for_export(config)
        self.assertFalse(report.valid)
        self.assertTrue(any(issue.field == "branding.footer_disclaimer" for issue in report.errors))


if __name__ == "__main__":
    unittest.main()
