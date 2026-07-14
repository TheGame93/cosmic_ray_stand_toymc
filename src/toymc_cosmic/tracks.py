"""Track container used by the engine."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


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
