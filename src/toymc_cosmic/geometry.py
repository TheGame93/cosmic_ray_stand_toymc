"""Geometry helpers for axis-aligned detector volumes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Detector:
    """Axis-aligned detector volume used by the engine.

    Attributes:
        name: Unique detector identifier used in logic expressions.
        center: Detector center as a 3-element numpy array `(x, y, z)`.
        size: Detector size as a 3-element numpy array `(dx, dy, dz)`.
        efficiency: Independent Bernoulli firing probability after a crossing.
    """

    name: str
    center: np.ndarray
    size: np.ndarray
    efficiency: float

    def __post_init__(self) -> None:
        """Normalize array-like inputs and validate basic detector fields."""
        center_array = np.asarray(self.center, dtype=float)
        size_array = np.asarray(self.size, dtype=float)

        if center_array.shape != (3,):
            raise ValueError("Detector center must have exactly three elements.")
        if size_array.shape != (3,):
            raise ValueError("Detector size must have exactly three elements.")
        if np.any(size_array <= 0.0):
            raise ValueError("Detector sizes must be strictly positive.")
        if not 0.0 <= float(self.efficiency) <= 1.0:
            raise ValueError("Detector efficiency must be between 0 and 1.")
        if not self.name:
            raise ValueError("Detector name must be a non-empty string.")

        object.__setattr__(self, "center", center_array)
        object.__setattr__(self, "size", size_array)
        object.__setattr__(self, "efficiency", float(self.efficiency))

    @property
    def lower_bounds(self) -> np.ndarray:
        """Return the detector lower bounds `(xmin, ymin, zmin)`."""
        return self.center - 0.5 * self.size

    @property
    def upper_bounds(self) -> np.ndarray:
        """Return the detector upper bounds `(xmax, ymax, zmax)`."""
        return self.center + 0.5 * self.size


def bounding_box(detectors: list[Detector]) -> tuple[float, float, float, float]:
    """Return the global `(xmin, xmax, ymin, ymax)` detector bounding box."""
    _require_detectors(detectors)

    lower_stack = np.stack([detector.lower_bounds for detector in detectors])
    upper_stack = np.stack([detector.upper_bounds for detector in detectors])

    xmin = float(np.min(lower_stack[:, 0]))
    xmax = float(np.max(upper_stack[:, 0]))
    ymin = float(np.min(lower_stack[:, 1]))
    ymax = float(np.max(upper_stack[:, 1]))
    return xmin, xmax, ymin, ymax


def bounding_box_3d(detectors: list[Detector]) -> tuple[float, float, float, float, float, float]:
    """Return the global `(xmin, xmax, ymin, ymax, zmin, zmax)` detector bounding box."""
    _require_detectors(detectors)

    lower_stack = np.stack([detector.lower_bounds for detector in detectors])
    upper_stack = np.stack([detector.upper_bounds for detector in detectors])

    xmin = float(np.min(lower_stack[:, 0]))
    xmax = float(np.max(upper_stack[:, 0]))
    ymin = float(np.min(lower_stack[:, 1]))
    ymax = float(np.max(upper_stack[:, 1]))
    zmin = float(np.min(lower_stack[:, 2]))
    zmax = float(np.max(upper_stack[:, 2]))
    return xmin, xmax, ymin, ymax, zmin, zmax


def enclosing_sphere(detectors: list[Detector], padding_factor: float = 1.01) -> tuple[np.ndarray, float]:
    """Return the detector-stack enclosing sphere center and padded radius."""
    if padding_factor <= 1.0:
        raise ValueError("padding_factor must be greater than 1.0.")

    xmin, xmax, ymin, ymax, zmin, zmax = bounding_box_3d(detectors)
    center = np.array(
        (
            0.5 * (xmin + xmax),
            0.5 * (ymin + ymax),
            0.5 * (zmin + zmax),
        ),
        dtype=float,
    )
    diagonal = np.array((xmax - xmin, ymax - ymin, zmax - zmin), dtype=float)
    radius = 0.5 * float(np.linalg.norm(diagonal)) * padding_factor
    return center, radius


def reference_z(detectors: list[Detector]) -> float:
    """Return the highest detector top face used as the track origin plane."""
    _require_detectors(detectors)
    return max(float(detector.upper_bounds[2]) for detector in detectors)


def min_reference_z(detectors: list[Detector]) -> float:
    """Return the lowest detector bottom face used as the beam upstream origin plane."""
    _require_detectors(detectors)
    return min(float(detector.lower_bounds[2]) for detector in detectors)


def intersect(
    origins: np.ndarray,
    directions: np.ndarray,
    detectors: list[Detector],
) -> np.ndarray:
    """Return a boolean crossing matrix with shape `(n_events, n_detectors)`.

    A crossing is counted only when the track has a strictly positive path
    length inside the detector volume. Surface-only, edge-only, and corner-only
    touches are excluded.
    """

    _require_detectors(detectors)
    _validate_track_arrays(origins, directions)

    event_count = origins.shape[0]
    detector_count = len(detectors)
    crossed_matrix = np.zeros((event_count, detector_count), dtype=bool)

    for detector_index, detector in enumerate(detectors):
        lower = detector.lower_bounds
        upper = detector.upper_bounds

        # We track the interval of ray parameters `t` that remain inside all
        # processed slabs. The final overlap of these intervals determines the
        # non-zero path length inside the box.
        t_enter = np.full(event_count, -np.inf, dtype=float)
        t_exit = np.full(event_count, np.inf, dtype=float)
        is_still_valid = np.ones(event_count, dtype=bool)

        for axis_index in range(3):
            origin_axis = origins[:, axis_index]
            direction_axis = directions[:, axis_index]
            axis_low = lower[axis_index]
            axis_high = upper[axis_index]

            moving_mask = direction_axis != 0.0
            stationary_mask = ~moving_mask

            if np.any(moving_mask):
                # For a moving coordinate, compute when the ray enters and exits
                # the current slab. These times shrink the global valid interval.
                t_first = (axis_low - origin_axis[moving_mask]) / direction_axis[moving_mask]
                t_second = (axis_high - origin_axis[moving_mask]) / direction_axis[moving_mask]

                axis_enter = np.minimum(t_first, t_second)
                axis_exit = np.maximum(t_first, t_second)

                t_enter[moving_mask] = np.maximum(t_enter[moving_mask], axis_enter)
                t_exit[moving_mask] = np.minimum(t_exit[moving_mask], axis_exit)

            if np.any(stationary_mask):
                # If the track never moves along this axis, it must already be
                # strictly inside the slab. Being exactly on the boundary would
                # mean the track only rides the detector surface, which should
                # not count as a positive path length crossing.
                stationary_origin = origin_axis[stationary_mask]
                outside_or_on_boundary = (stationary_origin <= axis_low) | (stationary_origin >= axis_high)
                invalid_indices = np.where(stationary_mask)[0][outside_or_on_boundary]
                is_still_valid[invalid_indices] = False

        crossed_matrix[:, detector_index] = is_still_valid & (t_enter < t_exit) & (t_exit > 0.0)

    return crossed_matrix


def _require_detectors(detectors: list[Detector]) -> None:
    """Raise if an operation that needs detectors is called with none."""
    if not detectors:
        raise ValueError("At least one detector is required.")


def _validate_track_arrays(origins: np.ndarray, directions: np.ndarray) -> None:
    """Validate the track arrays used by the intersection routine."""
    if origins.ndim != 2 or origins.shape[1] != 3:
        raise ValueError("Origins must have shape (n_events, 3).")
    if directions.ndim != 2 or directions.shape[1] != 3:
        raise ValueError("Directions must have shape (n_events, 3).")
    if origins.shape[0] != directions.shape[0]:
        raise ValueError("Origins and directions must contain the same number of events.")
