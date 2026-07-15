"""Pluggable source models that turn validated configs into track samples."""

from __future__ import annotations

from abc import ABC, abstractmethod
import math

import numpy as np

from .angular import Cos2AngularModel
from .config import BeamSourceConfig, CosmicSourceConfig, ObjectSourceConfig, SourceModelConfig
from .geometry import Detector, enclosing_sphere, min_reference_z, reference_z
from .tracks import Tracks


_FWHM_TO_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))
_GAUSSIAN_TRUNCATION_SIGMA_MULTIPLE = 5.0
_COSMIC_ENCLOSING_SPHERE_PADDING_FACTOR = 1.01


class SourceModel(ABC):
    """Abstract base class for pluggable source models."""

    @abstractmethod
    def generate(self, count: int, detectors: list[Detector], rng: np.random.Generator) -> Tracks:
        """Generate `count` source tracks; returns Tracks."""

    @abstractmethod
    def total_rate_hz(self, detectors: list[Detector]) -> float:
        """Return the total physical event rate represented by the sampling, in Hz."""

    @abstractmethod
    def spatial_bounds(
        self, detectors: list[Detector]
    ) -> tuple[float, float, float, float, float, float]:
        """Return the source footprint bounds `(xmin,xmax,ymin,ymax,zmin,zmax)`."""


class CosmicSourceModel(SourceModel):
    """Downward cosmic-ray source sampled from a padded enclosing sphere."""

    def __init__(self, model: str, flux_hz_per_cm2: float) -> None:
        """Store the cosmic source parameters and build the sky angular model."""
        self.model = model
        self.flux_hz_per_cm2 = flux_hz_per_cm2
        if model == "cos2":
            self.angular_model = Cos2AngularModel()
        else:
            raise ValueError(f"Unsupported cosmic angular model: {model}")

        self._cached_sphere: tuple[np.ndarray, float] | None = None

    def generate(self, count: int, detectors: list[Detector], rng: np.random.Generator) -> Tracks:
        """Sample tracks from an enclosing sphere; returns Tracks."""
        if count <= 0:
            raise ValueError("count must be positive.")

        sphere_center, sphere_radius = self._enclosing_sphere(detectors)

        theta = self.angular_model.sample_theta(count, rng)
        phi = rng.uniform(0.0, 2.0 * math.pi, size=count)

        sin_theta = np.sin(theta)
        directions = np.column_stack(
            (
                sin_theta * np.cos(phi),
                sin_theta * np.sin(phi),
                -np.cos(theta),
            )
        )

        impact_offsets = _sample_disk_offsets_perpendicular_to_vectors(directions, sphere_radius, rng)
        chord_lengths = np.sqrt(np.maximum(sphere_radius**2 - np.sum(impact_offsets**2, axis=1), 0.0))
        origins = sphere_center + impact_offsets - chord_lengths[:, np.newaxis] * directions
        return Tracks(origins=origins, directions=directions)

    def total_rate_hz(self, detectors: list[Detector]) -> float:
        """Return the auxiliary sphere-entry rate implied by the configured plane flux."""
        _, sphere_radius = self._enclosing_sphere(detectors)
        return (4.0 / 3.0) * math.pi * sphere_radius**2 * self.flux_hz_per_cm2

    def spatial_bounds(
        self, detectors: list[Detector]
    ) -> tuple[float, float, float, float, float, float]:
        """Return the enclosing sphere's axis-aligned bounding box."""
        sphere_center, sphere_radius = self._enclosing_sphere(detectors)
        return (
            float(sphere_center[0] - sphere_radius),
            float(sphere_center[0] + sphere_radius),
            float(sphere_center[1] - sphere_radius),
            float(sphere_center[1] + sphere_radius),
            float(sphere_center[2] - sphere_radius),
            float(sphere_center[2] + sphere_radius),
        )

    def _enclosing_sphere(self, detectors: list[Detector]) -> tuple[np.ndarray, float]:
        """Compute and cache the padded detector enclosing sphere; returns `(center, radius)`."""
        if self._cached_sphere is None:
            self._cached_sphere = enclosing_sphere(
                detectors,
                padding_factor=_COSMIC_ENCLOSING_SPHERE_PADDING_FACTOR,
            )
        return self._cached_sphere


