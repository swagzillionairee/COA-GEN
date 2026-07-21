from __future__ import annotations

import unittest

from pydantic import ValidationError

from coa.calculations import build_analytical_result, largest_remainder_percentages
from coa.models import AnalyticalSettings, ManualPeak


class CalculationTests(unittest.TestCase):
    def test_largest_remainder_sums_exactly(self) -> None:
        displayed = largest_remainder_percentages([33.333333, 33.333333, 33.333334], 2)
        self.assertEqual(sum(map(float, displayed)), 100.0)
        self.assertEqual(displayed, ["33.33", "33.33", "33.34"])

    def test_shared_result_purity_and_table_agree(self) -> None:
        settings = AnalyticalSettings(
            purity_percent=98.73,
            secondary_peak_times=[0.7, 3.1],
            secondary_peak_percent_areas=[0.72, 0.55],
        )
        result = build_analytical_result(settings)
        main = next(peak for peak in result.peaks if peak.is_main)
        self.assertAlmostEqual(main.unrounded_percent_area, 98.73, places=8)
        self.assertEqual(result.purity_display, "98.7")
        self.assertEqual(sum(float(p.displayed_percent_area) for p in result.peaks), 100.0)

    def test_seed_reproduces_automatic_distribution(self) -> None:
        settings = AnalyticalSettings(
            purity_percent=96.0,
            secondary_peak_times=[0.5, 1.1, 3.4],
            random_seed=77,
        )
        first = build_analytical_result(settings)
        second = build_analytical_result(settings)
        self.assertEqual(first.model_dump(), second.model_dump())

    def test_zero_percent_has_no_division_by_zero(self) -> None:
        settings = AnalyticalSettings(
            purity_percent=0,
            main_peak_time=2,
            secondary_peak_times=[1],
            secondary_peak_percent_areas=[100],
        )
        result = build_analytical_result(settings)
        main = next(peak for peak in result.peaks if peak.is_main)
        self.assertEqual(main.area, 0)
        self.assertEqual(result.purity_display, "0.0")

    def test_hundred_percent_omits_phantom_secondary_peaks(self) -> None:
        settings = AnalyticalSettings(purity_percent=100, secondary_peak_times=[0.9])
        result = build_analytical_result(settings)
        self.assertEqual(len(result.peaks), 1)
        self.assertEqual(result.peaks[0].displayed_percent_area, "100.00")

    def test_manual_area_mismatch_is_rejected(self) -> None:
        settings = AnalyticalSettings(
            purity_percent=90,
            manual_peaks=[
                ManualPeak(retention_time=1, area=50, is_main=True),
                ManualPeak(retention_time=2, area=50),
            ],
        )
        with self.assertRaisesRegex(ValueError, "does not agree"):
            build_analytical_result(settings)

    def test_duplicate_retention_time_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            AnalyticalSettings(main_peak_time=2.0, secondary_peak_times=[2.0])


if __name__ == "__main__":
    unittest.main()
