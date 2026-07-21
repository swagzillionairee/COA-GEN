from __future__ import annotations

import io
import unittest

import fitz
from pypdf import PdfReader

from coa.models import COAConfig
from coa.pdf_generator import generate_pdf
from coa.validation import validate_for_export
from tests.helpers import portable_sample


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

        document = fitz.open(stream=generated.pdf_bytes, filetype="pdf")
        page = document[0]
        sample_image_rects = [
            rect
            for image in page.get_images(full=True)
            for rect in page.get_image_rects(image)
            if rect.x0 > 400 and rect.y1 < 180
        ]
        self.assertEqual(len(sample_image_rects), 1)
        sample_rect = sample_image_rects[0]
        submitted_label = page.search_for("SUBMITTED SAMPLE")[0]
        self.assertFalse(sample_rect.intersects(submitted_label))
        self.assertGreaterEqual(sample_rect.y0, submitted_label.y1)
        document.close()

    def test_rendered_page_has_letter_aspect_and_nonempty_pixels(self) -> None:
        generated = generate_pdf(COAConfig(), apply_editing_restriction=False)
        document = fitz.open(stream=generated.pdf_bytes, filetype="pdf")
        pixmap = document[0].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
        self.assertEqual((pixmap.width, pixmap.height), (612, 792))
        self.assertGreater(len(pixmap.samples), 100_000)
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
