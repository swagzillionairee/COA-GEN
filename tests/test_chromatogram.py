from __future__ import annotations

import unittest

import numpy as np

from coa.calculations import build_analytical_result
from coa.chromatogram import generate_trace, render_chromatogram
from coa.models import COAConfig


class ChromatogramTests(unittest.TestCase):
    def test_trace_is_deterministic(self) -> None:
        config = COAConfig()
        result = build_analytical_result(config.analytical)
        first_x, first_y = generate_trace(config, result)
        second_x, second_y = generate_trace(config, result)
        np.testing.assert_array_equal(first_x, second_x)
        np.testing.assert_array_equal(first_y, second_y)

    def test_seed_changes_noise_not_peak_areas(self) -> None:
        first = COAConfig()
        second = first.model_copy(deep=True)
        second.analytical.random_seed += 1
        first_result = build_analytical_result(first.analytical)
        second_result = build_analytical_result(second.analytical)
        _, first_y = generate_trace(first, first_result)
        _, second_y = generate_trace(second, second_result)
        self.assertFalse(np.array_equal(first_y, second_y))
        self.assertAlmostEqual(first_result.purity_percent_unrounded, second_result.purity_percent_unrounded)

    def test_disturbance_is_not_an_analytical_peak(self) -> None:
        config = COAConfig()
        config.analytical.injection_disturbance = True
        result = build_analytical_result(config.analytical)
        self.assertEqual(len(result.peaks), 2)

    def test_rendered_png_is_high_resolution_and_has_no_forbidden_label(self) -> None:
        config = COAConfig()
        payload = render_chromatogram(config, build_analytical_result(config.analytical))
        self.assertTrue(payload.startswith(b"\x89PNG"))
        self.assertNotIn(b"synthetic chromatogram", payload.lower())
        self.assertGreater(len(payload), 20_000)


if __name__ == "__main__":
    unittest.main()
