"""Angular models for downward cosmic-ray track generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
import math
from typing import Callable

import numpy as np


class AngularModel(ABC):
    """Abstract base class for pluggable angular models."""

    @abstractmethod
    def sample_theta(
        self,
        count: int,
        theta_max: float,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Sample zenith angles in radians over the interval `[0, theta_max]`."""


class Cos2AngularModel(AngularModel):
    """Default angular model with `g(theta) = cos^2(theta)`."""

    def sample_theta(
        self,
        count: int,
        theta_max: float,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Sample `theta` using the closed-form inverse CDF for the cos^2 model."""
        _validate_theta_inputs(count, theta_max)

        cos_theta_max = math.cos(theta_max)
        normalization_span = 1.0 - cos_theta_max**4

        uniform_random = rng.uniform(0.0, 1.0, size=count)

        # The physical rate density is proportional to cos^3(theta) * sin(theta).
        # Its cumulative distribution can be inverted analytically, which keeps
        # the implementation exact and easy to explain.
        inner_term = 1.0 - uniform_random * normalization_span
        return np.arccos(np.power(inner_term, 0.25))


class TabulatedAngularModel(AngularModel):
    """Generic angular model built from a tabulated weight function.

    The callable passed here should implement `g(theta)`. The physical sampling
    density is built internally as `g(theta) * cos(theta) * sin(theta)`.
    """

    def __init__(self, weight_function: Callable[[np.ndarray], np.ndarray], grid_size: int = 4097) -> None:
        """Store the weight function and the integration grid size."""
        if grid_size < 3:
            raise ValueError("grid_size must be at least 3.")
        self.weight_function = weight_function
        self.grid_size = grid_size

    def sample_theta(
        self,
        count: int,
        theta_max: float,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Sample `theta` by numerically inverting a tabulated CDF."""
        _validate_theta_inputs(count, theta_max)

        theta_grid = np.linspace(0.0, theta_max, self.grid_size)
        model_weight = np.asarray(self.weight_function(theta_grid), dtype=float)
        if np.any(model_weight < 0.0):
            raise ValueError("Angular model weights must be non-negative.")

        physical_weight = model_weight * np.cos(theta_grid) * np.sin(theta_grid)

        # We use a trapezoidal cumulative integral because it is easy to read
        # and does not require additional dependencies.
        cdf = np.zeros_like(theta_grid)
        for index in range(1, len(theta_grid)):
            delta_theta = theta_grid[index] - theta_grid[index - 1]
            left_weight = physical_weight[index - 1]
            right_weight = physical_weight[index]
            cdf[index] = cdf[index - 1] + 0.5 * delta_theta * (left_weight + right_weight)

        normalization = cdf[-1]
        if normalization <= 0.0:
            raise ValueError("Angular model normalization must be positive.")

        cdf /= normalization
        random_values = rng.uniform(0.0, 1.0, size=count)
        return np.interp(random_values, cdf, theta_grid)


def _validate_theta_inputs(count: int, theta_max: float) -> None:
    """Validate shared angular sampling inputs."""
    if count <= 0:
        raise ValueError("count must be positive.")
    if not 0.0 < theta_max < (0.5 * math.pi):
        raise ValueError("theta_max must be between 0 and pi/2.")
