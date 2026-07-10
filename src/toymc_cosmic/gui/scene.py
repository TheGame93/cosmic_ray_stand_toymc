"""Static scene construction for the optional GUI."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..config import Config
from ..geometry import Detector
from .config import GUIConfig, load_gui_config


STARTUP_VIEW_DIRECTION = np.array([1.0, 1.0, 1.0], dtype=float)
STARTUP_VIEW_UP = (0.0, 0.0, 1.0)
MIN_CAMERA_DISTANCE = 5.0
CAMERA_DISTANCE_SCALE = 1.15


def show_geometry_only(config: Config) -> None:
    """Open a static detector-only 3D scene without running the Monte Carlo."""
    gui_config = load_gui_config(config)
    plotter = build_plotter(config.detectors, gui_config)
    startup_camera_position = build_startup_camera_position(
        detector_scene_bounds(config.detectors)
    )
    apply_camera_position(plotter, startup_camera_position)
    plotter.show()


def build_plotter(detectors: list[Detector], gui_config: GUIConfig) -> Any:
    """Create a PyVista plotter populated with detector meshes."""
    pv = _require_pyvista()

    plotter = pv.Plotter()
    plotter.set_background(gui_config.background_color)
    plotter.add_axes()
    render_detector_colors(plotter, detectors, gui_config, {})
    return plotter


def render_detector_colors(
    plotter: Any,
    detectors: list[Detector],
    gui_config: GUIConfig,
    event_colors: dict[str, Any],
    event_opacities: dict[str, float] | None = None,
) -> None:
    """Render or update detector boxes using either base or event colors."""
    pv = _require_pyvista()
    opacity_overrides = event_opacities or {}

    for detector in detectors:
        bounds = (
            float(detector.lower_bounds[0]),
            float(detector.upper_bounds[0]),
            float(detector.lower_bounds[1]),
            float(detector.upper_bounds[1]),
            float(detector.lower_bounds[2]),
            float(detector.upper_bounds[2]),
        )
        mesh = pv.Box(bounds=bounds)
        color = event_colors.get(detector.name, gui_config.detector_color(detector.name))
        opacity = opacity_overrides.get(detector.name, 0.35)
        plotter.add_mesh(
            mesh,
            color=color,
            opacity=opacity,
            show_edges=True,
            edge_color="white",
            name=f"detector_{detector.name}",
            reset_camera=False,
        )


def detector_scene_bounds(detectors: list[Detector]) -> tuple[float, float, float, float, float, float]:
    """Return the full axis-aligned bounds of the detector setup."""
    if not detectors:
        raise ValueError("At least one detector is required to define GUI scene bounds.")

    lower_stack = np.stack([detector.lower_bounds for detector in detectors])
    upper_stack = np.stack([detector.upper_bounds for detector in detectors])
    return (
        float(np.min(lower_stack[:, 0])),
        float(np.max(upper_stack[:, 0])),
        float(np.min(lower_stack[:, 1])),
        float(np.max(upper_stack[:, 1])),
        float(np.min(lower_stack[:, 2])),
        float(np.max(upper_stack[:, 2])),
    )


def build_startup_camera_position(
    scene_bounds: tuple[float, float, float, float, float, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    """Build a deterministic startup camera with direction parallel to `(1, 1, 1)`."""
    x_min, x_max, y_min, y_max, z_min, z_max = scene_bounds
    scene_center = np.array(
        [
            0.5 * (x_min + x_max),
            0.5 * (y_min + y_max),
            0.5 * (z_min + z_max),
        ],
        dtype=float,
    )
    extents = np.array(
        [
            x_max - x_min,
            y_max - y_min,
            z_max - z_min,
        ],
        dtype=float,
    )

    # Use a bounding-sphere approximation so the fixed view direction can frame
    # the full scene without asking PyVista to pick a new camera orientation.
    radius = 0.5 * float(np.linalg.norm(extents))
    radius = max(radius, 1.0)

    direction = STARTUP_VIEW_DIRECTION / np.linalg.norm(STARTUP_VIEW_DIRECTION)
    half_view_angle_radians = math.radians(15.0)
    camera_distance = max(
        MIN_CAMERA_DISTANCE,
        CAMERA_DISTANCE_SCALE * radius / math.tan(half_view_angle_radians),
    )
    camera_position = scene_center + direction * camera_distance

    return (
        tuple(float(component) for component in camera_position),
        tuple(float(component) for component in scene_center),
        STARTUP_VIEW_UP,
    )


def apply_camera_position(
    plotter: Any,
    camera_position: tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]],
) -> None:
    """Apply a fixed camera tuple without letting PyVista choose a new direction."""
    plotter.camera_position = camera_position

    if hasattr(plotter, "reset_camera_clipping_range"):
        plotter.reset_camera_clipping_range()
    elif hasattr(plotter, "renderer") and hasattr(plotter.renderer, "ResetCameraClippingRange"):
        plotter.renderer.ResetCameraClippingRange()


def _require_pyvista() -> Any:
    """Import PyVista only when the GUI is actually requested."""
    try:
        import pyvista as pv
    except ImportError as exc:
        raise RuntimeError(
            "GUI requested but PyVista is not installed. "
            "Use ./run_toymc.sh to create the local environment and install GUI dependencies."
        ) from exc
    return pv
