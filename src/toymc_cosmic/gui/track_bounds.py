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

from ..geometry import Detector, bounding_box
from ..source import SourceModel


@dataclass(frozen=True)
class DisplayBounds:
    """Axis-aligned box used to clip the displayed event track."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float


def compute_display_bounds(detectors: list[Detector], source_model: SourceModel) -> DisplayBounds:
    """Compute the finite box used to clip displayed event tracks.

    Unions the detector bounding box with the source's own spatial footprint
    (`source_model.spatial_bounds`), then pads every axis by 10% of its span
    (or of the bound's own magnitude, whichever is larger, matching the
    padding this module has always used for `z`) -- one box shape for all
    source types instead of a cosmic-specific `theta_max` margin.
    """
    detector_bounds = _detector_bounds(detectors)
    source_bounds = source_model.spatial_bounds(detectors)
    unioned = _union_bounds(detector_bounds, source_bounds)
    return _pad_bounds(unioned)


def _detector_bounds(detectors: list[Detector]) -> tuple[float, float, float, float, float, float]:
    """Return the detector stack's own axis-aligned bounds."""
    x_min, x_max, y_min, y_max = bounding_box(detectors)
    z_min = min(float(detector.lower_bounds[2]) for detector in detectors)
    z_max = max(float(detector.upper_bounds[2]) for detector in detectors)
    return x_min, x_max, y_min, y_max, z_min, z_max


def _union_bounds(
    first: tuple[float, float, float, float, float, float],
    second: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    """Return the axis-aligned union of two `(xmin,xmax,ymin,ymax,zmin,zmax)` boxes."""
    return (
        min(first[0], second[0]),
        max(first[1], second[1]),
        min(first[2], second[2]),
        max(first[3], second[3]),
        min(first[4], second[4]),
        max(first[5], second[5]),
    )


def _pad_bounds(bounds: tuple[float, float, float, float, float, float]) -> DisplayBounds:
    """Pad every axis of a raw bounds tuple into a `DisplayBounds`."""
    x_min, x_max, y_min, y_max, z_min, z_max = bounds
    return DisplayBounds(
        x_min=_padded_min(x_min, x_max),
        x_max=_padded_max(x_min, x_max),
        y_min=_padded_min(y_min, y_max),
        y_max=_padded_max(y_min, y_max),
        z_min=_padded_min(z_min, z_max),
        z_max=_padded_max(z_min, z_max),
    )


def _padded_min(axis_min: float, axis_max: float) -> float:
    """Return `axis_min` padded outward by 10% of its span or magnitude."""
    span = axis_max - axis_min
    margin = 0.1 * max(abs(axis_min), span)
    return axis_min - margin


def _padded_max(axis_min: float, axis_max: float) -> float:
    """Return `axis_max` padded outward by 10% of its span or magnitude."""
    span = axis_max - axis_min
    margin = 0.1 * max(abs(axis_max), span)
    return axis_max + margin


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
