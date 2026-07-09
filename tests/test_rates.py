"""Tests for rate and probability estimators."""

from __future__ import annotations

import math
import unittest

from toymc_cosmic.rates import binomial_probability, binomial_rate


class RateTests(unittest.TestCase):
    """Check numerical rate and probability helpers."""

    def test_binomial_rate_matches_expected_scale(self) -> None:
        """The rate value should be the pass fraction times `flux * area`."""
        estimate = binomial_rate(n_pass=25, n_total=100, flux=2.0, area=3.0)
        self.assertAlmostEqual(estimate.value, 1.5)
        self.assertGreater(estimate.error, 0.0)

    def test_binomial_probability_handles_zero_condition_count(self) -> None:
        """Undefined conditional probabilities should return NaN."""
        estimate = binomial_probability(0, 0)
        self.assertTrue(math.isnan(estimate.value))
        self.assertTrue(math.isnan(estimate.error))
