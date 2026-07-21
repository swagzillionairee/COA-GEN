from __future__ import annotations

import importlib.util
import io
import unittest

from pypdf import PdfReader

from coa.models import COAConfig
from coa.pdf_generator import generate_pdf
from coa.pdf_security import PDFSecurityError
from coa.scenarios import scenario_json


@unittest.skipUnless(importlib.util.find_spec("pikepdf"), "pikepdf is not installed")
class PDFSecurityTests(unittest.TestCase):
    def test_aes256_permissions_and_two_parser_verification(self) -> None:
        config = COAConfig()
        config.document_protection.editing_restriction.enabled = True
        generated = generate_pdf(
            config,
            owner_password="correct-horse-battery",
            owner_password_confirm="correct-horse-battery",
        )
        self.assertIsNotNone(generated.protection)
        self.assertEqual(generated.protection.encryption_bits, 256)
        self.assertTrue(generated.protection.independent_parser_verified)
        reader = PdfReader(io.BytesIO(generated.pdf_bytes))
        self.assertTrue(reader.is_encrypted)
        self.assertNotEqual(reader.decrypt("correct-horse-battery"), 0)
        self.assertNotIn("/AcroForm", reader.trailer["/Root"])

    def test_bad_password_confirmation_fails_closed(self) -> None:
        config = COAConfig()
        config.document_protection.editing_restriction.enabled = True
        with self.assertRaises(PDFSecurityError):
            generate_pdf(
                config,
                owner_password="correct-horse-battery",
                owner_password_confirm="not-the-same-password",
            )

    def test_passwords_never_serialize(self) -> None:
        config = COAConfig()
        content = scenario_json(config).lower()
        self.assertNotIn(b"owner_password\"", content)
        self.assertNotIn(b"open_password", content)

    def test_document_open_password_and_no_printing(self) -> None:
        config = COAConfig()
        restriction = config.document_protection.editing_restriction
        restriction.enabled = True
        restriction.allow_printing = False
        generated = generate_pdf(
            config,
            owner_password="owner-password-123",
            owner_password_confirm="owner-password-123",
            open_password="viewer-password-123",
        )
        reader = PdfReader(io.BytesIO(generated.pdf_bytes))
        self.assertEqual(reader.decrypt("wrong-password"), 0)
        self.assertNotEqual(reader.decrypt("viewer-password-123"), 0)
        permissions = reader.user_access_permissions
        from pypdf.constants import UserAccessPermissions as UAP

        self.assertFalse(bool(permissions & UAP.PRINT))
        self.assertFalse(bool(permissions & UAP.PRINT_TO_REPRESENTATION))


if __name__ == "__main__":
    unittest.main()
