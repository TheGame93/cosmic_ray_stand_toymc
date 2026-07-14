"""Tests for GUI scene helpers that can run without a live PyVista window."""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from toymc_cosmic.config import BeamSourceConfig, CosmicSourceConfig, ObjectSourceConfig
from toymc_cosmic.geometry import Detector
from toymc_cosmic.gui.config import GUIConfig
from toymc_cosmic.gui.scene import (
    BEAM_VIEW_UP,
    DEFAULT_VIEWPORT_ASPECT_RATIO,
    DEFAULT_WINDOW_HEIGHT_PX,
    DEFAULT_WINDOW_WIDTH_PX,
    STARTUP_VIEW_DIRECTION,
    STARTUP_VIEW_UP,
    apply_camera_position,
    build_plotter,
    build_startup_camera_position,
    compute_axes_viewport,
    plotter_viewport_aspect_ratio,
    plotter_window_height_px,
    plotter_window_width_px,
    render_detector_colors,
    render_source_shape,
    show_geometry_only,
    startup_view_up,
)


_COSMIC_SOURCE_CONFIG = CosmicSourceConfig(theta_max=1.0, model="cos2", flux_hz_per_cm2=0.01)


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

    def test_plotter_window_height_px_uses_window_size_or_default(self) -> None:
        """Window-height lookup should prefer the plotter window size but stay deterministic."""
        explicit_height_plotter = mock.Mock(window_size=(1600, 900))
        fallback_height_plotter = mock.Mock()
        del fallback_height_plotter.window_size

        self.assertEqual(plotter_window_height_px(explicit_height_plotter), 900.0)
        self.assertEqual(plotter_window_height_px(fallback_height_plotter), DEFAULT_WINDOW_HEIGHT_PX)

    def test_plotter_window_width_px_uses_window_size_or_default(self) -> None:
        """Window-width lookup should prefer the plotter window size but stay deterministic."""
        explicit_width_plotter = mock.Mock(window_size=(1600, 900))
        fallback_width_plotter = mock.Mock()
        del fallback_width_plotter.window_size

        self.assertEqual(plotter_window_width_px(explicit_width_plotter), 1600.0)
        self.assertEqual(plotter_window_width_px(fallback_width_plotter), DEFAULT_WINDOW_WIDTH_PX)

    def test_compute_axes_viewport_shifts_bottom_edge_by_reserved_pixel_fraction(self) -> None:
        """A non-zero pixel budget should shift the axes viewport up by that fraction."""
        viewport = compute_axes_viewport(90.0, 900.0)
        self.assertEqual(len(viewport), 4)
        for actual, expected in zip(viewport, (0.0, 0.1, 0.2, 0.3)):
            self.assertAlmostEqual(actual, expected)

    def test_compute_axes_viewport_zero_reserve_matches_pyvista_default(self) -> None:
        """No reserved space should reproduce PyVista's own default axes viewport."""
        self.assertEqual(compute_axes_viewport(0.0, 900.0), (0.0, 0.0, 0.2, 0.2))

    def test_compute_axes_viewport_rejects_negative_reserve(self) -> None:
        """A negative pixel budget makes no sense and should fail loudly."""
        with self.assertRaises(ValueError):
            compute_axes_viewport(-1.0, 900.0)

    def test_compute_axes_viewport_rejects_non_positive_window_height(self) -> None:
        """A zero or negative window height cannot be converted into a fraction."""
        with self.assertRaises(ValueError):
            compute_axes_viewport(90.0, 0.0)
        with self.assertRaises(ValueError):
            compute_axes_viewport(90.0, -900.0)

    def test_compute_axes_viewport_shifts_left_edge_by_horizontal_pixel_fraction(self) -> None:
        """A non-zero horizontal shift should move both the left and right edges."""
        viewport = compute_axes_viewport(0.0, 900.0, shift_right_px=160.0, window_width_px=1600.0)
        for actual, expected in zip(viewport, (0.1, 0.0, 0.3, 0.2)):
            self.assertAlmostEqual(actual, expected)

    def test_compute_axes_viewport_zero_horizontal_shift_ignores_window_width(self) -> None:
        """The default window_width_px must never cause a division error when unused."""
        viewport = compute_axes_viewport(0.0, 900.0)
        self.assertEqual(viewport, (0.0, 0.0, 0.2, 0.2))

    def test_compute_axes_viewport_rejects_non_positive_window_width_when_shifting(self) -> None:
        """A zero or negative window width cannot be converted into a fraction when shifting."""
        with self.assertRaises(ValueError):
            compute_axes_viewport(0.0, 900.0, shift_right_px=10.0, window_width_px=0.0)

    @mock.patch("toymc_cosmic.gui.scene._require_pyvista")
    def test_build_plotter_keeps_default_axes_when_reserve_is_zero(
        self,
        require_pyvista_mock: mock.Mock,
    ) -> None:
        """Geometry-only mode's default call must render the axes exactly as before."""
        require_pyvista_mock.return_value = FakePyVistaModule()
        detectors = [Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 1.0], 1.0)]

        plotter = build_plotter(detectors, self._gui_config(), _COSMIC_SOURCE_CONFIG)

        self.assertEqual(plotter.add_axes_calls, [{}])

    @mock.patch("toymc_cosmic.gui.scene._require_pyvista")
    def test_build_plotter_shifts_axes_viewport_when_reserve_given(
        self,
        require_pyvista_mock: mock.Mock,
    ) -> None:
        """Event-display mode's reserved pixel budget must reach `add_axes` as a viewport."""
        require_pyvista_mock.return_value = FakePyVistaModule()
        detectors = [Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 1.0], 1.0)]

        plotter = build_plotter(detectors, self._gui_config(), _COSMIC_SOURCE_CONFIG, reserve_bottom_px=90.0)

        self.assertEqual(len(plotter.add_axes_calls), 1)
        viewport = plotter.add_axes_calls[0]["viewport"]
        for actual, expected in zip(viewport, (0.0, 0.1, 0.2, 0.3)):
            self.assertAlmostEqual(actual, expected)

    @mock.patch("toymc_cosmic.gui.scene._require_pyvista")
    def test_build_plotter_shifts_axes_viewport_when_horizontal_shift_given(
        self,
        require_pyvista_mock: mock.Mock,
    ) -> None:
        """A non-zero horizontal shift alone must also reach `add_axes` as a viewport."""
        require_pyvista_mock.return_value = FakePyVistaModule()
        detectors = [Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 1.0], 1.0)]

        plotter = build_plotter(detectors, self._gui_config(), _COSMIC_SOURCE_CONFIG, shift_axes_right_px=160.0)

        self.assertEqual(len(plotter.add_axes_calls), 1)
        viewport = plotter.add_axes_calls[0]["viewport"]
        for actual, expected in zip(viewport, (0.1, 0.0, 0.3, 0.2)):
            self.assertAlmostEqual(actual, expected)

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

    def test_startup_view_up_flips_for_beam_sources(self) -> None:
        """Beam sources use x-up; other source types keep the default z-up view."""
        beam_config = BeamSourceConfig(profile="uniform", center=(0.0, 0.0), size=(1.0,), flux_hz_per_cm2=1.0)
        object_config = ObjectSourceConfig(shape="sphere", center=(0.0, 0.0, 0.0), size=(1.0,), activity_hz=1.0)

        self.assertEqual(startup_view_up(beam_config), BEAM_VIEW_UP)
        self.assertEqual(startup_view_up(_COSMIC_SOURCE_CONFIG), STARTUP_VIEW_UP)
        self.assertEqual(startup_view_up(object_config), STARTUP_VIEW_UP)

    @mock.patch("toymc_cosmic.gui.scene._require_pyvista")
    def test_render_source_shape_renders_mesh_for_object_sources(
        self,
        require_pyvista_mock: mock.Mock,
    ) -> None:
        """An object source should add exactly one mesh, colored from the GUI config."""
        require_pyvista_mock.return_value = FakePyVistaModule()
        plotter = FakePlotter()
        object_config = ObjectSourceConfig(
            shape="sphere", center=(0.0, 0.0, 0.0), size=(2.0,), activity_hz=1.0
        )

        render_source_shape(plotter, object_config, self._gui_config(), [])

        self.assertEqual(len(plotter.mesh_calls), 1)
        self.assertEqual(plotter.mesh_calls[0]["color"], "orange")
        self.assertEqual(plotter.mesh_calls[0]["opacity"], 0.25)

    @mock.patch("toymc_cosmic.gui.scene._require_pyvista")
    def test_render_source_shape_box_reuses_object_source_model_spatial_bounds(
        self,
        require_pyvista_mock: mock.Mock,
    ) -> None:
        """A box-shape object source's mesh bounds must match ObjectSourceModel.spatial_bounds."""
        require_pyvista_mock.return_value = FakePyVistaModule()
        plotter = FakePlotter()
        detectors = [Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 1.0], 1.0)]
        object_config = ObjectSourceConfig(
            shape="box", center=(1.0, 2.0, 3.0), size=(4.0, 6.0, 8.0), activity_hz=1.0
        )

        render_source_shape(plotter, object_config, self._gui_config(), detectors)

        self.assertEqual(
            plotter.mesh_calls[0]["mesh"],
            ("box", (-1.0, 3.0, -1.0, 5.0, -1.0, 7.0)),
        )

    @mock.patch("toymc_cosmic.gui.scene._require_pyvista")
    def test_render_source_shape_is_a_no_op_for_non_object_sources(
        self,
        require_pyvista_mock: mock.Mock,
    ) -> None:
        """Cosmic and beam sources must not add a source mesh."""
        require_pyvista_mock.return_value = FakePyVistaModule()
        plotter = FakePlotter()

        render_source_shape(plotter, _COSMIC_SOURCE_CONFIG, self._gui_config(), [])

        self.assertEqual(plotter.mesh_calls, [])

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
            source_color="orange",
            source_opacity=0.25,
        )


