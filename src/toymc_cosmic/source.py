"""Pluggable source models: turn a validated source config into (origin, direction) tracks."""

from __future__ import annotations

from abc import ABC, abstractmethod
import math

import numpy as np

from .angular import Cos2AngularModel
from .config import BeamSourceConfig, CosmicSourceConfig, ObjectSourceConfig, SourceModelConfig
from .geometry import Detector, generation_region, min_reference_z, reference_z
from .tracks import Tracks


_FWHM_TO_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))
_GAUSSIAN_DISPLAY_SIGMA_MULTIPLE = 3.0


class SourceModel(ABC):
    """Abstract base class for pluggable source models."""

    @abstractmethod
    def generate(self, count: int, detectors: list[Detector], rng: np.random.Generator) -> Tracks:
        """Generate `count` (origin, direction) tracks for this source."""

    @abstractmethod
    def total_rate_hz(self, detectors: list[Detector]) -> float:
        """Return the total physical event rate this source's sampling represents, in Hz."""

    @abstractmethod
    def spatial_bounds(
        self, detectors: list[Detector]
    ) -> tuple[float, float, float, float, float, float]:
        """Return this source's own axis-aligned footprint `(xmin,xmax,ymin,ymax,zmin,zmax)`."""


class CosmicSourceModel(SourceModel):
    """Downward cosmic-ray source: `cos^2` zenith sampling over a flat generation plane."""

    def __init__(self, theta_max: float, flux_hz_per_cm2: float) -> None:
        """Store the cosmic source parameters and build its angular model."""
        self.theta_max = theta_max
        self.flux_hz_per_cm2 = flux_hz_per_cm2
        self.angular_model = Cos2AngularModel()

    def generate(self, count: int, detectors: list[Detector], rng: np.random.Generator) -> Tracks:
        """Sample tracks from a flat plane above the detector stack; returns Tracks."""
        if count <= 0:
            raise ValueError("count must be positive.")

        x_min, x_max, y_min, y_max, _ = generation_region(detectors, self.theta_max)
        z_origin = reference_z(detectors)

        x_positions = rng.uniform(x_min, x_max, size=count)
        y_positions = rng.uniform(y_min, y_max, size=count)
        z_positions = np.full(count, z_origin, dtype=float)

        theta = self.angular_model.sample_theta(count, self.theta_max, rng)
        phi = rng.uniform(0.0, 2.0 * math.pi, size=count)

        sin_theta = np.sin(theta)
        direction_x = sin_theta * np.cos(phi)
        direction_y = sin_theta * np.sin(phi)
        direction_z = -np.cos(theta)

        origins = np.column_stack((x_positions, y_positions, z_positions))
        directions = np.column_stack((direction_x, direction_y, direction_z))
        return Tracks(origins=origins, directions=directions)

    def total_rate_hz(self, detectors: list[Detector]) -> float:
        """Return `flux_hz_per_cm2 * generation area`."""
        _, _, _, _, area_gen = generation_region(detectors, self.theta_max)
        return self.flux_hz_per_cm2 * area_gen

    def spatial_bounds(
        self, detectors: list[Detector]
    ) -> tuple[float, float, float, float, float, float]:
        """Return the generation rectangle at the flat origin plane's height."""
        x_min, x_max, y_min, y_max, _ = generation_region(detectors, self.theta_max)
        z_origin = reference_z(detectors)
        return (x_min, x_max, y_min, y_max, z_origin, z_origin)


class BeamSourceModel(SourceModel):
    """Directed beam source traveling in `+z` (upstream to downstream)."""

    def __init__(
        self,
        profile: str,
        center: tuple[float, float],
        size: tuple[float, ...],
        flux_hz_per_cm2: float,
    ) -> None:
        """Store the beam parameters; raises NotImplementedError for the unimplemented divergence profile."""
        if profile == "divergence":
            raise NotImplementedError(
                "source_model profile 'divergence' is not implemented yet; "
                "only 'uniform' and 'gaussian' beam profiles are wired up."
            )
        if profile not in ("uniform", "gaussian"):
            raise ValueError(f"Unsupported beam profile: {profile}")

        self.profile = profile
        self.center = center
        self.size = size
        self.flux_hz_per_cm2 = flux_hz_per_cm2

    def generate(self, count: int, detectors: list[Detector], rng: np.random.Generator) -> Tracks:
        """Sample tracks from the upstream face traveling in `+z`; returns Tracks."""
        if count <= 0:
            raise ValueError("count must be positive.")

        z_origin = min_reference_z(detectors)
        x_positions, y_positions = self._sample_transverse_positions(count, rng)
        z_positions = np.full(count, z_origin, dtype=float)

        origins = np.column_stack((x_positions, y_positions, z_positions))
        directions = np.zeros((count, 3), dtype=float)
        directions[:, 2] = 1.0
        return Tracks(origins=origins, directions=directions)

    def _sample_transverse_positions(
        self, count: int, rng: np.random.Generator
    ) -> tuple[np.ndarray, np.ndarray]:
        """Sample `(x, y)` transverse positions matching the configured profile."""
        x_center, y_center = self.center

        if self.profile == "uniform":
            radius = 0.5 * self.size[0]
            r = radius * np.sqrt(rng.uniform(0.0, 1.0, size=count))
            phi = rng.uniform(0.0, 2.0 * math.pi, size=count)
            return x_center + r * np.cos(phi), y_center + r * np.sin(phi)

        sigma_x = self.size[0] / _FWHM_TO_SIGMA
        sigma_y = self.size[1] / _FWHM_TO_SIGMA
        return rng.normal(x_center, sigma_x, size=count), rng.normal(y_center, sigma_y, size=count)

    def total_rate_hz(self, detectors: list[Detector]) -> float:
        """Return `flux_hz_per_cm2 * transverse footprint area`."""
        return self.flux_hz_per_cm2 * self._footprint_area()

    def _footprint_area(self) -> float:
        """Return the disk (`uniform`) or FWHM-ellipse (`gaussian`) footprint area."""
        if self.profile == "uniform":
            radius = 0.5 * self.size[0]
            return math.pi * radius**2
        return math.pi * (0.5 * self.size[0]) * (0.5 * self.size[1])

    def spatial_bounds(
        self, detectors: list[Detector]
    ) -> tuple[float, float, float, float, float, float]:
        """Return the beam's transverse footprint spanning from the upstream face to the far detector face."""
        x_center, y_center = self.center
        if self.profile == "uniform":
            half_x = half_y = 0.5 * self.size[0]
        else:
            half_x = _GAUSSIAN_DISPLAY_SIGMA_MULTIPLE * (self.size[0] / _FWHM_TO_SIGMA)
            half_y = _GAUSSIAN_DISPLAY_SIGMA_MULTIPLE * (self.size[1] / _FWHM_TO_SIGMA)

        z_near = min_reference_z(detectors)
        z_far = reference_z(detectors)
        return (x_center - half_x, x_center + half_x, y_center - half_y, y_center + half_y, z_near, z_far)


