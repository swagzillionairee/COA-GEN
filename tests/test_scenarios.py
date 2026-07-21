from __future__ import annotations

import json
import unittest

from coa.models import COAConfig
from coa.scenarios import ScenarioError, load_scenario_json, scenario_json
from tests.helpers import portable_sample


class ScenarioTests(unittest.TestCase):
    def test_round_trip_embeds_processed_image(self) -> None:
        config = COAConfig()
        config.sample_image = portable_sample()
        encoded = scenario_json(config)
        restored = load_scenario_json(encoded)
        self.assertEqual(restored.sample_image.sha256, config.sample_image.sha256)
        self.assertEqual(restored.sample_image.bytes(), config.sample_image.bytes())

    def test_v10_migration_adds_disabled_protection(self) -> None:
        legacy = COAConfig().model_dump(mode="json")
        legacy["schema_version"] = "1.0"
        legacy.pop("document_protection")
        legacy["branding"].pop("logo")
        legacy["branding"].pop("logo_use_authorized")
        legacy["approval"].pop("signature_image")
        legacy["approval"].pop("signature_image_use_authorized")
        restored = load_scenario_json(json.dumps(legacy))
        self.assertFalse(restored.document_protection.watermark.enabled)
        self.assertFalse(restored.document_protection.editing_restriction.enabled)

    def test_future_schema_is_rejected(self) -> None:
        data = COAConfig().model_dump(mode="json")
        data["schema_version"] = "9.0"
        with self.assertRaisesRegex(ScenarioError, "newer"):
            load_scenario_json(json.dumps(data))

    def test_unknown_fields_are_rejected(self) -> None:
        data = COAConfig().model_dump(mode="json")
        data["mystery"] = "discard me"
        with self.assertRaises(ScenarioError):
            load_scenario_json(json.dumps(data))

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(ScenarioError, "Duplicate"):
            load_scenario_json('{"schema_version":"1.1","schema_version":"1.1"}')

    def test_nested_password_field_is_rejected_without_echoing_secret(self) -> None:
        payload = COAConfig().model_dump(mode="json")
        payload["document_protection"]["editing_restriction"]["owner_password"] = (
            "never-repeat-this-secret"
        )
        with self.assertRaises(ScenarioError) as captured:
            load_scenario_json(json.dumps(payload))
        self.assertNotIn("never-repeat-this-secret", str(captured.exception))
        self.assertIn("owner_password", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
