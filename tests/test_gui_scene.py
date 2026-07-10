"""Tests for GUI scene helpers that can run without a live PyVista window."""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from toymc_cosmic.geometry import Detector
from toymc_cosmic.gui.config import GUIConfig
from toymc_cosmic.gui.scene import (
    DEFAULT_VIEWPORT_ASPECT_RATIO,
    STARTUP_VIEW_DIRECTION,
    STARTUP_VIEW_UP,
    apply_camera_position,
    build_startup_camera_position,
    plotter_viewport_aspect_ratio,
    render_detector_colors,
    show_geometry_only,
)


class GuiSceneTests(unittest.TestCase):
    """Check detector color and opacity wiring for the GUI scene layer."""

    def test_build_startup_camera_position_uses_center_direction_and_view_up(self) -> None:
        """The startup camera should look from the `(1, 1, 1)` direction with `z` up."""
        camera_position = build_startup_camera_position((-2.0, 4.0, 1.0, 7.0, -3.0, 9.0))

        position, focal_point, view_up = camera_position
        direction = np.array(position) - np.array(focal_point)
        unit_direction = direction / np.linalg.norm(direction)
        expected_direction = STARTUP_VIEW_DIRECTION / np.linalg.norm(STARTUP_VIEW_DIRECTION)

        self.assertTrue(np.allclose(focal_point, (1.0, 4.0, 3.0)))
        self.assertTrue(np.allclose(unit_direction, expected_direction))
        self.assertEqual(view_up, STARTUP_VIEW_UP)

    def test_build_startup_camera_position_zoom_depends_on_detector_bounds_not_large_generation_area(self) -> None:
        """A tighter detector box should produce a much closer camera than a huge framing box."""
        tight_camera = build_startup_camera_position(
            (-1.0, 1.0, -1.0, 1.0, 9.5, 10.5),
            viewport_aspect_ratio=4.0 / 3.0,
        )
        wide_camera = build_startup_camera_position(
            (-40.0, 40.0, -40.0, 40.0, 0.0, 20.0),
            viewport_aspect_ratio=4.0 / 3.0,
        )

        tight_distance = np.linalg.norm(np.array(tight_camera[0]) - np.array(tight_camera[1]))
        wide_distance = np.linalg.norm(np.array(wide_camera[0]) - np.array(wide_camera[1]))

        self.assertLess(tight_distance, wide_distance / 5.0)

    def test_apply_camera_position_updates_clipping_range(self) -> None:
        """Applying a fixed camera should not ask PyVista to choose a new view."""
        plotter = FakePlotter()
        camera_position = ((9.0, 9.0, 9.0), (1.0, 2.0, 3.0), (0.0, 0.0, 1.0))

        apply_camera_position(plotter, camera_position)

        self.assertEqual(plotter.camera_position, camera_position)
        self.assertEqual(plotter.reset_camera_clipping_range_calls, 1)

    def test_plotter_viewport_aspect_ratio_uses_window_size_or_default(self) -> None:
        """Viewport aspect should prefer the plotter window size but stay deterministic."""
        explicit_ratio_plotter = mock.Mock(window_size=(1600, 900))
        fallback_ratio_plotter = mock.Mock()
        del fallback_ratio_plotter.window_size

        self.assertAlmostEqual(plotter_viewport_aspect_ratio(explicit_ratio_plotter), 1600.0 / 900.0)
        self.assertEqual(plotter_viewport_aspect_ratio(fallback_ratio_plotter), DEFAULT_VIEWPORT_ASPECT_RATIO)

    @mock.patch("toymc_cosmic.gui.scene._require_pyvista")
    def test_render_detector_colors_applies_color_and_opacity_overrides(
        self,
        require_pyvista_mock: mock.Mock,
    ) -> None:
        """Per-detector event colors and opacities should both reach add_mesh."""
        require_pyvista_mock.return_value = FakePyVistaModule()
        plotter = FakePlotter()
        detectors = [
            Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 1.0], 1.0),
            Detector("D1", [0.0, 0.0, 8.0], [2.0, 2.0, 1.0], 1.0),
        ]

        render_detector_colors(
            plotter=plotter,
            detectors=detectors,
            gui_config=self._gui_config(),
            event_colors={"T1": "green"},
            event_opacities={"T1": 0.35, "D1": 0.05},
        )

        self.assertEqual(plotter.mesh_calls[0]["color"], "green")
        self.assertEqual(plotter.mesh_calls[0]["opacity"], 0.35)
        self.assertEqual(plotter.mesh_calls[1]["color"], "gray")
        self.assertEqual(plotter.mesh_calls[1]["opacity"], 0.05)

    @mock.patch("toymc_cosmic.gui.scene._require_pyvista")
    def test_render_detector_colors_uses_default_opacity_without_override(
        self,
        require_pyvista_mock: mock.Mock,
    ) -> None:
        """Geometry-only rendering should keep the normal detector opacity."""
        require_pyvista_mock.return_value = FakePyVistaModule()
        plotter = FakePlotter()
        detectors = [Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 1.0], 1.0)]

        render_detector_colors(
            plotter=plotter,
            detectors=detectors,
            gui_config=self._gui_config(),
            event_colors={},
        )

        self.assertEqual(plotter.mesh_calls[0]["opacity"], 0.35)

    @mock.patch("toymc_cosmic.gui.scene.build_plotter")
    @mock.patch("toymc_cosmic.gui.scene.load_gui_config")
    def test_geometry_only_mode_applies_startup_camera_before_show(
        self,
        load_gui_config_mock: mock.Mock,
        build_plotter_mock: mock.Mock,
    ) -> None:
        """Geometry-only mode should launch with the deterministic startup camera."""
        detector = Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 1.0], 1.0)
        config = mock.Mock(detectors=[detector])
        gui_config = self._gui_config()
        plotter = FakePlotter()
        load_gui_config_mock.return_value = gui_config
        build_plotter_mock.return_value = plotter

        show_geometry_only(config)

        expected_camera = build_startup_camera_position((-1.0, 1.0, -1.0, 1.0, 9.5, 10.5))
        self.assertEqual(plotter.camera_position, expected_camera)
        self.assertEqual(plotter.reset_camera_clipping_range_calls, 1)
        self.assertEqual(plotter.show_calls, 1)

    def _gui_config(self) -> GUIConfig:
        """Build a compact GUI config used across scene tests."""
        return GUIConfig(
            background_color="black",
            default_detector_color="lightgray",
            detector_colors={"D1": "gray"},
            default_track_color="white",
            track_color_geometric_only="orange",
            track_color_fired_given_only="gold",
            track_color_fired_joint="lime",
            line_width=4.0,
        )


class FakePyVistaModule:
    """Small stand-in for the Box factory used by the scene helper."""

    @staticmethod
    def Box(bounds: tuple[float, ...]) -> tuple[str, tuple[float, ...]]:
        """Return a simple tuple so tests can assert that a mesh was created."""
        return ("box", bounds)


class FakePlotter:
    """Record add_mesh calls issued by the scene renderer."""

    def __init__(self) -> None:
        """Initialize an empty mesh-call list."""
        self.mesh_calls: list[dict[str, object]] = []
        self.camera_position: object | None = None
        self.reset_camera_clipping_range_calls = 0
        self.show_calls = 0
        self.window_size = (1600, 900)

    def add_mesh(self, mesh: object, **kwargs: object) -> None:
        """Store mesh metadata without trying to render it."""
        self.mesh_calls.append({"mesh": mesh, **kwargs})

    def reset_camera_clipping_range(self) -> None:
        """Record clipping-range updates triggered by the camera helper."""
        self.reset_camera_clipping_range_calls += 1

    def show(self) -> None:
        """Record geometry-only viewer launch without opening a window."""
        self.show_calls += 1