class BeamSourceModel(SourceModel):
    """Directed beam source traveling in `+z` (upstream to downstream)."""

    def __init__(
        self,
        profile: str,
        center: tuple[float, float],
        size: tuple[float, ...],
        flux_hz_per_cm2: float,
    ) -> None:
        """Store the beam parameters."""
        if profile not in ("uniform", "gaussian"):
            raise ValueError(f"Unsupported beam profile: {profile}")

        self.profile = profile
        self.center = center
        self.size = size
        self.flux_hz_per_cm2 = flux_hz_per_cm2
        self._cached_min_reference_z: float | None = None

    def generate(self, count: int, detectors: list[Detector], rng: np.random.Generator) -> Tracks:
        """Sample tracks from the upstream face traveling in `+z`; returns Tracks."""
        if count <= 0:
            raise ValueError("count must be positive.")

        if self._cached_min_reference_z is None:
            self._cached_min_reference_z = min_reference_z(detectors)
        z_origin = self._cached_min_reference_z

        x_positions, y_positions = self._sample_transverse_positions(count, rng)
        z_positions = np.full(count, z_origin, dtype=float)

        origins = np.column_stack((x_positions, y_positions, z_positions))
        directions = np.zeros((count, 3), dtype=float)
        directions[:, 2] = 1.0
        return Tracks(origins=origins, directions=directions)

    def _uniform_radius(self) -> float:
        """Return the `uniform`-profile disk radius; returns float."""
        return 0.5 * self.size[0]

    def _gaussian_sigma(self) -> tuple[float, float]:
        """Return the `gaussian`-profile `(sigma_x, sigma_y)` derived from the FWHM."""
        return self.size[0] / _FWHM_TO_SIGMA, self.size[1] / _FWHM_TO_SIGMA

    def _sample_transverse_positions(
        self, count: int, rng: np.random.Generator
    ) -> tuple[np.ndarray, np.ndarray]:
        """Sample transverse `(x, y)` positions matching the configured profile."""
        if self.profile == "uniform":
            x_center, y_center = self.center
            radius = self._uniform_radius()
            r = radius * np.sqrt(rng.uniform(0.0, 1.0, size=count))
            phi = rng.uniform(0.0, 2.0 * math.pi, size=count)
            return x_center + r * np.cos(phi), y_center + r * np.sin(phi)

        return self._sample_gaussian_transverse_positions(count, rng)

    def _sample_gaussian_transverse_positions(
        self, count: int, rng: np.random.Generator
    ) -> tuple[np.ndarray, np.ndarray]:
        """Sample a truncated 2D gaussian beam spot; returns `(x_positions, y_positions)`."""
        x_center, y_center = self.center
        sigma_x, sigma_y = self._gaussian_sigma()

        x_positions = np.empty(count, dtype=float)
        y_positions = np.empty(count, dtype=float)
        pending_indices = np.arange(count)

        while pending_indices.size > 0:
            candidate_x = rng.normal(x_center, sigma_x, size=pending_indices.size)
            candidate_y = rng.normal(y_center, sigma_y, size=pending_indices.size)

            normalized_radius_sq = (
                ((candidate_x - x_center) / (_GAUSSIAN_TRUNCATION_SIGMA_MULTIPLE * sigma_x)) ** 2
                + ((candidate_y - y_center) / (_GAUSSIAN_TRUNCATION_SIGMA_MULTIPLE * sigma_y)) ** 2
            )
            accepted = normalized_radius_sq <= 1.0

            x_positions[pending_indices[accepted]] = candidate_x[accepted]
            y_positions[pending_indices[accepted]] = candidate_y[accepted]
            pending_indices = pending_indices[~accepted]

        return x_positions, y_positions

    def total_rate_hz(self, detectors: list[Detector]) -> float:
        """Return the source's total physical rate, in Hz."""
        if self.profile == "gaussian":
            return 2.0 * self.flux_hz_per_cm2 * self._footprint_area()
        return self.flux_hz_per_cm2 * self._footprint_area()

    def _footprint_area(self) -> float:
        """Return the beam footprint area used by the total-rate normalization; returns float."""
        if self.profile == "uniform":
            return math.pi * self._uniform_radius() ** 2
        return math.pi * (0.5 * self.size[0]) * (0.5 * self.size[1])

    def spatial_bounds(
        self, detectors: list[Detector]
    ) -> tuple[float, float, float, float, float, float]:
        """Return the beam footprint bounds from the upstream face to the far detector face."""
        x_center, y_center = self.center
        if self.profile == "uniform":
            half_x = half_y = self._uniform_radius()
        else:
            sigma_x, sigma_y = self._gaussian_sigma()
            half_x = _GAUSSIAN_TRUNCATION_SIGMA_MULTIPLE * sigma_x
            half_y = _GAUSSIAN_TRUNCATION_SIGMA_MULTIPLE * sigma_y

        z_near = min_reference_z(detectors)
        z_far = reference_z(detectors)
        return (x_center - half_x, x_center + half_x, y_center - half_y, y_center + half_y, z_near, z_far)


