"""Tests for pluggable source models."""

from __future__ import annotations

import math
import unittest

import numpy as np

from toymc_cosmic.config import BeamSourceConfig, CosmicSourceConfig, ObjectSourceConfig
from toymc_cosmic.geometry import Detector, enclosing_sphere, min_reference_z, reference_z
from toymc_cosmic.source import (
    BeamSourceModel,
    CosmicSourceModel,
    ObjectSourceModel,
    build_source_model,
)


class CosmicSourceModelTests(unittest.TestCase):
    """Check enclosing-sphere sampling, direction conventions, and normalization."""

    def setUp(self) -> None:
        """Build a small detector stack shared by the cosmic tests."""
        self.detectors = [
            Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 2.0], 1.0),
            Detector("T2", [0.0, 0.0, 0.0], [2.0, 2.0, 2.0], 1.0),
        ]

    def test_generated_tracks_start_on_enclosing_sphere_and_point_downward(self) -> None:
        """Cosmic origins must lie on the enclosing sphere and directions must point downward."""
        rng = np.random.default_rng(10)
        model = CosmicSourceModel(model="cos2", flux_hz_per_cm2=0.01)
        tracks = model.generate(5000, self.detectors, rng)
        sphere_center, sphere_radius = enclosing_sphere(self.detectors, padding_factor=1.01)

        distances = np.linalg.norm(tracks.origins - sphere_center[np.newaxis, :], axis=1)
        self.assertTrue(np.allclose(distances, sphere_radius))
        self.assertTrue(np.allclose(np.linalg.norm(tracks.directions, axis=1), 1.0))
        self.assertTrue(np.all(tracks.directions[:, 2] <= 0.0))

    def test_total_rate_hz_matches_flux_times_auxiliary_sphere_area_factor(self) -> None:
        """total_rate_hz must equal `(4/3) * pi * R^2 * flux_hz_per_cm2`."""
        model = CosmicSourceModel(model="cos2", flux_hz_per_cm2=0.01)
        _, sphere_radius = enclosing_sphere(self.detectors, padding_factor=1.01)

        expected = (4.0 / 3.0) * math.pi * sphere_radius**2 * 0.01
        self.assertAlmostEqual(model.total_rate_hz(self.detectors), expected)

    def test_unsupported_model_raises(self) -> None:
        """An unsupported cosmic angular model name must raise ValueError."""
        with self.assertRaises(ValueError):
            CosmicSourceModel(model="flat", flux_hz_per_cm2=0.01)


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
        """total_rate_hz for a uniform profile must equal flux times disk area."""
        model = BeamSourceModel(profile="uniform", center=(0.0, 0.0), size=(4.0,), flux_hz_per_cm2=10.0)
        expected = 10.0 * math.pi * 2.0**2
        self.assertAlmostEqual(model.total_rate_hz(self.detectors), expected)

    def test_gaussian_total_rate_hz_is_twice_flux_times_fwhm_ellipse_area(self) -> None:
        """total_rate_hz for a gaussian profile must equal twice flux times FWHM-ellipse area."""
        model = BeamSourceModel(
            profile="gaussian", center=(0.0, 0.0), size=(4.0, 2.0), flux_hz_per_cm2=10.0
        )
        expected = 2.0 * 10.0 * math.pi * 2.0 * 1.0
        self.assertAlmostEqual(model.total_rate_hz(self.detectors), expected)

    def test_gaussian_origins_never_exceed_spatial_bounds(self) -> None:
        """Truncated gaussian sampling must never place an origin outside spatial_bounds."""
        rng = np.random.default_rng(7)
        model = BeamSourceModel(
            profile="gaussian", center=(0.0, 0.0), size=(2.0, 3.0), flux_hz_per_cm2=10.0
        )
        tracks = model.generate(50000, self.detectors, rng)

        x_min, x_max, y_min, y_max, _, _ = model.spatial_bounds(self.detectors)
        self.assertTrue(np.all(tracks.origins[:, 0] >= x_min))
        self.assertTrue(np.all(tracks.origins[:, 0] <= x_max))
        self.assertTrue(np.all(tracks.origins[:, 1] >= y_min))
        self.assertTrue(np.all(tracks.origins[:, 1] <= y_max))


