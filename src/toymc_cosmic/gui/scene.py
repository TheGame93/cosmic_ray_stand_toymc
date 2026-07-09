"""Static scene construction for the optional GUI."""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..geometry import Detector
from .config import GUIConfig, load_gui_config


def show_geometry_only(config: Config) -> None:
    """Open a static detector-only 3D scene without running the Monte Carlo."""
    gui_config = load_gui_config(config)
    plotter = build_plotter(config.detectors, gui_config)
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
) -> None:
    """Render or update detector boxes using either base or event colors."""
    pv = _require_pyvista()

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
        plotter.add_mesh(
            mesh,
            color=color,
            opacity=0.35,
            show_edges=True,
            edge_color="white",
            name=f"detector_{detector.name}",
            reset_camera=False,
        )


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