class ObjectSourceModel(SourceModel):
    """Mounted one-sided disk source emitting into a forward hemisphere."""

    def __init__(
        self,
        center: tuple[float, float, float],
        diameter: float,
        normal: tuple[float, float, float],
        angular_model: str,
        front_emission_rate_hz: float,
    ) -> None:
        """Store the disk-source parameters and normalize its emitting normal."""
        if angular_model not in ("uniform", "cosine-weighted"):
            raise ValueError(f"Unsupported object angular model: {angular_model}")

        self.center = np.asarray(center, dtype=float)
        self.diameter = diameter
        self.angular_model = angular_model
        self.front_emission_rate_hz = front_emission_rate_hz
        self.unit_normal = _normalize_vector(np.asarray(normal, dtype=float))
        basis_u, basis_v = _orthonormal_basis_from_unit_vectors(self.unit_normal[np.newaxis, :])
        self._basis_u = basis_u[0]
        self._basis_v = basis_v[0]

    def generate(self, count: int, detectors: list[Detector], rng: np.random.Generator) -> Tracks:
        """Sample emission points on the disk and forward directions; returns Tracks."""
        if count <= 0:
            raise ValueError("count must be positive.")

        origins = self._sample_positions(count, rng)
        directions = self._sample_directions(count, rng)
        return Tracks(origins=origins, directions=directions)

    def _sample_positions(self, count: int, rng: np.random.Generator) -> np.ndarray:
        """Sample emission points uniformly on the disk surface; returns ndarray."""
        radius = 0.5 * self.diameter
        r = radius * np.sqrt(rng.uniform(0.0, 1.0, size=count))
        phi = rng.uniform(0.0, 2.0 * math.pi, size=count)
        offsets = (
            (r * np.cos(phi))[:, np.newaxis] * self._basis_u[np.newaxis, :]
            + (r * np.sin(phi))[:, np.newaxis] * self._basis_v[np.newaxis, :]
        )
        return self.center[np.newaxis, :] + offsets

    def _sample_directions(self, count: int, rng: np.random.Generator) -> np.ndarray:
        """Sample forward-hemisphere directions for the configured angular model; returns ndarray."""
        if self.angular_model == "uniform":
            cos_theta = rng.uniform(0.0, 1.0, size=count)
        else:
            cos_theta = np.sqrt(rng.uniform(0.0, 1.0, size=count))

        sin_theta = np.sqrt(1.0 - cos_theta**2)
        phi = rng.uniform(0.0, 2.0 * math.pi, size=count)
        return (
            (sin_theta * np.cos(phi))[:, np.newaxis] * self._basis_u[np.newaxis, :]
            + (sin_theta * np.sin(phi))[:, np.newaxis] * self._basis_v[np.newaxis, :]
            + cos_theta[:, np.newaxis] * self.unit_normal[np.newaxis, :]
        )

    def total_rate_hz(self, detectors: list[Detector]) -> float:
        """Return the configured front-side particle emission rate, in Hz."""
        return self.front_emission_rate_hz

    def spatial_bounds(
        self, detectors: list[Detector]
    ) -> tuple[float, float, float, float, float, float]:
        """Return the oriented emitting disk's axis-aligned bounds."""
        radius = 0.5 * self.diameter
        half_extents = radius * np.sqrt(np.maximum(1.0 - self.unit_normal**2, 0.0))
        return (
            float(self.center[0] - half_extents[0]),
            float(self.center[0] + half_extents[0]),
            float(self.center[1] - half_extents[1]),
            float(self.center[1] + half_extents[1]),
            float(self.center[2] - half_extents[2]),
            float(self.center[2] + half_extents[2]),
        )