class ObjectSourceModel(SourceModel):
    """Radioactive point/volume source emitting isotropically over the full 4*pi sphere."""

    def __init__(
        self,
        shape: str,
        center: tuple[float, float, float],
        size: tuple[float, ...],
        activity_hz: float,
    ) -> None:
        """Store the object source parameters."""
        if shape not in ("sphere", "disk", "box"):
            raise ValueError(f"Unsupported object shape: {shape}")

        self.shape = shape
        self.center = center
        self.size = size
        self.activity_hz = activity_hz

    def generate(self, count: int, detectors: list[Detector], rng: np.random.Generator) -> Tracks:
        """Sample emission points inside the volume and isotropic directions; returns Tracks."""
        if count <= 0:
            raise ValueError("count must be positive.")

        origins = self._sample_positions(count, rng)
        directions = _sample_isotropic_directions(count, rng)
        return Tracks(origins=origins, directions=directions)

    def _sample_positions(self, count: int, rng: np.random.Generator) -> np.ndarray:
        """Sample emission points uniformly inside the configured volume."""
        center = np.array(self.center, dtype=float)

        if self.shape == "sphere":
            radius = 0.5 * self.size[0]
            unit_directions = _sample_isotropic_directions(count, rng)
            r = radius * np.cbrt(rng.uniform(0.0, 1.0, size=count))
            offsets = unit_directions * r[:, np.newaxis]
        elif self.shape == "disk":
            radius = 0.5 * self.size[0]
            half_height = 0.5 * self.size[1]
            r = radius * np.sqrt(rng.uniform(0.0, 1.0, size=count))
            phi = rng.uniform(0.0, 2.0 * math.pi, size=count)
            offsets = np.column_stack(
                (
                    r * np.cos(phi),
                    r * np.sin(phi),
                    rng.uniform(-half_height, half_height, size=count),
                )
            )
        else:
            half_sizes = np.array(self.size, dtype=float) * 0.5
            offsets = rng.uniform(-half_sizes, half_sizes, size=(count, 3))

        return offsets + center

    def total_rate_hz(self, detectors: list[Detector]) -> float:
        """Return the configured total activity, unchanged."""
        return self.activity_hz

    def spatial_bounds(
        self, detectors: list[Detector]
    ) -> tuple[float, float, float, float, float, float]:
        """Return the source volume's own axis-aligned bounding box."""
        x_center, y_center, z_center = self.center

        if self.shape == "sphere":
            half_x = half_y = half_z = 0.5 * self.size[0]
        elif self.shape == "disk":
            half_x = half_y = 0.5 * self.size[0]
            half_z = 0.5 * self.size[1]
        else:
            half_x, half_y, half_z = (0.5 * component for component in self.size)

        return (
            x_center - half_x,
            x_center + half_x,
            y_center - half_y,
            y_center + half_y,
            z_center - half_z,
            z_center + half_z,
        )


def _sample_isotropic_directions(count: int, rng: np.random.Generator) -> np.ndarray:
    """Sample unit direction vectors uniformly over the full 4*pi sphere."""
    cos_theta = rng.uniform(-1.0, 1.0, size=count)
    sin_theta = np.sqrt(1.0 - cos_theta**2)
    phi = rng.uniform(0.0, 2.0 * math.pi, size=count)

    direction_x = sin_theta * np.cos(phi)
    direction_y = sin_theta * np.sin(phi)
    direction_z = cos_theta
    return np.column_stack((direction_x, direction_y, direction_z))


def build_source_model(source_config: SourceModelConfig) -> SourceModel:
    """Build the concrete `SourceModel` matching a validated source config."""
    if isinstance(source_config, CosmicSourceConfig):
        return CosmicSourceModel(
            theta_max=source_config.theta_max,
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
            shape=source_config.shape,
            center=source_config.center,
            size=source_config.size,
            activity_hz=source_config.activity_hz,
        )
    raise ValueError(f"Unsupported source_model config type: {type(source_config).__name__}")
