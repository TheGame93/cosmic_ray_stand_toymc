"""Tests for track generation."""

from __future__ import annotations

import math
import unittest

import numpy as np

from toymc_cosmic.angular import Cos2AngularModel
from toymc_cosmic.geometry import Detector, generation_region, reference_z
from toymc_cosmic.tracks import generate_tracks


class TrackTests(unittest.TestCase):
    """Check generation-region usage and direction normalization."""

    def test_generated_tracks_respect_region_and_direction_conventions(self) -> None:
        """Origins must lie in the generation rectangle and directions must be unit length."""
        detectors = [Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 2.0], 1.0)]
        rng = np.random.default_rng(10)

        tracks = generate_tracks(500, detectors, math.radians(80.0), Cos2AngularModel(), rng)
        x_min, x_max, y_min, y_max, _ = generation_region(detectors, math.radians(80.0))

        self.assertTrue(np.all(tracks.origins[:, 0] >= x_min))
        self.assertTrue(np.all(tracks.origins[:, 0] <= x_max))
        self.assertTrue(np.all(tracks.origins[:, 1] >= y_min))
        self.assertTrue(np.all(tracks.origins[:, 1] <= y_max))
        self.assertTrue(np.allclose(tracks.origins[:, 2], reference_z(detectors)))

        direction_norms = np.linalg.norm(tracks.directions, axis=1)
        self.assertTrue(np.allclose(direction_norms, 1.0))
        self.assertTrue(np.all(tracks.directions[:, 2] <= 0.0))
