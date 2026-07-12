"""Finite display-box geometry for the event-display GUI's track segments.

Pure geometry/math -- no PyVista here. The event display draws a finite
line segment for each track (an infinite line is not useful on screen), so
this module computes the clipping box from the detector setup and clips a
given origin/direction into a segment inside it. See `gui/viewer.py` for
the controller that turns the clipped segment into an actual rendered
line.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ..geometry import Detector, generation_region


@dataclass(frozen=True)
class DisplayBounds:
    """Axis-aligned box used to clip the displayed event track."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float


def compute_display_bounds(detectors: list[Detector], theta_max: float) -> DisplayBounds:
    """Compute the finite box used to clip displayed event tracks."""
    x_min, x_max, y_min, y_max, _ = generation_region(detectors, theta_max)
    z_lower_bounds = [float(detector.lower_bounds[2]) for detector in detectors]
    z_upper_bounds = [float(detector.upper_bounds[2]) for detector in detectors]
    min_z = min(z_lower_bounds)
    max_z = max(z_upper_bounds)
    vertical_span = max_z - min_z

    top_margin = 0.1 * max(abs(max_z), vertical_span)
    bottom_margin = 0.1 * max(abs(min_z), vertical_span)

    return DisplayBounds(
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        z_min=min_z - bottom_margin,
        z_max=max_z + top_margin,
    )


def clip_line_to_bounds(
    origin: np.ndarray,
    direction: np.ndarray,
    bounds: DisplayBounds,
) -> tuple[np.ndarray, np.ndarray]:
    """Clip an infinite line to the finite display box."""
    t_min = -math.inf
    t_max = math.inf

    axis_bounds = (
        (bounds.x_min, bounds.x_max),
        (bounds.y_min, bounds.y_max),
        (bounds.z_min, bounds.z_max),
    )

    for axis_index, (axis_min, axis_max) in enumerate(axis_bounds):
        axis_origin = float(origin[axis_index])
        axis_direction = float(direction[axis_index])

        if axis_direction == 0.0:
            if axis_origin < axis_min or axis_origin > axis_max:
                raise ValueError("Track does not intersect the display bounds.")
            continue

        t_first = (axis_min - axis_origin) / axis_direction
        t_second = (axis_max - axis_origin) / axis_direction
        axis_t_min = min(t_first, t_second)
        axis_t_max = max(t_first, t_second)

        t_min = max(t_min, axis_t_min)
        t_max = min(t_max, axis_t_max)

    if t_min > t_max:
        raise ValueError("Track does not intersect the display bounds.")

    return origin + t_min * direction, origin + t_max * direction
