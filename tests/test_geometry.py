"""Tests for detector geometry and intersection behavior."""

from __future__ import annotations

import math
import unittest

import numpy as np

from toymc_cosmic.geometry import Detector, generation_region, intersect, reference_z, vertical_extent


class GeometryTests(unittest.TestCase):
    """Exercise the geometric helpers and the strict crossing rule."""

    def setUp(self) -> None:
        """Create a simple detector used by several tests."""
        self.detector = Detector(
            name="D1",
            center=np.array([0.0, 0.0, 0.0]),
            size=np.array([2.0, 2.0, 2.0]),
            efficiency=1.0,
        )

    def test_track_through_center_counts_as_crossing(self) -> None:
        """A vertical track through the detector center must count."""
        origins = np.array([[0.0, 0.0, 3.0]])
        directions = np.array([[0.0, 0.0, -1.0]])

        crossed = intersect(origins, directions, [self.detector])
        self.assertTrue(crossed[0, 0])

    def test_track_on_detector_face_does_not_count(self) -> None:
        """A track that only lies on a detector face must be excluded."""
        origins = np.array([[1.0, 0.0, 3.0]])
        directions = np.array([[0.0, 0.0, -1.0]])

        crossed = intersect(origins, directions, [self.detector])
        self.assertFalse(crossed[0, 0])

    def test_track_miss_does_not_count(self) -> None:
        """A track that misses the detector must be rejected."""
        origins = np.array([[3.0, 0.0, 3.0]])
        directions = np.array([[0.0, 0.0, -1.0]])

        crossed = intersect(origins, directions, [self.detector])
        self.assertFalse(crossed[0, 0])

    def test_generation_region_uses_vertical_margin(self) -> None:
        """The generation rectangle must grow with `tan(theta_max)`."""
        upper_detector = Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 2.0], 1.0)
        lower_detector = Detector("T2", [0.0, 0.0, 0.0], [2.0, 2.0, 2.0], 1.0)

        _, _, _, _, area = generation_region([upper_detector, lower_detector], math.radians(45.0))
        self.assertGreater(area, 4.0)
        self.assertAlmostEqual(vertical_extent([upper_detector, lower_detector]), 12.0)
        self.assertAlmostEqual(reference_z([upper_detector, lower_detector]), 11.0)
