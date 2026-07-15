"""Tests for detector geometry and intersection behavior."""

from __future__ import annotations

import math
import unittest

import numpy as np

from toymc_cosmic.geometry import (
    Detector,
    bounding_box_3d,
    enclosing_sphere,
    intersect,
    reference_z,
)


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

    def test_enclosing_sphere_covers_the_full_detector_box(self) -> None:
        """The padded enclosing sphere must cover the detector stack corners."""
        upper_detector = Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 2.0], 1.0)
        lower_detector = Detector("T2", [0.0, 0.0, 0.0], [2.0, 2.0, 2.0], 1.0)

        bounds = bounding_box_3d([upper_detector, lower_detector])
        center, radius = enclosing_sphere([upper_detector, lower_detector], padding_factor=1.01)

        corners = np.array(
            [
                [bounds[0], bounds[2], bounds[4]],
                [bounds[0], bounds[2], bounds[5]],
                [bounds[0], bounds[3], bounds[4]],
                [bounds[0], bounds[3], bounds[5]],
                [bounds[1], bounds[2], bounds[4]],
                [bounds[1], bounds[2], bounds[5]],
                [bounds[1], bounds[3], bounds[4]],
                [bounds[1], bounds[3], bounds[5]],
            ]
        )
        distances = np.linalg.norm(corners - center[np.newaxis, :], axis=1)

        self.assertTrue(np.all(distances < radius))
        self.assertAlmostEqual(reference_z([upper_detector, lower_detector]), 11.0)
        self.assertAlmostEqual(radius, 0.5 * math.sqrt(2.0**2 + 2.0**2 + 12.0**2) * 1.01)
