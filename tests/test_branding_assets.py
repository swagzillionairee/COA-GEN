from __future__ import annotations

import unittest

from coa.models import COAConfig
from coa.validation import validate_for_export
from tests.helpers import portable_logo


class BrandingAssetTests(unittest.TestCase):
    def test_logo_requires_authorization(self) -> None:
        config = COAConfig()
        config.branding.logo = portable_logo()
        report = validate_for_export(config)
        self.assertFalse(report.valid)
        self.assertIn("authorization", report.errors[0].message.lower())

    def test_authorized_logo_is_valid(self) -> None:
        config = COAConfig()
        config.branding.logo = portable_logo()
        config.branding.logo_use_authorized = True
        self.assertTrue(validate_for_export(config).valid)


if __name__ == "__main__":
    unittest.main()
