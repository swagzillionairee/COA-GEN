from __future__ import annotations

import io
import unittest

from pypdf import PdfReader

from coa.models import COAConfig
from coa.pdf_generator import generate_pdf


class PDFMetadataTests(unittest.TestCase):
    def test_metadata_contains_no_source_paths_or_passwords(self) -> None:
        config = COAConfig()
        generated = generate_pdf(config, apply_editing_restriction=False)
        metadata = PdfReader(io.BytesIO(generated.pdf_bytes)).metadata
        rendered = " ".join(str(value) for value in metadata.values()).lower()
        self.assertNotIn("/workspace/", rendered)
        self.assertNotIn("owner_password", rendered)
        self.assertNotIn("open_password", rendered)

    def test_author_is_current_fictional_brand(self) -> None:
        config = COAConfig()
        config.branding.organization_display_name = "Orion Fictional Analytics"
        generated = generate_pdf(config, apply_editing_restriction=False)
        metadata = PdfReader(io.BytesIO(generated.pdf_bytes)).metadata
        self.assertEqual(metadata.author, "Orion Fictional Analytics")


if __name__ == "__main__":
    unittest.main()
