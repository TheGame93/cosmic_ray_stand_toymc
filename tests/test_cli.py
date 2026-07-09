"""Tests for CLI-specific helpers."""

from __future__ import annotations

import io
import unittest

from toymc_cosmic.cli import _render_progress


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
