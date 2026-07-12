"""Tests for the legend text builders used by the event display."""

from __future__ import annotations

import unittest

from toymc_cosmic.gui.event_state import EventDisplayState
from toymc_cosmic.gui.legend import build_legend_lines, build_legend_sentence_text


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


class GuiLegendTests(unittest.TestCase):
    """Check the plain-text content built for the boxed legend overlay."""

    def test_build_legend_lines_contains_all_eight_lines_with_expected_content(self) -> None:
        """The merged legend should show counters, the expressions, and the live sentence."""
        state = _make_event_display_state(given_fired=True, numerator_fired=True)

        legend_lines = build_legend_lines(state, total_events=5)

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

        legend_lines = build_legend_lines(state, total_events=5)
        joined_text = "\n".join(legend_lines)

        self.assertNotIn("CONDITIONAL", joined_text)
        self.assertNotIn("|", joined_text)

    def test_build_legend_sentence_numerator_reflects_actual_boolean_even_when_given_is_no(self) -> None:
        """The numerator boolean should be shown as-is, not 'N/A', even when given is NO."""
        state = _make_event_display_state(given_fired=False, numerator_fired=True)

        self.assertEqual(build_legend_sentence_text(state), "Given NO / Numerator YES")

    def test_build_legend_sentence_text_for_all_three_states(self) -> None:
        """Each of the three configured track states should map to its own sentence text."""
        geometric_only_state = _make_event_display_state(given_fired=False, numerator_fired=False)
        fired_given_only_state = _make_event_display_state(given_fired=True, numerator_fired=False)
        fired_joint_state = _make_event_display_state(given_fired=True, numerator_fired=True)

        self.assertEqual(build_legend_sentence_text(geometric_only_state), "Given NO / Numerator NO")
        self.assertEqual(build_legend_sentence_text(fired_given_only_state), "Given YES / Numerator NO")
        self.assertEqual(build_legend_sentence_text(fired_joint_state), "Given YES / Numerator YES")
