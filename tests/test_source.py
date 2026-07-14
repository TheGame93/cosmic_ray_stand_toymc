"""Tests for pluggable source models."""

from __future__ import annotations

import math
import unittest

import numpy as np

from toymc_cosmic.config import BeamSourceConfig, CosmicSourceConfig, ObjectSourceConfig
from toymc_cosmic.geometry import Detector, generation_region, min_reference_z, reference_z
from toymc_cosmic.source import (
    BeamSourceModel,
    CosmicSourceModel,
    ObjectSourceModel,
    build_source_model,
)


class CosmicSourceModelTests(unittest.TestCase):
    """Check generation-region usage, direction conventions, and total_rate_hz."""

    def test_generated_tracks_respect_region_and_direction_conventions(self) -> None:
        """Origins must lie in the generation rectangle and directions must be unit length, pointing down."""
        detectors = [Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 2.0], 1.0)]
        theta_max = math.radians(80.0)
        rng = np.random.default_rng(10)

        model = CosmicSourceModel(theta_max=theta_max, flux_hz_per_cm2=0.01)
        tracks = model.generate(500, detectors, rng)
        x_min, x_max, y_min, y_max, _ = generation_region(detectors, theta_max)

        self.assertTrue(np.all(tracks.origins[:, 0] >= x_min))
        self.assertTrue(np.all(tracks.origins[:, 0] <= x_max))
        self.assertTrue(np.all(tracks.origins[:, 1] >= y_min))
        self.assertTrue(np.all(tracks.origins[:, 1] <= y_max))
        self.assertTrue(np.allclose(tracks.origins[:, 2], reference_z(detectors)))

        direction_norms = np.linalg.norm(tracks.directions, axis=1)
        self.assertTrue(np.allclose(direction_norms, 1.0))
        self.assertTrue(np.all(tracks.directions[:, 2] <= 0.0))

    def test_total_rate_hz_is_flux_times_generation_area(self) -> None:
        """total_rate_hz must equal flux_hz_per_cm2 * area_gen."""
        detectors = [Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 2.0], 1.0)]
        theta_max = math.radians(80.0)
        model = CosmicSourceModel(theta_max=theta_max, flux_hz_per_cm2=0.01)

        _, _, _, _, area_gen = generation_region(detectors, theta_max)
        self.assertAlmostEqual(model.total_rate_hz(detectors), 0.01 * area_gen)


class BeamSourceModelTests(unittest.TestCase):
    """Check transverse profile sampling, direction, and total_rate_hz per profile."""

    def setUp(self) -> None:
        """Build a small detector stack shared by the beam tests."""
        self.detectors = [
            Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 2.0], 1.0),
            Detector("T2", [0.0, 0.0, 0.0], [2.0, 2.0, 2.0], 1.0),
        ]

    def test_uniform_origins_stay_inside_disk_and_direction_is_downstream(self) -> None:
        """Uniform-profile origins must lie within the configured disk, moving in +z."""
        rng = np.random.default_rng(1)
        model = BeamSourceModel(profile="uniform", center=(1.0, -1.0), size=(4.0,), flux_hz_per_cm2=10.0)
        tracks = model.generate(2000, self.detectors, rng)

        radii = np.hypot(tracks.origins[:, 0] - 1.0, tracks.origins[:, 1] - (-1.0))
        self.assertTrue(np.all(radii <= 2.0 + 1.0e-9))
        self.assertTrue(np.allclose(tracks.origins[:, 2], min_reference_z(self.detectors)))
        self.assertTrue(np.array_equal(tracks.directions, np.tile([0.0, 0.0, 1.0], (2000, 1))))

    def test_uniform_total_rate_hz_is_flux_times_disk_area(self) -> None:
        """total_rate_hz for a uniform profile must equal flux * disk area."""
        model = BeamSourceModel(profile="uniform", center=(0.0, 0.0), size=(4.0,), flux_hz_per_cm2=10.0)
        expected = 10.0 * math.pi * 2.0**2
        self.assertAlmostEqual(model.total_rate_hz(self.detectors), expected)

    def test_gaussian_total_rate_hz_is_flux_times_fwhm_ellipse_area(self) -> None:
        """total_rate_hz for a gaussian profile must equal flux * FWHM ellipse area."""
        model = BeamSourceModel(
            profile="gaussian", center=(0.0, 0.0), size=(4.0, 2.0), flux_hz_per_cm2=10.0
        )
        expected = 10.0 * math.pi * 2.0 * 1.0
        self.assertAlmostEqual(model.total_rate_hz(self.detectors), expected)

    def test_gaussian_origins_scatter_around_center(self) -> None:
        """Gaussian-profile origins should be centered near the configured center."""
        rng = np.random.default_rng(2)
        model = BeamSourceModel(
            profile="gaussian", center=(5.0, -3.0), size=(2.0, 2.0), flux_hz_per_cm2=10.0
        )
        tracks = model.generate(20000, self.detectors, rng)
        self.assertAlmostEqual(float(np.mean(tracks.origins[:, 0])), 5.0, delta=0.1)
        self.assertAlmostEqual(float(np.mean(tracks.origins[:, 1])), -3.0, delta=0.1)

    def test_divergence_profile_raises_not_implemented(self) -> None:
        """The divergence profile must raise NotImplementedError at construction time."""
        with self.assertRaises(NotImplementedError):
            BeamSourceModel(profile="divergence", center=(0.0, 0.0), size=(1.0,), flux_hz_per_cm2=1.0)