class ObjectSourceModelTests(unittest.TestCase):
    """Check one-sided disk sampling, hemisphere directions, and rate normalization."""

    def setUp(self) -> None:
        """Build a small detector stack shared by the object tests."""
        self.detectors = [Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 2.0], 1.0)]

    def test_origins_stay_on_the_disk_plane(self) -> None:
        """Object-source origins must lie on the configured disk surface."""
        rng = np.random.default_rng(3)
        model = ObjectSourceModel(
            center=(1.0, 2.0, 3.0),
            diameter=4.0,
            normal=(0.0, 0.0, 1.0),
            angular_model="uniform",
            front_emission_rate_hz=1.0,
        )
        tracks = model.generate(5000, self.detectors, rng)

        offsets = tracks.origins - np.array([1.0, 2.0, 3.0])
        radii = np.hypot(offsets[:, 0], offsets[:, 1])
        self.assertTrue(np.allclose(offsets[:, 2], 0.0))
        self.assertTrue(np.all(radii <= 2.0 + 1.0e-9))

    def test_directions_stay_in_the_forward_hemisphere(self) -> None:
        """Object-source directions must satisfy `direction dot normal > 0`."""
        rng = np.random.default_rng(4)
        model = ObjectSourceModel(
            center=(0.0, 0.0, 0.0),
            diameter=2.0,
            normal=(1.0, 1.0, 0.0),
            angular_model="uniform",
            front_emission_rate_hz=1.0,
        )
        tracks = model.generate(10000, self.detectors, rng)
        unit_normal = np.array((1.0, 1.0, 0.0), dtype=float) / math.sqrt(2.0)

        projections = tracks.directions @ unit_normal
        self.assertTrue(np.all(projections >= 0.0))
        self.assertAlmostEqual(float(np.mean(projections)), 0.5, delta=0.03)

    def test_cosine_weighted_directions_bias_toward_the_normal(self) -> None:
        """Cosine-weighted emission should favor larger `direction dot normal`."""
        rng = np.random.default_rng(5)
        model = ObjectSourceModel(
            center=(0.0, 0.0, 0.0),
            diameter=2.0,
            normal=(0.0, 0.0, 1.0),
            angular_model="cosine-weighted",
            front_emission_rate_hz=1.0,
        )
        tracks = model.generate(20000, self.detectors, rng)

        self.assertAlmostEqual(float(np.mean(tracks.directions[:, 2])), 2.0 / 3.0, delta=0.03)

    def test_total_rate_hz_equals_front_emission_rate(self) -> None:
        """total_rate_hz must equal the configured front-side emission rate."""
        model = ObjectSourceModel(
            center=(0.0, 0.0, 0.0),
            diameter=1.0,
            normal=(0.0, 0.0, 1.0),
            angular_model="uniform",
            front_emission_rate_hz=42.0,
        )
        self.assertEqual(model.total_rate_hz(self.detectors), 42.0)

    def test_invalid_angular_model_raises(self) -> None:
        """An unsupported object angular model must raise ValueError."""
        with self.assertRaises(ValueError):
            ObjectSourceModel(
                center=(0.0, 0.0, 0.0),
                diameter=1.0,
                normal=(0.0, 0.0, 1.0),
                angular_model="material-dependent",
                front_emission_rate_hz=1.0,
            )


class BuildSourceModelTests(unittest.TestCase):
    """Check the config-to-model dispatcher."""

    def test_dispatches_cosmic(self) -> None:
        """A CosmicSourceConfig should build a CosmicSourceModel."""
        config = CosmicSourceConfig(model="cos2", flux_hz_per_cm2=0.01)
        self.assertIsInstance(build_source_model(config), CosmicSourceModel)

    def test_dispatches_beam(self) -> None:
        """A BeamSourceConfig should build a BeamSourceModel."""
        config = BeamSourceConfig(profile="uniform", center=(0.0, 0.0), size=(1.0,), flux_hz_per_cm2=1.0)
        self.assertIsInstance(build_source_model(config), BeamSourceModel)

    def test_dispatches_object(self) -> None:
        """An ObjectSourceConfig should build an ObjectSourceModel."""
        config = ObjectSourceConfig(
            center=(0.0, 0.0, 0.0),
            diameter=1.0,
            normal=(0.0, 0.0, 1.0),
            angular_model="uniform",
            activity_bq=10.0,
            yield_per_decay=1.0,
            surface_emission_rate_hz=None,
        )
        self.assertIsInstance(build_source_model(config), ObjectSourceModel)
