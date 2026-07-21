from __future__ import annotations

import io
import json
import unittest
import zipfile

from coa.batch import generate_batch_archive, validate_batch_upload
from coa.models import COAConfig
from tests.helpers import png_bytes


class BatchTests(unittest.TestCase):
    def test_csv_validates_before_generation(self) -> None:
        content = (
            "report_no,client,sample_name,receipt_date,analysis_date,report_date,"
            "document_issue_date,purity_percent,main_peak_time,secondary_peak_times,"
            "secondary_peak_percent_areas,random_seed\n"
            "2026-1,Client A,Sample A,2026-01-01,2026-01-02,2026-01-03,2026-01-03,"
            "99,2.0,1.0,1.0,5\n"
        ).encode()
        result = validate_batch_upload(content, "batch.csv", COAConfig())
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(len(result.configs), 1)

    def test_duplicate_report_numbers_reject_entire_batch(self) -> None:
        reports = [
            {"report_no": "DUPLICATE"},
            {"report_no": "DUPLICATE"},
        ]
        result = validate_batch_upload(json.dumps(reports).encode(), "batch.json", COAConfig())
        self.assertFalse(result.valid)
        self.assertEqual(result.configs, [])

    def test_password_column_is_rejected(self) -> None:
        content = b"report_no,owner_password\n2026-1,forbidden-secret\n"
        result = validate_batch_upload(content, "batch.csv", COAConfig())
        self.assertFalse(result.valid)
        self.assertIn("forbidden", result.errors[0].message.lower())

    def test_nested_json_password_is_rejected_without_echoing_secret(self) -> None:
        content = json.dumps(
            [
                {
                    "report_no": "2026-NESTED-PASSWORD",
                    "document_protection": {
                        "editing_restriction": {
                            "owner_password": "never-repeat-this-secret"
                        }
                    },
                }
            ]
        ).encode()
        result = validate_batch_upload(content, "batch.json", COAConfig())
        self.assertFalse(result.valid)
        rendered = " ".join(
            f"{error.field} {error.message}" for error in result.errors
        )
        self.assertNotIn("never-repeat-this-secret", rendered)
        self.assertIn("owner_password", rendered)

    def test_portable_zip_resolves_relative_image(self) -> None:
        csv_content = (
            "report_no,sample_image_path\n"
            "2026-IMAGE,images/sample.png\n"
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("batch.csv", csv_content)
            archive.writestr("images/sample.png", png_bytes())
        result = validate_batch_upload(buffer.getvalue(), "batch.zip", COAConfig())
        self.assertTrue(result.valid, result.errors)
        self.assertIsNotNone(result.configs[0].sample_image)

    def test_archive_contains_pdf_scenario_and_manifest(self) -> None:
        archive_bytes = generate_batch_archive([COAConfig()])
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            names = set(archive.namelist())
            self.assertIn("manifest.json", names)
            self.assertTrue(any(name.startswith("pdf/") for name in names))
            self.assertTrue(any(name.startswith("scenarios/") for name in names))
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["report_count"], 1)


if __name__ == "__main__":
    unittest.main()
