"""Tests for CLI-specific helpers."""

from __future__ import annotations

import io
import unittest

from toymc_cosmic.cli import (
    _format_detector_rate_table,
    _format_probability,
    _format_rate_hz,
    _render_progress,
)
from toymc_cosmic.geometry import Detector
from toymc_cosmic.rates import ProbabilityEstimate, RateEstimate


class CliTests(unittest.TestCase):
    """Check terminal progress rendering behavior."""

    def test_progress_renderer_includes_absolute_count_and_percent(self) -> None:
        """The progress line should show both count and percentage."""
        stream = io.StringIO()
        _render_progress(10000, 25000, 40.0, stream=stream)
        self.assertEqual(stream.getvalue(), "\rProgress: 10000 / 25000 (40.00%)")

    def test_progress_renderer_adds_newline_when_complete(self) -> None:
        """The final update should terminate the progress line cleanly."""
        stream = io.StringIO()
        _render_progress(25000, 25000, 100.0, stream=stream)
        self.assertEqual(stream.getvalue(), "\rProgress: 25000 / 25000 (100.00%)\n")

    def test_rate_formatter_uses_one_decimal_digit(self) -> None:
        """Rate text should be rounded to one digit after the decimal point."""
        estimate = RateEstimate(value=109.426561, error=0.580031, n_pass=1, n_total=1)
        self.assertEqual(_format_rate_hz(estimate, 1), "109.4 +/- 0.6 Hz")

    def test_rate_formatter_uses_configured_decimal_digits(self) -> None:
        """Rate text should respect the requested number of decimal digits."""
        estimate = RateEstimate(value=0.123456, error=0.004321, n_pass=1, n_total=1)
        self.assertEqual(_format_rate_hz(estimate, 3), "0.123 +/- 0.004 Hz")

    def test_probability_formatter_uses_three_decimal_digits(self) -> None:
        """Conditional probabilities should use per-thousand precision."""
        estimate = ProbabilityEstimate(value=0.941176, error=0.00619, n_joint=1, n_cond=1445)
        self.assertEqual(_format_probability(estimate), "0.941 +/- 0.006 (n_cond=1445)")

    def test_detector_rate_table_contains_three_columns(self) -> None:
        """Detector output should be printed as one combined table."""
        detector = Detector("T1", [0.0, 0.0, 0.0], [1.0, 1.0, 1.0], 1.0)

        class DummyResult:
            """Minimal result object exposing detectors in config order."""

            detectors = [detector]

        table = _format_detector_rate_table(
            DummyResult(),
            {
                "T1": {
                    "geometric": RateEstimate(109.426561, 0.580031, 1, 1),
                    "fired": RateEstimate(87.607777, 0.519085, 1, 1),
                }
            },
            rate_decimals=1,
        )
        self.assertIn("det", table)
        self.assertIn("geometric", table)
        self.assertIn("fired", table)
        self.assertIn("T1", table)
        self.assertIn("109.4 +/- 0.6 Hz", table)
        self.assertIn("87.6 +/- 0.5 Hz", table)

    def test_detector_rate_table_uses_configured_precision(self) -> None:
        """Detector tables should use the configured detector precision."""
        detector = Detector("T1", [0.0, 0.0, 0.0], [1.0, 1.0, 1.0], 1.0)

        class DummyResult:
            """Minimal result object exposing detectors in config order."""

            detectors = [detector]

        table = _format_detector_rate_table(
            DummyResult(),
            {
                "T1": {
                    "geometric": RateEstimate(1.123456, 0.004321, 1, 1),
                    "fired": RateEstimate(0.987654, 0.003210, 1, 1),
                }
            },
            rate_decimals=3,
        )
        self.assertIn("1.123 +/- 0.004 Hz", table)
        self.assertIn("0.988 +/- 0.003 Hz", table)
