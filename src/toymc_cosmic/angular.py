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
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Sample zenith angles in radians over the downward hemisphere; returns ndarray."""


class Cos2AngularModel(AngularModel):
    """Default angular model with `g(theta) = cos^2(theta)`."""

    def sample_theta(
        self,
        count: int,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Sample `theta` from the downward-hemisphere `cos^2(theta)` sky law; returns ndarray."""
        _validate_count(count)

        uniform_random = rng.uniform(0.0, 1.0, size=count)

        # For a sky intensity I(theta) proportional to cos^2(theta), the
        # incoming-direction marginal over the downward hemisphere is
        # p(theta) = 3 cos^2(theta) sin(theta), whose CDF inverts analytically.
        return np.arccos(np.cbrt(1.0 - uniform_random))


class TabulatedAngularModel(AngularModel):
    """Generic angular model built from a tabulated weight function.

    The callable passed here should implement `g(theta)` over the downward
    hemisphere. The physical sampling density is built internally as
    `g(theta) * sin(theta)`.
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
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Sample `theta` by numerically inverting a tabulated hemisphere CDF; returns ndarray."""
        _validate_count(count)

        theta_grid = np.linspace(0.0, 0.5 * math.pi, self.grid_size)
        model_weight = np.asarray(self.weight_function(theta_grid), dtype=float)
        if np.any(model_weight < 0.0):
            raise ValueError("Angular model weights must be non-negative.")

        physical_weight = model_weight * np.sin(theta_grid)

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


def _validate_count(count: int) -> None:
    """Validate a positive sample count; returns None."""
    if count <= 0:
        raise ValueError("count must be positive.")