def _sample_disk_offsets_perpendicular_to_vectors(
    directions: np.ndarray,
    radius: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample uniform disk offsets perpendicular to unit directions; returns ndarray."""
    basis_u, basis_v = _orthonormal_basis_from_unit_vectors(directions)
    radial_distance = radius * np.sqrt(rng.uniform(0.0, 1.0, size=directions.shape[0]))
    azimuth = rng.uniform(0.0, 2.0 * math.pi, size=directions.shape[0])
    return (
        (radial_distance * np.cos(azimuth))[:, np.newaxis] * basis_u
        + (radial_distance * np.sin(azimuth))[:, np.newaxis] * basis_v
    )


def _orthonormal_basis_from_unit_vectors(unit_vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Build orthonormal bases perpendicular to unit vectors; returns `(basis_u, basis_v)`."""
    reference = np.tile(np.array((0.0, 0.0, 1.0), dtype=float), (unit_vectors.shape[0], 1))
    near_parallel_mask = np.abs(unit_vectors[:, 2]) > 0.9
    reference[near_parallel_mask] = np.array((1.0, 0.0, 0.0), dtype=float)

    basis_u = np.cross(reference, unit_vectors)
    basis_u /= np.linalg.norm(basis_u, axis=1)[:, np.newaxis]
    basis_v = np.cross(unit_vectors, basis_u)
    return basis_u, basis_v


def _normalize_vector(vector: np.ndarray) -> np.ndarray:
    """Normalize a non-zero vector; returns the normalized vector."""
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise ValueError("Vector must be non-zero.")
    return vector / norm


def build_source_model(source_config: SourceModelConfig) -> SourceModel:
    """Build the concrete SourceModel matching a validated source config."""
    if isinstance(source_config, CosmicSourceConfig):
        return CosmicSourceModel(
            model=source_config.model,
            flux_hz_per_cm2=source_config.flux_hz_per_cm2,
        )
    if isinstance(source_config, BeamSourceConfig):
        return BeamSourceModel(
            profile=source_config.profile,
            center=source_config.center,
            size=source_config.size,
            flux_hz_per_cm2=source_config.flux_hz_per_cm2,
        )
    if isinstance(source_config, ObjectSourceConfig):
        return ObjectSourceModel(
            center=source_config.center,
            diameter=source_config.diameter,
            normal=source_config.normal,
            angular_model=source_config.angular_model,
            front_emission_rate_hz=source_config.front_emission_rate_hz(),
        )
    raise ValueError(f"Unsupported source_model config type: {type(source_config).__name__}")
