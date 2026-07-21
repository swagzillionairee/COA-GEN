from __future__ import annotations

import os
import tempfile
import unittest

from coa.lifecycle import clear_cache_and_history, recent_report_numbers, record_recent_export


class LifecycleTests(unittest.TestCase):
    def test_recent_history_flags_collisions_and_can_be_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            previous = os.environ.get("COA_DATA_DIR")
            os.environ["COA_DATA_DIR"] = temporary
            try:
                record_recent_export("2026-000001", "GEN-1", protected=False)
                record_recent_export("2026-000002", "GEN-2", protected=True)
                self.assertEqual(recent_report_numbers(), {"2026-000001", "2026-000002"})
                clear_cache_and_history()
                self.assertEqual(recent_report_numbers(), set())
            finally:
                if previous is None:
                    os.environ.pop("COA_DATA_DIR", None)
                else:
                    os.environ["COA_DATA_DIR"] = previous


if __name__ == "__main__":
    unittest.main()
