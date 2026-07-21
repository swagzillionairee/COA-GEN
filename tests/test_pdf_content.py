from __future__ import annotations

import io
import unittest

from pypdf import PdfReader

from coa.constants import RESULT_STATUS_NOTICE
from coa.models import COAConfig
from coa.pdf_generator import generate_pdf


class PDFContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = COAConfig()
        cls.generated = generate_pdf(
            cls.config,
            apply_editing_restriction=False,
            generation_identifier="COA-DEV-UNITTEST0001",
        )
        cls.reader = PdfReader(io.BytesIO(cls.generated.pdf_bytes))
        cls.text = cls.reader.pages[0].extract_text()

    def test_exact_letter_page_and_single_page(self) -> None:
        self.assertEqual(len(self.reader.pages), 1)
        self.assertEqual(float(self.reader.pages[0].mediabox.width), 612.0)
        self.assertEqual(float(self.reader.pages[0].mediabox.height), 792.0)

    def test_source_verification_status_is_visible_and_in_metadata(self) -> None:
        self.assertEqual(self.text.count("SOURCE VERIFICATION REQUIRED"), 1)
        self.assertEqual(self.reader.metadata.subject, RESULT_STATUS_NOTICE)
        self.assertIn(RESULT_STATUS_NOTICE, self.reader.metadata.get("/Keywords"))
        self.assertNotIn(
            "Generated report - analytical results have not been independently verified.",
            self.text,
        )
        self.assertNotIn("DEVELOPMENT USE ONLY", self.text)

    def test_expected_fields_are_selectable(self) -> None:
        for expected in (
            self.config.report_no,
            self.config.client,
            self.config.sample_name,
            self.config.instrument_metadata.data_file,
            self.config.approval.approver,
            "Purity: 99.6%",
            "Peak List",
        ):
            self.assertIn(expected, self.text)

    def test_forbidden_chart_phrase_is_absent(self) -> None:
        self.assertNotIn("synthetic chromatogram", self.text.lower())

    def test_pdf_is_static_but_contact_links_remain(self) -> None:
        root = self.reader.trailer["/Root"]
        self.assertNotIn("/AcroForm", root)
        annotations = self.reader.pages[0].get("/Annots", [])
        self.assertGreaterEqual(len(annotations), 2)

    def test_generation_and_version_clutter_are_not_visible(self) -> None:
        self.assertNotIn("COA-DEV-UNITTEST0001", self.text)
        self.assertNotIn("Generation ID:", self.text)
        self.assertNotIn("App 0.1.0-beta.1", self.text)
        self.assertNotIn("COA-DEV-UNITTEST0001", self.reader.metadata.creator)
        self.assertEqual(
            self.generated.config.audit.generation_identifier,
            "COA-DEV-UNITTEST0001",
        )


if __name__ == "__main__":
    unittest.main()
