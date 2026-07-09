"""Detector response helpers."""

from __future__ import annotations

import numpy as np


def apply_response(
    crossed: np.ndarray,
    efficiencies: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Apply independent Bernoulli firing to every geometric crossing."""
    if crossed.ndim != 2:
        raise ValueError("crossed must have shape (n_events, n_detectors).")

    efficiency_array = np.asarray(efficiencies, dtype=float)
    if efficiency_array.shape != (crossed.shape[1],):
        raise ValueError("efficiencies must have shape (n_detectors,).")

    random_draws = rng.uniform(0.0, 1.0, size=crossed.shape)
    fired = random_draws < efficiency_array[np.newaxis, :]
    return crossed & fired
