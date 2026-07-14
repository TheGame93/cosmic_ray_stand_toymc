"""Tests for the Tracks container."""

from __future__ import annotations

import unittest

import numpy as np

from toymc_cosmic.tracks import Tracks


class TracksTests(unittest.TestCase):
    """Check the Tracks dataclass's shape validation."""

    def test_matching_shapes_construct(self) -> None:
        """Origins and directions with matching event counts should construct fine."""
        origins = np.zeros((3, 3))
        directions = np.zeros((3, 3))
        tracks = Tracks(origins=origins, directions=directions)
        self.assertEqual(tracks.origins.shape, (3, 3))
        self.assertEqual(tracks.directions.shape, (3, 3))

    def test_wrong_origin_width_raises(self) -> None:
        """Origins must have exactly 3 columns."""
        with self.assertRaises(ValueError):
            Tracks(origins=np.zeros((3, 2)), directions=np.zeros((3, 3)))

    def test_wrong_direction_width_raises(self) -> None:
        """Directions must have exactly 3 columns."""
        with self.assertRaises(ValueError):
            Tracks(origins=np.zeros((3, 3)), directions=np.zeros((3, 2)))

    def test_mismatched_event_counts_raise(self) -> None:
        """Origins and directions must share the same event count."""
        with self.assertRaises(ValueError):
            Tracks(origins=np.zeros((3, 3)), directions=np.zeros((4, 3)))

    def test_non_2d_origins_raise(self) -> None:
        """Origins must be a 2D array."""
        with self.assertRaises(ValueError):
            Tracks(origins=np.zeros(3), directions=np.zeros((1, 3)))
