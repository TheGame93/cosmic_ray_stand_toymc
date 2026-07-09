"""Step-by-step event display for the optional GUI."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from ..config import Config
from ..geometry import Detector, generation_region
from ..logic import evaluate
from ..simulation import SimulationResult
from .config import GUIConfig, load_gui_config
from .scene import build_plotter, render_detector_colors


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
    """One viewer state for one event and one relevant conditional."""

    event_index: int
    conditional_index: int | None
    step_index_within_event: int
    step_count_within_event: int
    conditional_name: str | None
    state_name: str
    state_description: str
    track_color: Any


@dataclass(frozen=True)
class DisplayBounds:
    """Axis-aligned box used to clip the displayed event track."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float


class EventNavigator:
    """Manage nested event/conditional stepping for the event display."""

    def __init__(
        self,
        simulation_result: SimulationResult,
        prepared_conditionals: list[PreparedConditional],
        gui_config: GUIConfig,
    ) -> None:
        """Build a lazy navigator over event display states."""
        self._simulation_result = simulation_result
        self._prepared_conditionals = prepared_conditionals
        self._gui_config = gui_config
        self._event_states_cache: dict[int, list[EventDisplayState]] = {}
        self._event_index = 0
        self._state_index_within_event = 0

    def current_state(self) -> EventDisplayState:
        """Return the state currently selected by the navigator."""
        event_states = self._states_for_event(self._event_index)
        return event_states[self._state_index_within_event]

    def next_state(self) -> EventDisplayState:
        """Advance to the next conditional state or the next event."""
        event_states = self._states_for_event(self._event_index)
        if self._state_index_within_event + 1 < len(event_states):
            self._state_index_within_event += 1
            return self.current_state()

        if self._event_index + 1 < self._simulation_result.n_events:
            self._event_index += 1
            self._state_index_within_event = 0
        return self.current_state()

    def previous_state(self) -> EventDisplayState:
        """Move back to the previous conditional state or previous event."""
        if self._state_index_within_event > 0:
            self._state_index_within_event -= 1
            return self.current_state()

        if self._event_index > 0:
            self._event_index -= 1
            previous_event_states = self._states_for_event(self._event_index)
            self._state_index_within_event = len(previous_event_states) - 1
        return self.current_state()

    def _states_for_event(self, event_index: int) -> list[EventDisplayState]:
        """Build and cache the display states needed for one event."""
        if event_index not in self._event_states_cache:
            self._event_states_cache[event_index] = build_event_states_for_event(
                event_index,
                self._prepared_conditionals,
                self._gui_config,
            )
        return self._event_states_cache[event_index]


def show_event_display(config: Config, simulation_result: SimulationResult) -> None:
    """Open the step-by-step event display viewer."""
    gui_config = load_gui_config(config)
    prepared_conditionals = prepare_conditionals(config, simulation_result)
    display_bounds = compute_display_bounds(config.detectors, config.theta_max)
    navigator = EventNavigator(simulation_result, prepared_conditionals, gui_config)
    controller = EventDisplayController(
        config=config,
        simulation_result=simulation_result,
        gui_config=gui_config,
        navigator=navigator,
        display_bounds=display_bounds,
    )
    controller.show()


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


