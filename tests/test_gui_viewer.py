"""Tests for GUI event-display helpers that do not require PyVista."""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from toymc_cosmic.config import Config, ConditionalConfig
from toymc_cosmic.geometry import Detector
from toymc_cosmic.gui.config import GUIConfig
from toymc_cosmic.gui.scene import build_startup_camera_position
from toymc_cosmic.gui.viewer import (
    BUTTON_ROW_Y_PX,
    BUTTON_SIZE_PX,
    BUTTON_LEFT_PADDING_PX,
    NAV_HELP_TEXT,
    STACK_BOTTOM_MARGIN_PX,
    DisplayBounds,
    EventDisplayController,
    EventDisplayState,
    EventNavigator,
    PreparedConditional,
    build_button_texture_pixels,
    build_event_states_for_event,
    build_navigation_button_specs,
    clip_line_to_bounds,
    collect_relevant_event_indices,
    _build_legend_lines,
    _build_legend_sentence_text,
)


def _make_event_display_state(
    state_name: str = "geometric-only",
    given_fired: bool = True,
    numerator_fired: bool = False,
) -> EventDisplayState:
    """Build a minimal EventDisplayState fixture for legend text tests."""
    return EventDisplayState(
        event_index=0,
        relevant_event_index=0,
        relevant_event_count=2,
        conditional_index=0,
        step_index_within_event=0,
        step_count_within_event=3,
        conditional_name="D1|T1*T2",
        given_expression="T1 and T2",
        numerator_expression="D1",
        given_fired=given_fired,
        numerator_fired=numerator_fired,
        involved_detector_names=frozenset({"T1", "T2", "D1"}),
        state_name=state_name,
        track_color="orange",
    )


