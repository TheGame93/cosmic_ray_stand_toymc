"""Tests for detector response sampling."""

from __future__ import annotations

import unittest

import numpy as np

from toymc_cosmic.response import apply_response


class ResponseTests(unittest.TestCase):
    """Check Bernoulli detector response behavior."""

    def test_efficiency_zero_never_fires(self) -> None:
        """An efficiency of zero must suppress all fired events."""
        crossed = np.ones((10, 1), dtype=bool)
        fired = apply_response(crossed, np.array([0.0]), np.random.default_rng(1))
        self.assertFalse(np.any(fired))

    def test_efficiency_one_always_fires_when_crossed(self) -> None:
        """An efficiency of one must keep all crossed events."""
        crossed = np.array([[True], [False], [True]])
        fired = apply_response(crossed, np.array([1.0]), np.random.default_rng(1))
        self.assertTrue(np.array_equal(fired[:, 0], crossed[:, 0]))

    def test_intermediate_efficiency_matches_expected_rate(self) -> None:
        """A large sample should approach the requested efficiency."""
        crossed = np.ones((5000, 1), dtype=bool)
        fired = apply_response(crossed, np.array([0.5]), np.random.default_rng(2))
        observed_fraction = np.mean(fired[:, 0])
        self.assertAlmostEqual(observed_fraction, 0.5, delta=0.05)
