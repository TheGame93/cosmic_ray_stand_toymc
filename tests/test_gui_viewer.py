"""Tests for the EventDisplayController orchestrator (mocked PyVista)."""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from toymc_cosmic.config import Config, ConditionalConfig
from toymc_cosmic.geometry import Detector
from toymc_cosmic.gui.buttons import build_navigation_button_specs
from toymc_cosmic.gui.config import GUIConfig
from toymc_cosmic.gui.event_state import EventNavigator, PreparedConditional
from toymc_cosmic.gui.layout import BUTTON_LEFT_PADDING_PX, NAV_HELP_TEXT, STACK_BOTTOM_MARGIN_PX
from toymc_cosmic.gui.scene import build_startup_camera_position
from toymc_cosmic.gui.track_bounds import DisplayBounds
from toymc_cosmic.gui.viewer import EventDisplayController


class GuiViewerControllerTests(unittest.TestCase):
    """Check the controller's PyVista wiring end to end, with PyVista mocked out."""

    @mock.patch("toymc_cosmic.gui.viewer._require_pyvista")
    @mock.patch("toymc_cosmic.gui.viewer.create_textured_button_widget")
    @mock.patch("toymc_cosmic.gui.viewer.build_plotter")
    def test_controller_buttons_follow_navigation_and_home_resets_camera(
        self,
        build_plotter_mock: mock.Mock,
        create_button_widget_mock: mock.Mock,
        require_pyvista_mock: mock.Mock,
    ) -> None:
        """Button callbacks should mirror keyboard stepping and restore the initial camera."""
        build_plotter_mock.return_value = FakePlotter()
        create_button_widget_mock.side_effect = _create_fake_button_widget
        require_pyvista_mock.return_value = FakePyVistaModule()

        detectors = [
            Detector("T1", [0.0, 0.0, 10.0], [2.0, 2.0, 1.0], 1.0),
            Detector("D1", [0.0, 0.0, 8.0], [2.0, 2.0, 1.0], 1.0),
            Detector("T2", [0.0, 0.0, 6.0], [2.0, 2.0, 1.0], 1.0),
        ]
        config = Config(
            seed=123,
            theta_max=1.0,
            angular_model=mock.Mock(),
            flux_hz_per_cm2=0.01,
            monte_carlo=mock.Mock(n_events=2),
            detectors=detectors,
            logic_expressions=[],
            conditionals=[ConditionalConfig(name="C1", numerator="D1", given="T1 and T2")],
            output=mock.Mock(),
            gui=None,
        )
        tracks = mock.Mock(
            origins=np.array([[0.0, 0.0, 12.0], [0.0, 0.0, 12.0]]),
            directions=np.array([[0.0, 0.0, -1.0], [0.0, 0.0, -1.0]]),
        )
        simulation_result = mock.Mock(
            detectors=detectors,
            crossed={
                "T1": np.array([True, True]),
                "D1": np.array([True, True]),
                "T2": np.array([True, True]),
            },
            fired={
                "T1": np.array([True, True]),
                "D1": np.array([False, True]),
                "T2": np.array([True, True]),
            },
            tracks=tracks,
            n_events=2,
        )
        prepared_conditionals = [
            PreparedConditional(
                index=0,
                name="C1",
                numerator="D1",
                given="T1 and T2",
                geometric_given=np.array([True, True]),
                fired_given=np.array([True, True]),
                fired_numerator=np.array([False, True]),
            )
        ]
        navigator = EventNavigator([0, 1], prepared_conditionals, self._gui_config())
        controller = EventDisplayController(
            config=config,
            simulation_result=simulation_result,
            gui_config=self._gui_config(),
            navigator=navigator,
            display_bounds=DisplayBounds(-1.0, 1.0, -1.0, 1.0, 0.0, 12.0),
        )

        controller.show()
        plotter = build_plotter_mock.return_value

        self.assertEqual(list(plotter.button_callbacks.keys()), ["Home", "Previous", "Next"])
        self.assertEqual(
            [plotter.button_positions[name] for name in ["Home", "Previous", "Next"]],
            [spec.position for spec in build_navigation_button_specs()],
        )
        expected_camera = build_startup_camera_position(
            (-1.0, 1.0, -1.0, 1.0, 5.5, 10.5),
            viewport_aspect_ratio=1600.0 / 900.0,
        )
        self.assertEqual(plotter.camera_position, expected_camera)
        self.assertEqual(plotter.reset_camera_clipping_range_calls, 1)

        self.assertEqual(navigator.state_position(), (0, 0))
        plotter.button_callbacks["Next"](True)
        self.assertEqual(navigator.state_position(), (1, 0))
        plotter.button_callbacks["Previous"](True)
        self.assertEqual(navigator.state_position(), (0, 0))

        navigator_position_before_home = navigator.state_position()
        plotter.camera_position = ((9.0, 9.0, 9.0), (5.0, 5.0, 5.0), (0.0, 1.0, 0.0))
        plotter.button_callbacks["Home"](True)
        self.assertEqual(plotter.camera_position, expected_camera)
        self.assertEqual(plotter.reset_camera_clipping_range_calls, 2)
        self.assertEqual(navigator.state_position(), navigator_position_before_home)

        plotter.key_callbacks["Right"]()
        self.assertEqual(navigator.state_position(), (1, 0))

        legend_box_entries = [entry for entry in plotter.added_text if entry.get("name") == "legend_box"]
        self.assertTrue(legend_box_entries)
        legend_box_text = legend_box_entries[-1]["text"]
        self.assertIn("Event: 2 / 2", legend_box_text)
        self.assertIn("Relevant track: 2 / 2", legend_box_text)
        self.assertIn("State in event: 1 / 1", legend_box_text)
        self.assertIn('numerator: "D1"', legend_box_text)
        self.assertIn('given: "T1 and T2"', legend_box_text)
        self.assertIn("Given YES / Numerator YES", legend_box_text)
        self.assertNotIn("CONDITIONAL", legend_box_text)

        self.assertFalse(any(entry.get("name") == "viewer_status" for entry in plotter.added_text))
        for swatch_name in ("legend_swatch_0", "legend_swatch_1", "legend_swatch_2"):
            self.assertFalse(any(entry.get("name") == swatch_name for entry in plotter.added_text))

        text_entries = [entry for entry in plotter.added_text if entry.get("name") == "legend_text"]
        self.assertTrue(text_entries)
        legend_text_text = text_entries[-1]["text"]
        self.assertIn("Event: 2 / 2", legend_text_text)
        self.assertNotIn("Given YES / Numerator YES", legend_text_text)

        sentence_entries = [entry for entry in plotter.added_text if entry.get("name") == "legend_sentence"]
        self.assertTrue(sentence_entries)
        self.assertEqual(sentence_entries[-1]["color"], self._gui_config().track_color_fired_joint)
        self.assertTrue(sentence_entries[-1]["actor"].prop.bold)

        nav_help_entries = [entry for entry in plotter.added_text if entry.get("name") == "nav_help_text"]
        self.assertTrue(nav_help_entries)
        self.assertEqual(nav_help_entries[-1]["text"], NAV_HELP_TEXT)
        self.assertEqual(
            nav_help_entries[-1]["position"],
            (float(BUTTON_LEFT_PADDING_PX), float(STACK_BOTTOM_MARGIN_PX)),
        )

    def _gui_config(self) -> GUIConfig:
        """Build a compact GUI config used across viewer tests."""
        return GUIConfig(
            background_color="black",
            default_detector_color="lightgray",
            detector_colors={},
            default_track_color="white",
            track_color_geometric_only="orange",
            track_color_fired_given_only="gold",
            track_color_fired_joint="lime",
            line_width=4.0,
        )


