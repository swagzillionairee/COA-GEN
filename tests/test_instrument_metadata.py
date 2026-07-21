from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from coa.instrument_metadata import (
    derive_data_file_name,
    derive_instrument_sample_identifier,
    format_acquisition_time,
    identifier_warnings,
    randomized_acquisition_time,
)
from coa.models import COAConfig
from coa.validation import validate_for_export


class InstrumentMetadataTests(unittest.TestCase):
    def test_canonical_identifiers_support_special_characters(self) -> None:
        identifier = derive_instrument_sample_identifier("GHK-Cu Development Sample", "LOT-22", "Purity")
        self.assertEqual(identifier, "GHK_CU_LOT22_PURITY")
        filename = derive_data_file_name("GHK-Cu Development Sample", "LOT-22", date(2026, 7, 21), "Purity")
        self.assertEqual(filename, "260721_GHK_CU_LOT22_PURITY.d")

    def test_beta_prefix_is_removed_from_derived_identifiers(self) -> None:
        identifier = derive_instrument_sample_identifier("Retatrutide", "BETA-001", "Purity")
        self.assertEqual(identifier, "RETATRUTIDE_001_PURITY")

    def test_randomized_acquisition_time_uses_analysis_date_and_requested_window(self) -> None:
        rendered = randomized_acquisition_time(
            date(2026, 6, 4),
            timezone.utc,
            offset_seconds=(2 * 60 * 60) + 17,
        )
        self.assertEqual(rendered.date(), date(2026, 6, 4))
        self.assertEqual((rendered.hour, rendered.minute, rendered.second), (15, 0, 17))

    def test_default_identifiers_are_linked(self) -> None:
        self.assertEqual(identifier_warnings(COAConfig()), [])

    def test_normal_warns_and_strict_rejects_mismatch(self) -> None:
        config = COAConfig()
        config.instrument_metadata.data_file = "unrelated.d"
        normal = validate_for_export(config)
        self.assertTrue(normal.valid)
        self.assertTrue(normal.warnings)
        config.strict_identifier_matching = True
        strict = validate_for_export(config)
        self.assertFalse(strict.valid)

    def test_acquisition_display_includes_offset_and_ampm(self) -> None:
        value = datetime(2026, 7, 21, 14, 2, 3, tzinfo=timezone.utc)
        rendered = format_acquisition_time(value)
        self.assertIn("02:02:03 PM", rendered)
        self.assertIn("UTC+00:00", rendered)


if __name__ == "__main__":
    unittest.main()
