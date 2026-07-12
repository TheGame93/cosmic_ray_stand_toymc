"""Per-event/conditional navigation state for the event display.

Pure Python/NumPy bookkeeping -- no PyVista here. This module answers
"which event and which conditional state are we looking at right now, and
what should the next/previous one be", independent of how that state is
actually drawn. See `gui/viewer.py` for the `EventDisplayController` that
renders the states this module produces, and `gui/legend.py` for the text
built from one `EventDisplayState`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..config import Config
from ..logic import evaluate, extract_names
from ..simulation import SimulationResult
from .config import GUIConfig


@dataclass(frozen=True)
class PreparedConditional:
    """Precomputed per-event booleans for one configured conditional."""

    index: int
    name: str
    numerator: str
    given: str
    geometric_given: np.ndarray
    fired_given: np.ndarray
    fired_numerator: np.ndarray


@dataclass(frozen=True)
class EventDisplayState:
    """One viewer state for one event and one relevant conditional.

    `conditional_name` and `conditional_index` are kept for structural
    completeness (they identify which configured conditional this state
    belongs to) but are no longer rendered anywhere -- the legend dropped
    the "CONDITIONAL: <name>" line in favor of showing the raw
    `given`/`numerator` expressions directly.
    """

    event_index: int
    relevant_event_index: int
    relevant_event_count: int
    conditional_index: int | None
    step_index_within_event: int
    step_count_within_event: int
    conditional_name: str | None
    given_expression: str | None
    numerator_expression: str | None
    given_fired: bool
    numerator_fired: bool
    involved_detector_names: frozenset[str]
    state_name: str
    track_color: Any


class EventNavigator:
    """Manage nested event/conditional stepping for the event display."""

    def __init__(
        self,
        relevant_event_indices: list[int],
        prepared_conditionals: list[PreparedConditional],
        gui_config: GUIConfig,
    ) -> None:
        """Build a lazy navigator over event display states."""
        if not relevant_event_indices:
            raise ValueError("Event display requires at least one relevant track.")

        self._relevant_event_indices = relevant_event_indices
        self._prepared_conditionals = prepared_conditionals
        self._gui_config = gui_config
        self._event_states_cache: dict[int, list[EventDisplayState]] = {}
        self._relevant_event_index = 0
        self._state_index_within_event = 0

    def current_state(self) -> EventDisplayState:
        """Return the state currently selected by the navigator."""
        event_states = self._states_for_current_event()
        return event_states[self._state_index_within_event]

    def next_state(self) -> EventDisplayState:
        """Advance to the next conditional state or the next event."""
        event_states = self._states_for_current_event()
        if self._state_index_within_event + 1 < len(event_states):
            self._state_index_within_event += 1
            return self.current_state()

        if self._relevant_event_index + 1 < len(self._relevant_event_indices):
            self._relevant_event_index += 1
            self._state_index_within_event = 0
        return self.current_state()

    def previous_state(self) -> EventDisplayState:
        """Move back to the previous conditional state or previous event."""
        if self._state_index_within_event > 0:
            self._state_index_within_event -= 1
            return self.current_state()

        if self._relevant_event_index > 0:
            self._relevant_event_index -= 1
            previous_event_states = self._states_for_current_event()
            self._state_index_within_event = len(previous_event_states) - 1
        return self.current_state()

    def state_position(self) -> tuple[int, int]:
        """Return the current event/state position for tests and controller checks."""
        return self._relevant_event_index, self._state_index_within_event

    def _states_for_current_event(self) -> list[EventDisplayState]:
        """Return the cached states for the currently selected relevant event."""
        event_index = self._relevant_event_indices[self._relevant_event_index]
        if event_index not in self._event_states_cache:
            self._event_states_cache[event_index] = build_event_states_for_event(
                event_index,
                self._relevant_event_index,
                len(self._relevant_event_indices),
                self._prepared_conditionals,
                self._gui_config,
            )
        return self._event_states_cache[event_index]


def prepare_conditionals(
    config: Config,
    simulation_result: SimulationResult,
) -> list[PreparedConditional]:
    """Precompute per-event boolean arrays for every configured conditional."""
    prepared: list[PreparedConditional] = []
    for index, conditional in enumerate(config.conditionals):
        prepared.append(
            PreparedConditional(
                index=index,
                name=conditional.name,
                numerator=conditional.numerator,
                given=conditional.given,
                geometric_given=evaluate(conditional.given, simulation_result.crossed),
                fired_given=evaluate(conditional.given, simulation_result.fired),
                fired_numerator=evaluate(conditional.numerator, simulation_result.fired),
            )
        )
    return prepared


def collect_relevant_event_indices(prepared_conditionals: list[PreparedConditional]) -> list[int]:
    """Return event indices relevant to at least one conditional in geometric mode."""
    if not prepared_conditionals:
        return []

    relevant_mask = np.zeros_like(prepared_conditionals[0].geometric_given, dtype=bool)
    for conditional in prepared_conditionals:
        relevant_mask |= conditional.geometric_given
    return np.flatnonzero(relevant_mask).tolist()


def build_event_states_for_event(
    event_index: int,
    relevant_event_index: int,
    relevant_event_count: int,
    prepared_conditionals: list[PreparedConditional],
    gui_config: GUIConfig,
) -> list[EventDisplayState]:
    """Return all viewer states for one event in the configured stepping order."""
    relevant_conditionals = [
        conditional
        for conditional in prepared_conditionals
        if bool(conditional.geometric_given[event_index])
    ]

    if not relevant_conditionals:
        return []

    event_states: list[EventDisplayState] = []
    step_count = len(relevant_conditionals)
    for step_index, conditional in enumerate(relevant_conditionals):
        involved_detector_names = frozenset(
            extract_names(conditional.given) | extract_names(conditional.numerator)
        )
        # Read both booleans as named locals -- not just to branch into
        # `state_name`/`track_color` below, but also to surface them
        # verbatim on `EventDisplayState` for the legend text. In
        # particular `numerator_fired` is evaluated independently of
        # `given_fired` in `prepare_conditionals`, so it already has a
        # well-defined value even when `given_fired` is False; the legend
        # displays that real value rather than an "N/A" placeholder.
        given_fired = bool(conditional.fired_given[event_index])
        numerator_fired = bool(conditional.fired_numerator[event_index])
        if not given_fired:
            state_name = "geometric-only"
            track_color = gui_config.track_color_geometric_only
        elif not numerator_fired:
            state_name = "fired-given-only"
            track_color = gui_config.track_color_fired_given_only
        else:
            state_name = "fired-joint"
            track_color = gui_config.track_color_fired_joint

        event_states.append(
            EventDisplayState(
                event_index=event_index,
                relevant_event_index=relevant_event_index,
                relevant_event_count=relevant_event_count,
                conditional_index=conditional.index,
                step_index_within_event=step_index,
                step_count_within_event=step_count,
                conditional_name=conditional.name,
                given_expression=conditional.given,
                numerator_expression=conditional.numerator,
                given_fired=given_fired,
                numerator_fired=numerator_fired,
                involved_detector_names=involved_detector_names,
                state_name=state_name,
                track_color=track_color,
            )
        )

    return event_states
