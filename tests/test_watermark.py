from __future__ import annotations

import io
import unittest

from pydantic import ValidationError
from pypdf import PdfReader

from coa.models import COAConfig, WatermarkSettings
from coa.pdf_generator import generate_pdf
from coa.validation import resolve_watermark_text, validate_for_export


class WatermarkTests(unittest.TestCase):
    def test_allowed_variables_resolve_from_validated_model(self) -> None:
        config = COAConfig()
        config.document_protection.watermark.enabled = True
        config.document_protection.watermark.text = (
            "{client} | {report_no} | {sample_name} | {document_issue_date}"
        )
        self.assertEqual(
            resolve_watermark_text(config),
            "Vitum Lab | 2026-000042 | Retatrutide | 2026-06-04",
        )

    def test_unknown_or_expression_variable_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            WatermarkSettings(text="{unknown}")
        config = COAConfig()
        with self.assertRaises(ValidationError):
            config.document_protection.watermark.text = "{client.__class__}"

    def test_watermark_is_native_page_content_not_an_annotation(self) -> None:
        base = COAConfig()
        base_pdf = generate_pdf(base, apply_editing_restriction=False)
        base_reader = PdfReader(io.BytesIO(base_pdf.pdf_bytes))
        base_annotations = len(base_reader.pages[0].get("/Annots", []))

        watermarked = base.model_copy(deep=True)
        watermarked.document_protection.watermark.enabled = True
        watermarked.document_protection.watermark.text = "LITERAL <b>DEMO</b> {report_no}"
        generated = generate_pdf(watermarked, apply_editing_restriction=False)
        reader = PdfReader(io.BytesIO(generated.pdf_bytes))
        text = reader.pages[0].extract_text()
        self.assertIn("LITERAL <b>DEMO</b> 2026-000042", text)
        self.assertEqual(len(reader.pages[0].get("/Annots", [])), base_annotations)

    def test_overwide_repeated_watermark_blocks_export(self) -> None:
        config = COAConfig()
        config.document_protection.watermark.enabled = True
        config.document_protection.watermark.repeat = True
        config.document_protection.watermark.text = "X" * 150
        report = validate_for_export(config)
        self.assertFalse(report.valid)
        self.assertTrue(any("too wide" in issue.message for issue in report.errors))


if __name__ == "__main__":
    unittest.main()