class FakePyVistaModule:
    """Small stand-in for the pyvista module functions used by the scene helper."""

    @staticmethod
    def Box(bounds: tuple[float, ...]) -> tuple[str, tuple[float, ...]]:
        """Return a simple tuple so tests can assert that a mesh was created."""
        return ("box", bounds)

    @staticmethod
    def Sphere(radius: float, center: tuple[float, ...]) -> tuple[str, float, tuple[float, ...]]:
        """Return a simple tuple so tests can assert that a mesh was created."""
        return ("sphere", radius, center)

    @staticmethod
    def Cylinder(
        center: tuple[float, ...], direction: tuple[float, ...], radius: float, height: float
    ) -> tuple[str, tuple[float, ...], tuple[float, ...], float, float]:
        """Return a simple tuple so tests can assert that a mesh was created."""
        return ("cylinder", center, direction, radius, height)

    @staticmethod
    def Plotter() -> "FakePlotter":
        """Return a fresh fake plotter, mirroring `pv.Plotter()` used by `build_plotter`."""
        return FakePlotter()


class FakePlotter:
    """Record add_mesh/add_axes calls issued by the scene renderer."""

    def __init__(self) -> None:
        """Initialize empty call logs."""
        self.mesh_calls: list[dict[str, object]] = []
        self.camera_position: object | None = None
        self.reset_camera_clipping_range_calls = 0
        self.show_calls = 0
        self.window_size = (1600, 900)
        self.background_color: object | None = None
        self.add_axes_calls: list[dict[str, object]] = []

    def add_mesh(self, mesh: object, **kwargs: object) -> None:
        """Store mesh metadata without trying to render it."""
        self.mesh_calls.append({"mesh": mesh, **kwargs})

    def set_background(self, color: object) -> None:
        """Record the requested background color."""
        self.background_color = color

    def add_axes(self, **kwargs: object) -> None:
        """Record the axes widget call, with or without an explicit viewport."""
        self.add_axes_calls.append(kwargs)

    def reset_camera_clipping_range(self) -> None:
        """Record clipping-range updates triggered by the camera helper."""
        self.reset_camera_clipping_range_calls += 1

    def show(self) -> None:
        """Record geometry-only viewer launch without opening a window."""
        self.show_calls += 1
