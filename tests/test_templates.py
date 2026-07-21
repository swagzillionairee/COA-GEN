from __future__ import annotations

import os
import tempfile
import unittest

from coa.templates import (
    BUILTIN_TEMPLATE_NAME,
    list_template_names,
    load_template,
    save_template,
)


class TemplateTests(unittest.TestCase):
    def test_builtin_vitum_template_contains_requested_defaults(self) -> None:
        config = load_template(BUILTIN_TEMPLATE_NAME)
        self.assertEqual(config.client, "Vitum Lab")
        self.assertEqual(config.analysis_date.isoformat(), "2026-06-04")
        self.assertEqual(config.receipt_date, config.analysis_date)
        self.assertEqual(config.report_date, config.analysis_date)
        self.assertEqual(config.document_issue_date, config.analysis_date)
        self.assertEqual(config.matrix, "Lyophilized Powder")
        self.assertEqual(config.number_of_samples, 1)
        self.assertEqual(config.test, "Purity")
        self.assertEqual(config.instrument_metadata.instrument, "Instrument 2")
        self.assertEqual(
            config.instrument_metadata.software_version,
            "6400 Series Triple B.09.00",
        )
        self.assertEqual(config.instrument_metadata.acquired_at.date(), config.analysis_date)
        self.assertGreaterEqual(config.instrument_metadata.acquired_at.hour, 13)
        self.assertLessEqual(config.instrument_metadata.acquired_at.hour, 17)

    def test_saved_template_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            previous = os.environ.get("COA_DATA_DIR")
            os.environ["COA_DATA_DIR"] = temporary
            try:
                config = load_template(BUILTIN_TEMPLATE_NAME)
                config.client = "Saved Client"
                saved_name = save_template("My reusable values", config)
                self.assertIn(saved_name, list_template_names())
                restored = load_template(saved_name)
                self.assertEqual(restored.client, "Saved Client")
                self.assertEqual(restored.instrument_metadata.acquired_at.date(), restored.analysis_date)
            finally:
                if previous is None:
                    os.environ.pop("COA_DATA_DIR", None)
                else:
                    os.environ["COA_DATA_DIR"] = previous


if __name__ == "__main__":
    unittest.main()
