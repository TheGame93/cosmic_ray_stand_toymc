"""Static scene construction for the optional GUI."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..config import BeamSourceConfig, Config, ObjectSourceConfig, SourceModelConfig
from ..geometry import Detector
from .config import GUIConfig, load_gui_config


STARTUP_VIEW_DIRECTION = np.array([1.0, 1.0, 1.0], dtype=float)
STARTUP_VIEW_UP = (0.0, 0.0, 1.0)
BEAM_VIEW_UP = (1.0, 0.0, 0.0)
MIN_CAMERA_DISTANCE = 5.0
CAMERA_FRAME_PADDING = 1.08
DEFAULT_VIEWPORT_ASPECT_RATIO = 4.0 / 3.0
DEFAULT_WINDOW_HEIGHT_PX = 900.0
DEFAULT_WINDOW_WIDTH_PX = 1600.0


def show_geometry_only(config: Config) -> None:
    """Open a static detector-only 3D scene without running the Monte Carlo."""
    gui_config = load_gui_config(config)
    plotter = build_plotter(config.detectors, gui_config, config.source_model)
    startup_camera_position = build_startup_camera_position(
        detector_scene_bounds(config.detectors),
        viewport_aspect_ratio=plotter_viewport_aspect_ratio(plotter),
        view_up=startup_view_up(config.source_model),
    )
    apply_camera_position(plotter, startup_camera_position)
    plotter.show()


def startup_view_up(source_config: SourceModelConfig) -> tuple[float, float, float]:
    """Return the startup camera's up vector for a source type.

    `beam` sources travel horizontally along `z`, so the default view flips
    to `x` pointing up (the `yz` plane becomes the horizontal ground plane,
    with the beam entering from the side) instead of the usual `z`-up view
    used for downward-traveling `cosmic`/`object` sources.
    """
    if isinstance(source_config, BeamSourceConfig):
        return BEAM_VIEW_UP
    return STARTUP_VIEW_UP


def build_plotter(
    detectors: list[Detector],
    gui_config: GUIConfig,
    source_config: SourceModelConfig,
    *,
    reserve_bottom_px: float = 0.0,
    shift_axes_right_px: float = 0.0,
) -> Any:
    """Create a PyVista plotter populated with detector meshes.

    `reserve_bottom_px` optionally shifts the default bottom-left axes
    triad upward by that many pixels, freeing deterministic room beneath
    it for the event display's stacked button row and key-hint text (see
    `EventDisplayController.__init__` in `viewer.py`). `shift_axes_right_px`
    optionally nudges the triad sideways by that many pixels (negative
    moves it left). `show_geometry_only` always uses the defaults `0.0`,
    which reproduce today's unshifted axes exactly -- that mode has no
    buttons or overlay text competing for that corner.
    """
    pv = _require_pyvista()

    plotter = pv.Plotter()
    plotter.set_background(gui_config.background_color)

    if reserve_bottom_px > 0.0 or shift_axes_right_px != 0.0:
        # Only recompute the viewport when a caller actually needs it
        # shifted, so geometry-only mode keeps calling `add_axes()` with
        # no arguments, exactly as before, rather than an
        # equivalent-but-different explicit `viewport=` kwarg.
        window_height_px = plotter_window_height_px(plotter)
        window_width_px = plotter_window_width_px(plotter)
        plotter.add_axes(
            viewport=compute_axes_viewport(
                reserve_bottom_px,
                window_height_px,
                shift_right_px=shift_axes_right_px,
                window_width_px=window_width_px,
            )
        )
    else:
        plotter.add_axes()

    render_detector_colors(plotter, detectors, gui_config, {})
    render_source_shape(plotter, source_config, gui_config)
    return plotter


def render_source_shape(plotter: Any, source_config: SourceModelConfig, gui_config: GUIConfig) -> None:
    """Render the source volume once for `object`-type sources; no-op otherwise."""
    if not isinstance(source_config, ObjectSourceConfig):
        return

    pv = _require_pyvista()
    center = source_config.center
    size = source_config.size

    if source_config.shape == "sphere":
        mesh = pv.Sphere(radius=0.5 * size[0], center=center)
    elif source_config.shape == "disk":
        mesh = pv.Cylinder(center=center, direction=(0.0, 0.0, 1.0), radius=0.5 * size[0], height=size[1])
    else:
        mesh = pv.Box(
            bounds=(
                center[0] - 0.5 * size[0],
                center[0] + 0.5 * size[0],
                center[1] - 0.5 * size[1],
                center[1] + 0.5 * size[1],
                center[2] - 0.5 * size[2],
                center[2] + 0.5 * size[2],
            )
        )

    plotter.add_mesh(
        mesh,
        color=gui_config.source_color,
        opacity=gui_config.source_opacity,
        name="source_shape",
        reset_camera=False,
    )


def compute_axes_viewport(
    reserve_bottom_px: float,
    window_height_px: float,
    *,
    shift_right_px: float = 0.0,
    window_width_px: float = 1.0,
) -> tuple[float, float, float, float]:
    """Return the (xstart, ystart, xend, yend) axes viewport, shifted from PyVista's default.

    PyVista's default axes viewport is the bottom-left `(0, 0, 0.2, 0.2)`
    square of the render window, expressed in normalized (0 to 1)
    coordinates with the same bottom-left origin VTK uses everywhere in
    this project -- see also the button widgets' `PlaceWidget` calls in
    `viewer.py`, which use that same origin convention but in absolute
    pixel ("display") coordinates instead of normalized fractions.

    We keep the triad's 0.2 x 0.2 size unchanged and only shift its
    position, converting each requested pixel budget into a fraction of
    the *matching* window dimension (vertical shift as a fraction of
    height, horizontal shift as a fraction of width) at the moment this
    runs (right after `pv.Plotter()` construction, before `.show()`).
    `window_width_px` is only actually used when `shift_right_px` is
    non-zero, so its harmless default of `1.0` never causes a division
    error for the common vertical-only case.

    This is only exact at that one window size: if the user resizes the
    window afterward, this normalized-fraction axes triad rescales with
    the new window dimensions while the pixel-positioned button row and
    key-hint text do not, so on an unusually small resized window the two
    could end up overlapping. This mirrors a pre-existing limitation
    already accepted in this file (the axes triad's on-screen footprint
    was always only an approximation at one assumed window size) and is
    not fixed here.
    """
    if reserve_bottom_px < 0.0:
        raise ValueError("reserve_bottom_px must not be negative.")
    if window_height_px <= 0.0:
        raise ValueError("window_height_px must be positive to compute the axes viewport.")
    if shift_right_px != 0.0 and window_width_px <= 0.0:
        raise ValueError("window_width_px must be positive to shift the axes viewport horizontally.")

    bottom_fraction = reserve_bottom_px / window_height_px
    left_fraction = shift_right_px / window_width_px
    return (left_fraction, bottom_fraction, left_fraction + 0.2, bottom_fraction + 0.2)


def plotter_window_height_px(plotter: Any) -> float:
    """Return the plotter's current window height in pixels, or a safe fallback.

    Mirrors the defensive handling in `plotter_viewport_aspect_ratio` below:
    some PyVista/VTK backends may not expose a valid `window_size`
    immediately after construction. Falling back to
    `DEFAULT_WINDOW_HEIGHT_PX` keeps axes placement deterministic instead
    of raising here.
    """
    if hasattr(plotter, "window_size"):
        raw_window_size = plotter.window_size
        if (
            isinstance(raw_window_size, (tuple, list))
            and len(raw_window_size) == 2
            and float(raw_window_size[1]) > 0.0
        ):
            return float(raw_window_size[1])
    return DEFAULT_WINDOW_HEIGHT_PX


def plotter_window_width_px(plotter: Any) -> float:
    """Return the plotter's current window width in pixels, or a safe fallback.

    Mirrors `plotter_window_height_px` above, for the horizontal axes shift.
    """
    if hasattr(plotter, "window_size"):
        raw_window_size = plotter.window_size
        if (
            isinstance(raw_window_size, (tuple, list))
            and len(raw_window_size) == 2
            and float(raw_window_size[0]) > 0.0
        ):
            return float(raw_window_size[0])
    return DEFAULT_WINDOW_WIDTH_PX


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
    view_up: tuple[float, float, float] = STARTUP_VIEW_UP,
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
    view_up_array = np.array(view_up, dtype=float)
    view_right = np.cross(direction, view_up_array)
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
        view_up,
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