def build_event_states_for_event(
    event_index: int,
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
        return [
            EventDisplayState(
                event_index=event_index,
                conditional_index=None,
                step_index_within_event=0,
                step_count_within_event=1,
                conditional_name=None,
                state_name="default",
                state_description="No geometrically relevant conditional for this event.",
                track_color=gui_config.default_track_color,
            )
        ]

    event_states: list[EventDisplayState] = []
    step_count = len(relevant_conditionals)
    for step_index, conditional in enumerate(relevant_conditionals):
        if not bool(conditional.fired_given[event_index]):
            state_name = "geometric-only"
            state_description = "Given is true geometrically but false in fired mode."
            track_color = gui_config.track_color_geometric_only
        elif not bool(conditional.fired_numerator[event_index]):
            state_name = "fired-given-only"
            state_description = "Given is true in fired mode but numerator is false."
            track_color = gui_config.track_color_fired_given_only
        else:
            state_name = "fired-joint"
            state_description = "Given and numerator are both true in fired mode."
            track_color = gui_config.track_color_fired_joint

        event_states.append(
            EventDisplayState(
                event_index=event_index,
                conditional_index=conditional.index,
                step_index_within_event=step_index,
                step_count_within_event=step_count,
                conditional_name=conditional.name,
                state_name=state_name,
                state_description=state_description,
                track_color=track_color,
            )
        )

    return event_states


def compute_display_bounds(detectors: list[Detector], theta_max: float) -> DisplayBounds:
    """Compute the finite box used to clip displayed event tracks."""
    x_min, x_max, y_min, y_max, _ = generation_region(detectors, theta_max)
    z_lower_bounds = [float(detector.lower_bounds[2]) for detector in detectors]
    z_upper_bounds = [float(detector.upper_bounds[2]) for detector in detectors]
    min_z = min(z_lower_bounds)
    max_z = max(z_upper_bounds)
    vertical_span = max_z - min_z

    top_margin = 0.1 * max(abs(max_z), vertical_span)
    bottom_margin = 0.1 * max(abs(min_z), vertical_span)

    return DisplayBounds(
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        z_min=min_z - bottom_margin,
        z_max=max_z + top_margin,
    )


def clip_line_to_bounds(
    origin: np.ndarray,
    direction: np.ndarray,
    bounds: DisplayBounds,
) -> tuple[np.ndarray, np.ndarray]:
    """Clip an infinite line to the finite display box."""
    t_min = -math.inf
    t_max = math.inf

    axis_bounds = (
        (bounds.x_min, bounds.x_max),
        (bounds.y_min, bounds.y_max),
        (bounds.z_min, bounds.z_max),
    )

    for axis_index, (axis_min, axis_max) in enumerate(axis_bounds):
        axis_origin = float(origin[axis_index])
        axis_direction = float(direction[axis_index])

        if axis_direction == 0.0:
            if axis_origin < axis_min or axis_origin > axis_max:
                raise ValueError("Track does not intersect the display bounds.")
            continue

        t_first = (axis_min - axis_origin) / axis_direction
        t_second = (axis_max - axis_origin) / axis_direction
        axis_t_min = min(t_first, t_second)
        axis_t_max = max(t_first, t_second)

        t_min = max(t_min, axis_t_min)
        t_max = min(t_max, axis_t_max)

    if t_min > t_max:
        raise ValueError("Track does not intersect the display bounds.")

    return origin + t_min * direction, origin + t_max * direction


class EventDisplayController:
    """Own the PyVista scene and update it as the user steps through events."""

    def __init__(
        self,
        config: Config,
        simulation_result: SimulationResult,
        gui_config: GUIConfig,
        navigator: EventNavigator,
        display_bounds: DisplayBounds,
    ) -> None:
        """Build the controller and its base detector scene."""
        self._config = config
        self._simulation_result = simulation_result
        self._gui_config = gui_config
        self._navigator = navigator
        self._display_bounds = display_bounds
        self._plotter = build_plotter(config.detectors, gui_config)

    def show(self) -> None:
        """Register callbacks, draw the first state, and open the window."""
        self._plotter.add_key_event("Right", self._show_next_state)
        self._plotter.add_key_event("Left", self._show_previous_state)
        self._plotter.add_key_event("q", self._close)
        self._plotter.add_key_event("Escape", self._close)
        self._render_current_state()
        self._plotter.show()

    def _show_next_state(self) -> None:
        """Advance to the next state and redraw the scene."""
        self._navigator.next_state()
        self._render_current_state()

    def _show_previous_state(self) -> None:
        """Move back to the previous state and redraw the scene."""
        self._navigator.previous_state()
        self._render_current_state()

    def _close(self) -> None:
        """Close the PyVista window."""
        self._plotter.close()

    def _render_current_state(self) -> None:
        """Redraw detectors, track, and status text for the current state."""
        pv = _require_pyvista()
        state = self._navigator.current_state()
        event_index = state.event_index

        detector_event_colors: dict[str, Any] = {}
        for detector in self._simulation_result.detectors:
            crossed = bool(self._simulation_result.crossed[detector.name][event_index])
            fired = bool(self._simulation_result.fired[detector.name][event_index])
            if crossed and fired:
                detector_event_colors[detector.name] = "green"
            elif crossed:
                detector_event_colors[detector.name] = "red"

        render_detector_colors(
            self._plotter,
            self._simulation_result.detectors,
            self._gui_config,
            detector_event_colors,
        )

        origin = self._simulation_result.tracks.origins[event_index]
        direction = self._simulation_result.tracks.directions[event_index]
        line_start, line_end = clip_line_to_bounds(origin, direction, self._display_bounds)
        track_mesh = pv.Line(line_start, line_end)
        self._plotter.add_mesh(
            track_mesh,
            color=state.track_color,
            line_width=self._gui_config.line_width,
            name="current_track",
            reset_camera=False,
        )

        self._plotter.add_text(
            _build_status_text(state, self._simulation_result.n_events),
            position="upper_left",
            font_size=10,
            name="viewer_status",
        )
        self._plotter.render()


def _build_status_text(state: EventDisplayState, total_events: int) -> str:
    """Build the overlay text shown inside the event display."""
    lines = [
        f"Event: {state.event_index + 1} / {total_events}",
        f"State in event: {state.step_index_within_event + 1} / {state.step_count_within_event}",
        f"Track state: {state.state_name}",
        state.state_description,
    ]

    if state.conditional_name is None:
        lines.append("Conditional: none")
    else:
        lines.append(f"Conditional: {state.conditional_name}")

    lines.append("Keys: Left/Right step, q quits")
    return "\n".join(lines)


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
