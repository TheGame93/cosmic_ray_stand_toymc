"""Track generation helpers for the engine."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .angular import AngularModel
from .geometry import Detector, generation_region, reference_z


@dataclass
class Tracks:
    """Generated straight-line tracks for the Monte Carlo.

    Attributes:
        origins: Array with shape `(n_events, 3)` storing `(x, y, z)` origins.
        directions: Array with shape `(n_events, 3)` storing unit direction vectors.
    """

    origins: np.ndarray
    directions: np.ndarray

    def __post_init__(self) -> None:
        """Validate the track container arrays."""
        if self.origins.ndim != 2 or self.origins.shape[1] != 3:
            raise ValueError("Track origins must have shape (n_events, 3).")
        if self.directions.ndim != 2 or self.directions.shape[1] != 3:
            raise ValueError("Track directions must have shape (n_events, 3).")
        if self.origins.shape[0] != self.directions.shape[0]:
            raise ValueError("Track origins and directions must have matching event counts.")


def generate_tracks(
    count: int,
    detectors: list[Detector],
    theta_max: float,
    angular_model: AngularModel,
    rng: np.random.Generator,
) -> Tracks:
    """Generate straight downward tracks for the Monte Carlo."""
    if count <= 0:
        raise ValueError("count must be positive.")

    x_min, x_max, y_min, y_max, _ = generation_region(detectors, theta_max)
    z_origin = reference_z(detectors)

    x_positions = rng.uniform(x_min, x_max, size=count)
    y_positions = rng.uniform(y_min, y_max, size=count)
    z_positions = np.full(count, z_origin, dtype=float)

    theta = angular_model.sample_theta(count, theta_max, rng)
    phi = rng.uniform(0.0, 2.0 * math.pi, size=count)

    sin_theta = np.sin(theta)
    direction_x = sin_theta * np.cos(phi)
    direction_y = sin_theta * np.sin(phi)
    direction_z = -np.cos(theta)

    origins = np.column_stack((x_positions, y_positions, z_positions))
    directions = np.column_stack((direction_x, direction_y, direction_z))
    return Tracks(origins=origins, directions=directions)
