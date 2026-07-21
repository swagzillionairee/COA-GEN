from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from coa.numbering import NumberingPolicy, reserve_report_numbers


class NumberingTests(unittest.TestCase):
    def test_atomic_sequence_and_collision_skip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            policy = NumberingPolicy(prefix="COA", padding=4, sequence_start=1)
            first = reserve_report_numbers(
                2,
                policy=policy,
                state_directory=directory,
                today=date(2026, 7, 21),
            )
            self.assertEqual(first, ["COA-2026-0001", "COA-2026-0002"])
            second = reserve_report_numbers(
                2,
                policy=policy,
                existing_numbers={"COA-2026-0003"},
                state_directory=directory,
                today=date(2026, 7, 21),
            )
            self.assertEqual(second, ["COA-2026-0004", "COA-2026-0005"])

    def test_year_rollover_preserves_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            reserve_report_numbers(1, state_directory=directory, today=date(2026, 12, 31))
            next_year = reserve_report_numbers(1, state_directory=directory, today=date(2027, 1, 1))
            self.assertEqual(next_year, ["2027-000001"])


if __name__ == "__main__":
    unittest.main()
