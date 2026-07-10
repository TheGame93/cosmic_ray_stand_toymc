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
CAMERA_FRAME_PADDING = 1.08
DEFAULT_VIEWPORT_ASPECT_RATIO = 4.0 / 3.0


def show_geometry_only(config: Config) -> None:
    """Open a static detector-only 3D scene without running the Monte Carlo."""
    gui_config = load_gui_config(config)
    plotter = build_plotter(config.detectors, gui_config)
    startup_camera_position = build_startup_camera_position(
        detector_scene_bounds(config.detectors),
        viewport_aspect_ratio=plotter_viewport_aspect_ratio(plotter),
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
    *,
    viewport_aspect_ratio: float = DEFAULT_VIEWPORT_ASPECT_RATIO,
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

    safe_aspect_ratio = max(float(viewport_aspect_ratio), 1.0e-6)
    direction = STARTUP_VIEW_DIRECTION / np.linalg.norm(STARTUP_VIEW_DIRECTION)
    view_up = np.array(STARTUP_VIEW_UP, dtype=float)
    view_right = np.cross(direction, view_up)
    view_right = view_right / np.linalg.norm(view_right)
    view_up_orthogonal = np.cross(view_right, direction)
    view_up_orthogonal = view_up_orthogonal / np.linalg.norm(view_up_orthogonal)

    # Fit the detector box itself, not the much larger generation or track
    # region. This keeps the stand large and readable in the window.
    corners = _scene_bounds_corners(scene_bounds) - scene_center
    half_width = float(np.max(np.abs(corners @ view_right)))
    half_height = float(np.max(np.abs(corners @ view_up_orthogonal)))
    half_width = max(half_width, 1.0e-6)
    half_height = max(half_height, 1.0e-6)

    vertical_view_angle_radians = math.radians(30.0)
    horizontal_view_angle_radians = 2.0 * math.atan(
        math.tan(vertical_view_angle_radians / 2.0) * safe_aspect_ratio
    )

    distance_for_height = half_height / math.tan(vertical_view_angle_radians / 2.0)
    distance_for_width = half_width / math.tan(horizontal_view_angle_radians / 2.0)
    camera_distance = max(
        MIN_CAMERA_DISTANCE,
        CAMERA_FRAME_PADDING * max(distance_for_height, distance_for_width),
    )
    camera_position = scene_center + direction * camera_distance

    return (
        tuple(float(component) for component in camera_position),
        tuple(float(component) for component in scene_center),
        STARTUP_VIEW_UP,
    )


def plotter_viewport_aspect_ratio(plotter: Any) -> float:
    """Return the current plotter width/height ratio or a deterministic fallback."""
    if hasattr(plotter, "window_size"):
        raw_window_size = plotter.window_size
        if (
            isinstance(raw_window_size, (tuple, list))
            and len(raw_window_size) == 2
            and float(raw_window_size[1]) > 0.0
        ):
            return float(raw_window_size[0]) / float(raw_window_size[1])

    return DEFAULT_VIEWPORT_ASPECT_RATIO


def _scene_bounds_corners(
    scene_bounds: tuple[float, float, float, float, float, float],
) -> np.ndarray:
    """Return the eight corners of an axis-aligned bounds box."""
    x_min, x_max, y_min, y_max, z_min, z_max = scene_bounds
    return np.array(
        [
            [x_min, y_min, z_min],
            [x_min, y_min, z_max],
            [x_min, y_max, z_min],
            [x_min, y_max, z_max],
            [x_max, y_min, z_min],
            [x_max, y_min, z_max],
            [x_max, y_max, z_min],
            [x_max, y_max, z_max],
        ],
        dtype=float,
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