class GuiViewerTests(unittest.TestCase):
    """Check the non-render logic that powers the event display."""

    def test_event_without_relevant_conditionals_produces_no_states(self) -> None:
        """An event with no geometric match should not be navigable."""
        gui_config = self._gui_config()
        prepared_conditionals = [
            PreparedConditional(
                index=0,
                name="C1",
                numerator="D1",
                given="T1",
                geometric_given=np.array([False]),
                fired_given=np.array([False]),
                fired_numerator=np.array([False]),
            )
        ]

        states = build_event_states_for_event(0, 0, 1, prepared_conditionals, gui_config)

        self.assertEqual(states, [])

    def test_event_states_distinguish_all_three_conditional_track_states(self) -> None:
        """Relevant conditionals should map to the three configured track colors."""
        gui_config = self._gui_config()
        prepared_conditionals = [
            PreparedConditional(
                index=0,
                name="C1",
                numerator="D1",
                given="T1",
                geometric_given=np.array([True]),
                fired_given=np.array([False]),
                fired_numerator=np.array([False]),
            ),
            PreparedConditional(
                index=1,
                name="C2",
                numerator="D1",
                given="T1",
                geometric_given=np.array([True]),
                fired_given=np.array([True]),
                fired_numerator=np.array([False]),
            ),
            PreparedConditional(
                index=2,
                name="C3",
                numerator="D1",
                given="T1",
                geometric_given=np.array([True]),
                fired_given=np.array([True]),
                fired_numerator=np.array([True]),
            ),
        ]

        states = build_event_states_for_event(0, 0, 1, prepared_conditionals, gui_config)

        self.assertEqual([state.state_name for state in states], ["geometric-only", "fired-given-only", "fired-joint"])
        self.assertEqual(
            [state.track_color for state in states],
            ["orange", "gold", "lime"],
        )
        self.assertEqual([state.given_fired for state in states], [False, True, True])
        self.assertEqual([state.numerator_fired for state in states], [False, False, True])
        self.assertEqual(states[0].involved_detector_names, frozenset({"T1", "D1"}))
        self.assertEqual(states[0].relevant_event_index, 0)
        self.assertEqual(states[0].relevant_event_count, 1)
        self.assertEqual(
            [state.given_expression for state in states],
            ["T1", "T1", "T1"],
        )
        self.assertEqual(
            [state.numerator_expression for state in states],
            ["D1", "D1", "D1"],
        )

    def test_event_state_involved_detector_names_ignore_boolean_keywords(self) -> None:
        """Only detector names from given and numerator should be retained."""
        gui_config = self._gui_config()
        prepared_conditionals = [
            PreparedConditional(
                index=0,
                name="C1",
                numerator="D1 or D2",
                given="T1 and not T2",
                geometric_given=np.array([True]),
                fired_given=np.array([True]),
                fired_numerator=np.array([True]),
            )
        ]

        states = build_event_states_for_event(0, 0, 1, prepared_conditionals, gui_config)

        self.assertEqual(states[0].involved_detector_names, frozenset({"T1", "T2", "D1", "D2"}))

    def test_collect_relevant_event_indices_keeps_only_geometric_matches(self) -> None:
        """Only events relevant to at least one conditional should be kept."""
        prepared_conditionals = [
            PreparedConditional(
                index=0,
                name="C1",
                numerator="D1",
                given="T1",
                geometric_given=np.array([False, True, False, False]),
                fired_given=np.array([False, False, False, False]),
                fired_numerator=np.array([False, False, False, False]),
            ),
            PreparedConditional(
                index=1,
                name="C2",
                numerator="D1",
                given="T1",
                geometric_given=np.array([False, False, True, False]),
                fired_given=np.array([False, False, False, False]),
                fired_numerator=np.array([False, False, False, False]),
            ),
        ]

        relevant_event_indices = collect_relevant_event_indices(prepared_conditionals)

        self.assertEqual(relevant_event_indices, [1, 2])

    def test_event_navigator_advances_event_then_conditional_in_requested_order(self) -> None:
        """The stepping order should skip non-relevant events and keep conditional order."""
        gui_config = self._gui_config()
        prepared_conditionals = [
            PreparedConditional(
                index=0,
                name="C1",
                numerator="D1",
                given="T1",
                geometric_given=np.array([True, False, False]),
                fired_given=np.array([False, False, False]),
                fired_numerator=np.array([False, False, False]),
            ),
            PreparedConditional(
                index=1,
                name="C2",
                numerator="D1",
                given="T1",
                geometric_given=np.array([True, False, True]),
                fired_given=np.array([True, False, True]),
                fired_numerator=np.array([False, False, True]),
            ),
        ]
        relevant_event_indices = collect_relevant_event_indices(prepared_conditionals)
        navigator = EventNavigator(
            relevant_event_indices=relevant_event_indices,
            prepared_conditionals=prepared_conditionals,
            gui_config=gui_config,
        )

        first_state = navigator.current_state()
        second_state = navigator.next_state()
        third_state = navigator.next_state()

        self.assertEqual((first_state.event_index, first_state.conditional_index), (0, 0))
        self.assertEqual((second_state.event_index, second_state.conditional_index), (0, 1))
        self.assertEqual((third_state.event_index, third_state.conditional_index), (2, 1))
        self.assertEqual(third_state.relevant_event_index, 1)
        self.assertEqual(third_state.relevant_event_count, 2)

    def test_clip_line_to_bounds_returns_finite_segment(self) -> None:
        """The track should be clipped to the requested display box."""
        start, end = clip_line_to_bounds(
            origin=np.array([0.0, 0.0, 0.0]),
            direction=np.array([0.0, 0.0, 1.0]),
            bounds=DisplayBounds(-1.0, 1.0, -1.0, 1.0, -2.0, 3.0),
        )

        self.assertTrue(np.allclose(start, np.array([0.0, 0.0, -2.0])))
        self.assertTrue(np.allclose(end, np.array([0.0, 0.0, 3.0])))

    def test_event_navigator_rejects_empty_relevant_track_list(self) -> None:
        """The viewer should fail early when no relevant tracks exist."""
        with self.assertRaises(ValueError):
            EventNavigator(
                relevant_event_indices=[],
                prepared_conditionals=[],
                gui_config=self._gui_config(),
            )

    def test_navigation_button_specs_form_one_horizontal_row_left_aligned_under_axes(self) -> None:
        """Buttons should sit directly under the axes, left-aligned, in Home/Previous/Next order."""
        button_specs = build_navigation_button_specs()

        self.assertEqual([spec.name for spec in button_specs], ["Home", "Previous", "Next"])
        self.assertEqual([spec.icon_kind for spec in button_specs], ["home", "previous", "next"])
        self.assertTrue(all(spec.position[1] == BUTTON_ROW_Y_PX for spec in button_specs))
        self.assertEqual(button_specs[0].position[0], float(BUTTON_LEFT_PADDING_PX))
        self.assertTrue(button_specs[0].position[0] < button_specs[1].position[0] < button_specs[2].position[0])

    def test_button_texture_icons_have_expected_shape_and_mirroring(self) -> None:
        """Home should be a square, while Previous/Next should be mirrored arrows."""
        home_pixels = build_button_texture_pixels("home", is_pressed=False, size=BUTTON_SIZE_PX)
        previous_pixels = build_button_texture_pixels("previous", is_pressed=False, size=BUTTON_SIZE_PX)
        next_pixels = build_button_texture_pixels("next", is_pressed=False, size=BUTTON_SIZE_PX)

        self.assertEqual(home_pixels.dtype, np.uint8)
        self.assertEqual(home_pixels.shape, (BUTTON_SIZE_PX, BUTTON_SIZE_PX, 3))
        self.assertTrue(np.array_equal(previous_pixels[:, ::-1, :], next_pixels))
        self.assertFalse(np.array_equal(home_pixels, previous_pixels))

        center = BUTTON_SIZE_PX // 2
        self.assertTrue(np.array_equal(home_pixels[center, center], home_pixels[center - 1, center - 1]))
        self.assertFalse(np.array_equal(home_pixels[center, center], home_pixels[1, 1]))

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

    def test_event_state_carries_given_and_numerator_expressions(self) -> None:
        """The given/numerator strings should propagate verbatim onto the state."""
        gui_config = self._gui_config()
        prepared_conditionals = [
            PreparedConditional(
                index=0,
                name="D1|T1*T2",
                numerator="D1",
                given="T1 and T2",
                geometric_given=np.array([True]),
                fired_given=np.array([True]),
                fired_numerator=np.array([True]),
            )
        ]

        states = build_event_states_for_event(0, 0, 1, prepared_conditionals, gui_config)

        self.assertEqual(states[0].given_expression, "T1 and T2")
        self.assertEqual(states[0].numerator_expression, "D1")

    def test_build_legend_lines_contains_all_eight_lines_with_expected_content(self) -> None:
        """The merged legend should show counters, the expressions, and the live sentence."""
        state = _make_event_display_state(given_fired=True, numerator_fired=True)

        legend_lines = _build_legend_lines(state, total_events=5)

        self.assertEqual(
            legend_lines,
            [
                "Event: 1 / 5",
                "Relevant track: 1 / 2",
                "",
                "State in event: 1 / 3",
                "",
                'numerator: "D1"',
                'given: "T1 and T2"',
                "Given YES / Numerator YES",
            ],
        )

    def test_build_legend_lines_excludes_conditional_name(self) -> None:
        """The dropped 'CONDITIONAL: <name>' line must not resurface, pipe or otherwise."""
        state = _make_event_display_state()

        legend_lines = _build_legend_lines(state, total_events=5)
        joined_text = "\n".join(legend_lines)

        self.assertNotIn("CONDITIONAL", joined_text)
        self.assertNotIn("|", joined_text)

    def test_build_legend_sentence_numerator_reflects_actual_boolean_even_when_given_is_no(self) -> None:
        """The numerator boolean should be shown as-is, not 'N/A', even when given is NO."""
        state = _make_event_display_state(given_fired=False, numerator_fired=True)

        self.assertEqual(_build_legend_sentence_text(state), "Given NO / Numerator YES")

    def test_build_legend_sentence_text_for_all_three_states(self) -> None:
        """Each of the three configured track states should map to its own sentence text."""
        geometric_only_state = _make_event_display_state(given_fired=False, numerator_fired=False)
        fired_given_only_state = _make_event_display_state(given_fired=True, numerator_fired=False)
        fired_joint_state = _make_event_display_state(given_fired=True, numerator_fired=True)

        self.assertEqual(_build_legend_sentence_text(geometric_only_state), "Given NO / Numerator NO")
        self.assertEqual(_build_legend_sentence_text(fired_given_only_state), "Given YES / Numerator NO")
        self.assertEqual(_build_legend_sentence_text(fired_joint_state), "Given YES / Numerator YES")

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