class FakeButtonRepresentation:
    """Track the checkbox widget state for action-button tests."""

    def __init__(self) -> None:
        """Initialize the fake representation in the off state."""
        self.state = 0

    def SetState(self, value: int) -> None:
        """Record the requested state value."""
        self.state = value


class FakeButtonWidget:
    """Expose the representation API used by the controller callback."""

    def __init__(self) -> None:
        """Attach one fake representation object."""
        self.representation = FakeButtonRepresentation()

    def GetRepresentation(self) -> FakeButtonRepresentation:
        """Return the stored representation object."""
        return self.representation


class FakeTextProperty:
    """Mutable stand-in for a VTK text actor's ``prop`` namespace."""


class FakeTextActor:
    """Minimal text actor double exposing a settable ``prop`` namespace."""

    def __init__(self) -> None:
        """Attach one fake text-property namespace."""
        self.prop = FakeTextProperty()


class FakePyVistaModule:
    """Small stand-in for the PyVista module used in controller tests."""

    @staticmethod
    def Line(start: np.ndarray, end: np.ndarray) -> tuple[str, tuple[float, ...], tuple[float, ...]]:
        """Record the requested line segment without real rendering."""
        return ("line", tuple(start.tolist()), tuple(end.tolist()))


class FakePlotter:
    """Minimal plotter double that records registered callbacks and camera state."""

    def __init__(self) -> None:
        """Initialize callback registries and a stable initial camera."""
        self.key_callbacks: dict[str, object] = {}
        self.button_callbacks: dict[str, object] = {}
        self.button_positions: dict[str, tuple[float, float]] = {}
        self.camera_position = ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        self.added_meshes: list[dict[str, object]] = []
        self.added_text: list[dict[str, object]] = []
        self.iren = mock.Mock(interactor=object())
        self.renderer = object()
        self.reset_camera_clipping_range_calls = 0
        self.window_size = (1600, 900)

    def add_key_event(self, key: str, callback: object) -> None:
        """Record a keyboard callback registration."""
        self.key_callbacks[key] = callback

    def add_mesh(self, mesh: object, **kwargs: object) -> None:
        """Record mesh redraws without rendering anything."""
        self.added_meshes.append({"mesh": mesh, **kwargs})

    def add_text(self, text: str, **kwargs: object) -> "FakeTextActor":
        """Record text overlays (including the returned actor) without rendering them."""
        actor = FakeTextActor()
        self.added_text.append({"text": text, "actor": actor, **kwargs})
        return actor

    def render(self) -> None:
        """No-op render hook used by the controller."""
        return None

    def reset_camera_clipping_range(self) -> None:
        """Record clipping-range updates triggered by the startup camera helper."""
        self.reset_camera_clipping_range_calls += 1

    def show(self) -> None:
        """No-op show hook used by the controller."""
        return None

    def close(self) -> None:
        """No-op close hook used by the controller."""
        return None


def _create_fake_button_widget(
    plotter: FakePlotter,
    pv: object,
    *,
    label: str,
    position: tuple[float, float],
    size: int,
    texture_off: np.ndarray,
    texture_on: np.ndarray,
    callback: object,
) -> FakeButtonWidget:
    """Store controller button metadata without touching VTK."""
    del pv, size, texture_off, texture_on
    plotter.button_callbacks[label] = callback
    plotter.button_positions[label] = position
    return FakeButtonWidget()
