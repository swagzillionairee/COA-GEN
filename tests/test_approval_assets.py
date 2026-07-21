from __future__ import annotations

import unittest

from coa.models import COAConfig
from coa.pdf_generator import generate_pdf
from coa.validation import validate_for_export
from tests.helpers import portable_signature


class ApprovalAssetTests(unittest.TestCase):
    def test_signature_authorization_gate(self) -> None:
        config = COAConfig()
        config.approval.signature_image = portable_signature()
        self.assertFalse(validate_for_export(config).valid)
        config.approval.signature_image_use_authorized = True
        self.assertTrue(validate_for_export(config).valid)

    def test_typed_identity_remains_with_signature(self) -> None:
        from pypdf import PdfReader
        import io

        config = COAConfig()
        config.approval.signature_image = portable_signature()
        config.approval.signature_image_use_authorized = True
        generated = generate_pdf(config, apply_editing_restriction=False)
        text = PdfReader(io.BytesIO(generated.pdf_bytes)).pages[0].extract_text()
        self.assertIn(config.approval.approver, text)
        self.assertIn("not a digital signature", text)


if __name__ == "__main__":
    unittest.main()
