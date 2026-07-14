"""Tests for the event/conditional navigation state that powers the event display."""

from __future__ import annotations

import unittest

import numpy as np

from toymc_cosmic.gui.config import GUIConfig
from toymc_cosmic.gui.event_state import (
    EventNavigator,
    PreparedConditional,
    build_event_states_for_event,
    collect_relevant_event_indices,
)


class GuiEventStateTests(unittest.TestCase):
    """Check the non-render logic that decides which event/state is shown."""

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

    def test_event_navigator_rejects_empty_relevant_track_list(self) -> None:
        """The viewer should fail early when no relevant tracks exist."""
        with self.assertRaises(ValueError):
            EventNavigator(
                relevant_event_indices=[],
                prepared_conditionals=[],
                gui_config=self._gui_config(),
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

    def _gui_config(self) -> GUIConfig:
        """Build a compact GUI config used across event-state tests."""
        return GUIConfig(
            background_color="black",
            default_detector_color="lightgray",
            detector_colors={},
            default_track_color="white",
            track_color_geometric_only="orange",
            track_color_fired_given_only="gold",
            track_color_fired_joint="lime",
            line_width=4.0,
            source_color="orange",
            source_opacity=0.25,
        )
