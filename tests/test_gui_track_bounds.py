"""Tests for the pure display-bounds/clipping geometry used by the event display."""

from __future__ import annotations

import unittest

import numpy as np

from toymc_cosmic.geometry import Detector
from toymc_cosmic.gui.track_bounds import DisplayBounds, clip_line_to_bounds, compute_display_bounds
from toymc_cosmic.source import BeamSourceModel, ObjectSourceModel


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


class ComputeDisplayBoundsTests(unittest.TestCase):
    """Check the union-and-pad box computed for each source type."""

    def setUp(self) -> None:
        """Build a small two-detector stack shared by these tests."""
        self.detectors = [
            Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 2.0], 1.0),
            Detector("T2", [0.0, 0.0, 0.0], [2.0, 2.0, 2.0], 1.0),
        ]

    def test_bounds_cover_detector_stack_even_with_a_smaller_beam_footprint(self) -> None:
        """A beam footprint narrower than the detectors must not shrink the display box."""
        source_model = BeamSourceModel(
            profile="uniform", center=(0.0, 0.0), size=(0.5,), flux_hz_per_cm2=1.0
        )
        bounds = compute_display_bounds(self.detectors, source_model)

        self.assertLessEqual(bounds.x_min, -1.0)
        self.assertGreaterEqual(bounds.x_max, 1.0)
        self.assertLessEqual(bounds.y_min, -1.0)
        self.assertGreaterEqual(bounds.y_max, 1.0)
        self.assertLessEqual(bounds.z_min, -1.0)
        self.assertGreaterEqual(bounds.z_max, 11.0)

    def test_bounds_extend_to_include_an_object_source_outside_the_stack(self) -> None:
        """An object source placed away from the stack must widen the display box to reach it."""
        source_model = ObjectSourceModel(
            shape="sphere", center=(0.0, 0.0, -20.0), size=(2.0,), activity_hz=1.0
        )
        bounds = compute_display_bounds(self.detectors, source_model)

        self.assertLess(bounds.z_min, -20.0)

    def test_padding_widens_the_raw_union_on_every_axis(self) -> None:
        """The returned box must be strictly larger than the raw (unpadded) union."""
        source_model = BeamSourceModel(
            profile="uniform", center=(0.0, 0.0), size=(0.5,), flux_hz_per_cm2=1.0
        )
        bounds = compute_display_bounds(self.detectors, source_model)

        self.assertLess(bounds.x_min, -1.0)
        self.assertGreater(bounds.x_max, 1.0)
        self.assertLess(bounds.z_min, -1.0)
        self.assertGreater(bounds.z_max, 11.0)
