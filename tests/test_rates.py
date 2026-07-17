"""Tests for rate and probability estimators."""

from __future__ import annotations

import math
import unittest

from toymc_cosmic.rates import (
    ProbabilityEstimate,
    RateEstimate,
    SystematicEstimateSummary,
    _apply_probability_systematics,
    _apply_rate_systematics,
    binomial_probability,
    binomial_rate,
)


class RateTests(unittest.TestCase):
    """Check numerical rate and probability helpers."""

    def test_binomial_rate_matches_expected_scale(self) -> None:
        """The rate value should be the pass fraction times `total_rate_hz`."""
        estimate = binomial_rate(n_pass=25, n_total=100, total_rate_hz=6.0)
        self.assertAlmostEqual(estimate.value, 1.5)
        self.assertGreater(estimate.error, 0.0)

    def test_binomial_probability_handles_zero_condition_count(self) -> None:
        """Undefined conditional probabilities should return NaN."""
        estimate = binomial_probability(0, 0)
        self.assertTrue(math.isnan(estimate.value))
        self.assertTrue(math.isnan(estimate.error))

    def test_rate_systematics_use_quadrature_total(self) -> None:
        """Systematic rate summaries should combine with statistics in quadrature."""
        estimate = RateEstimate(value=10.0, error=3.0, n_pass=50, n_total=100, stat_error=3.0)
        combined = _apply_rate_systematics(
            estimate,
            SystematicEstimateSummary(syst_error=4.0, quality_warning="replica_min_n_pass=7"),
        )

        self.assertEqual(combined.stat_error, 3.0)
        self.assertEqual(combined.syst_error, 4.0)
        self.assertEqual(combined.quality_warning, "replica_min_n_pass=7")
        self.assertEqual(combined.error, 5.0)

    def test_probability_systematics_use_quadrature_total(self) -> None:
        """Systematic probability summaries should combine with statistics in quadrature."""
        estimate = ProbabilityEstimate(value=0.4, error=0.03, n_joint=40, n_cond=100, stat_error=0.03)
        combined = _apply_probability_systematics(
            estimate,
            SystematicEstimateSummary(syst_error=0.04, quality_warning="replica_min_n_cond=5"),
        )

        self.assertEqual(combined.stat_error, 0.03)
        self.assertEqual(combined.syst_error, 0.04)
        self.assertEqual(combined.quality_warning, "replica_min_n_cond=5")
        self.assertAlmostEqual(combined.error, 0.05)