class ObjectSourceModelTests(unittest.TestCase):
    """Check volume sampling bounds, isotropy, and total_rate_hz."""

    def setUp(self) -> None:
        """Build a small detector stack shared by the object tests."""
        self.detectors = [Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 2.0], 1.0)]

    def test_sphere_origins_stay_inside_the_ball(self) -> None:
        """Sphere-shape origins must lie within the configured radius of the center."""
        rng = np.random.default_rng(3)
        model = ObjectSourceModel(shape="sphere", center=(1.0, 2.0, 3.0), size=(4.0,), activity_hz=1.0)
        tracks = model.generate(2000, self.detectors, rng)

        offsets = tracks.origins - np.array([1.0, 2.0, 3.0])
        distances = np.linalg.norm(offsets, axis=1)
        self.assertTrue(np.all(distances <= 2.0 + 1.0e-9))

    def test_box_origins_stay_inside_the_box(self) -> None:
        """Box-shape origins must lie within the configured half-extents of the center."""
        rng = np.random.default_rng(4)
        model = ObjectSourceModel(
            shape="box", center=(0.0, 0.0, 0.0), size=(2.0, 4.0, 6.0), activity_hz=1.0
        )
        tracks = model.generate(2000, self.detectors, rng)

        self.assertTrue(np.all(np.abs(tracks.origins[:, 0]) <= 1.0 + 1.0e-9))
        self.assertTrue(np.all(np.abs(tracks.origins[:, 1]) <= 2.0 + 1.0e-9))
        self.assertTrue(np.all(np.abs(tracks.origins[:, 2]) <= 3.0 + 1.0e-9))

    def test_disk_origins_stay_inside_the_cylinder(self) -> None:
        """Disk-shape origins must lie within the configured radius and half-height."""
        rng = np.random.default_rng(5)
        model = ObjectSourceModel(
            shape="disk", center=(0.0, 0.0, 0.0), size=(4.0, 2.0), activity_hz=1.0
        )
        tracks = model.generate(2000, self.detectors, rng)

        radii = np.hypot(tracks.origins[:, 0], tracks.origins[:, 1])
        self.assertTrue(np.all(radii <= 2.0 + 1.0e-9))
        self.assertTrue(np.all(np.abs(tracks.origins[:, 2]) <= 1.0 + 1.0e-9))

    def test_directions_are_unit_length_and_isotropic(self) -> None:
        """Directions must be unit vectors with ~zero mean over a large isotropic sample."""
        rng = np.random.default_rng(6)
        model = ObjectSourceModel(shape="sphere", center=(0.0, 0.0, 0.0), size=(1.0,), activity_hz=1.0)
        tracks = model.generate(50000, self.detectors, rng)

        direction_norms = np.linalg.norm(tracks.directions, axis=1)
        self.assertTrue(np.allclose(direction_norms, 1.0))

        mean_direction = np.mean(tracks.directions, axis=0)
        self.assertTrue(np.all(np.abs(mean_direction) < 0.02))

    def test_total_rate_hz_equals_activity(self) -> None:
        """total_rate_hz must equal the configured activity_hz, independent of detectors."""
        model = ObjectSourceModel(shape="sphere", center=(0.0, 0.0, 0.0), size=(1.0,), activity_hz=42.0)
        self.assertEqual(model.total_rate_hz(self.detectors), 42.0)


class BuildSourceModelTests(unittest.TestCase):
    """Check the config-to-model dispatcher."""

    def test_dispatches_cosmic(self) -> None:
        """A CosmicSourceConfig should build a CosmicSourceModel."""
        config = CosmicSourceConfig(theta_max=math.radians(70.0), model="cos2", flux_hz_per_cm2=0.01)
        self.assertIsInstance(build_source_model(config), CosmicSourceModel)

    def test_dispatches_beam(self) -> None:
        """A BeamSourceConfig should build a BeamSourceModel."""
        config = BeamSourceConfig(profile="uniform", center=(0.0, 0.0), size=(1.0,), flux_hz_per_cm2=1.0)
        self.assertIsInstance(build_source_model(config), BeamSourceModel)

    def test_dispatches_object(self) -> None:
        """An ObjectSourceConfig should build an ObjectSourceModel."""
        config = ObjectSourceConfig(shape="sphere", center=(0.0, 0.0, 0.0), size=(1.0,), activity_hz=1.0)
        self.assertIsInstance(build_source_model(config), ObjectSourceModel)
