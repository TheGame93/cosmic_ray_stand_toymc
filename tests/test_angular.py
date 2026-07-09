"""Tests for angular sampling."""

from __future__ import annotations

import math
import unittest

import numpy as np

from toymc_cosmic.angular import Cos2AngularModel


class AngularTests(unittest.TestCase):
    """Check the default angular model sampling."""

    def test_cos2_samples_stay_in_range_and_match_cdf(self) -> None:
        """The sampled distribution should match the analytic CDF reasonably well."""
        rng = np.random.default_rng(12345)
        model = Cos2AngularModel()
        theta_max = math.radians(80.0)

        samples = model.sample_theta(30000, theta_max, rng)
        self.assertTrue(np.all(samples >= 0.0))
        self.assertTrue(np.all(samples <= theta_max))

        grid = np.linspace(0.0, theta_max, 20)
        empirical_cdf = np.array([np.mean(samples <= value) for value in grid])
        expected_cdf = (1.0 - np.cos(grid) ** 4) / (1.0 - math.cos(theta_max) ** 4)

        max_deviation = np.max(np.abs(empirical_cdf - expected_cdf))
        self.assertLess(max_deviation, 0.03)
