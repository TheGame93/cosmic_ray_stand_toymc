"""Tests for the pure display-bounds/clipping geometry used by the event display."""

from __future__ import annotations

import unittest

import numpy as np

from toymc_cosmic.gui.track_bounds import DisplayBounds, clip_line_to_bounds


class GuiTrackBoundsTests(unittest.TestCase):
    """Check track clipping against the finite display box."""

    def test_clip_line_to_bounds_returns_finite_segment(self) -> None:
        """The track should be clipped to the requested display box."""
        start, end = clip_line_to_bounds(
            origin=np.array([0.0, 0.0, 0.0]),
            direction=np.array([0.0, 0.0, 1.0]),
            bounds=DisplayBounds(-1.0, 1.0, -1.0, 1.0, -2.0, 3.0),
        )

        self.assertTrue(np.allclose(start, np.array([0.0, 0.0, -2.0])))
        self.assertTrue(np.allclose(end, np.array([0.0, 0.0, 3.0])))
