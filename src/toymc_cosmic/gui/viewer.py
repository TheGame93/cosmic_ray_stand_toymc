"""Step-by-step event display for the optional GUI."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable

import numpy as np

from ..config import Config
from ..geometry import Detector, generation_region
from ..logic import evaluate, extract_names
from ..simulation import SimulationResult
from .config import GUIConfig, load_gui_config
from .scene import (
    apply_camera_position,
    build_plotter,
    build_startup_camera_position,
    detector_scene_bounds,
    plotter_viewport_aspect_ratio,
    render_detector_colors,
)


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


@dataclass(frozen=True)
class DisplayBounds:
    """Axis-aligned box used to clip the displayed event track."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float


@dataclass(frozen=True)
class NavigationButtonSpec:
    """Describe one icon-only action button shown in the event display."""

    name: str
    icon_kind: str
    position: tuple[float, float]


BUTTON_SIZE_PX = 24
BUTTON_GAP_PX = 10
BUTTON_LEFT_PADDING_PX = 18
BUTTON_BORDER_PX = 3
BUTTON_BACKGROUND_RGB = np.array([245, 245, 245], dtype=np.uint8)
BUTTON_BORDER_RGB = np.array([180, 180, 180], dtype=np.uint8)
BUTTON_ICON_RGB = np.array([70, 70, 70], dtype=np.uint8)
BUTTON_PRESSED_ICON_RGB = np.array([30, 30, 30], dtype=np.uint8)
BUTTON_PRESSED_FILL_RGB = np.array([220, 220, 220], dtype=np.uint8)

LEGEND_FONT_SIZE = 10
LEGEND_LINE_COUNT = 8
LEGEND_LINE_HEIGHT_PX = 20
LEGEND_LEFT_MARGIN_PX = 10
LEGEND_TOP_MARGIN_PX = 10

# Bottom-left corner layout: a vertical stack of [axes triad] above
# [button row] above [key-hint text], all left-aligned. Each constant
# below feeds directly into the next, so the rows can never overlap by
# construction -- editing one without the others would silently
# reintroduce overlap, so keep this block together.
STACK_BOTTOM_MARGIN_PX = 12  # window bottom edge -> key-hint text baseline
STACK_ROW_GAP_PX = 10  # vertical breathing room between each stacked row
NAV_HELP_TEXT = "Keys: Left/Right for Previous/Next state, q exit"
BUTTON_ROW_Y_PX = float(STACK_BOTTOM_MARGIN_PX + LEGEND_LINE_HEIGHT_PX + STACK_ROW_GAP_PX)
AXES_EXTRA_LIFT_PX = -50.0  # lower the axes triad
AXES_HORIZONTAL_SHIFT_PX = -90.0  # positive nudges the axes triad right, negative left
BOTTOM_STACK_RESERVE_PX = float(BUTTON_ROW_Y_PX + BUTTON_SIZE_PX + STACK_ROW_GAP_PX + AXES_EXTRA_LIFT_PX)



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


def show_event_display(config: Config, simulation_result: SimulationResult) -> None:
    """Open the step-by-step event display viewer."""
    if not config.conditionals:
        raise ValueError(
            "Event display requires at least one logic.conditional entry because relevant tracks are conditional-driven."
        )

    gui_config = load_gui_config(config)
    prepared_conditionals = prepare_conditionals(config, simulation_result)
    relevant_event_indices = collect_relevant_event_indices(prepared_conditionals)
    if not relevant_event_indices:
        raise ValueError(
            "No geometrically relevant tracks were found for the configured conditionals."
        )
    display_bounds = compute_display_bounds(config.detectors, config.theta_max)
    navigator = EventNavigator(relevant_event_indices, prepared_conditionals, gui_config)
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


def build_navigation_button_specs() -> list[NavigationButtonSpec]:
    """Return the fixed horizontal button row, left-aligned directly under the axes triad."""
    button_y = BUTTON_ROW_Y_PX
    first_button_x = float(BUTTON_LEFT_PADDING_PX)
    button_stride = float(BUTTON_SIZE_PX + BUTTON_GAP_PX)

    return [
        NavigationButtonSpec("Home", "home", (first_button_x + 0.0 * button_stride, button_y)),
        NavigationButtonSpec("Previous", "previous", (first_button_x + 1.0 * button_stride, button_y)),
        NavigationButtonSpec("Next", "next", (first_button_x + 2.0 * button_stride, button_y)),
    ]


def build_button_texture_pixels(
    icon_kind: str,
    *,
    is_pressed: bool,
    size: int = BUTTON_SIZE_PX,
) -> np.ndarray:
    """Build one RGB texture for a button with a centered icon."""
    if size <= 0:
        raise ValueError("Button texture size must be positive.")

    pixels = np.empty((size, size, 3), dtype=np.uint8)
    pixels[:, :] = BUTTON_BACKGROUND_RGB
    pixels[0, :] = BUTTON_BORDER_RGB
    pixels[-1, :] = BUTTON_BORDER_RGB
    pixels[:, 0] = BUTTON_BORDER_RGB
    pixels[:, -1] = BUTTON_BORDER_RGB

    fill_start = BUTTON_BORDER_PX
    fill_stop = size - BUTTON_BORDER_PX
    fill_color = BUTTON_PRESSED_FILL_RGB if is_pressed else BUTTON_BACKGROUND_RGB
    pixels[fill_start:fill_stop, fill_start:fill_stop] = fill_color

    icon_color = BUTTON_PRESSED_ICON_RGB if is_pressed else BUTTON_ICON_RGB
    _draw_button_icon(pixels, icon_kind, icon_color)
    return pixels


def _draw_button_icon(
    pixels: np.ndarray,
    icon_kind: str,
    icon_color: np.ndarray,
) -> None:
    """Paint one of the supported button icons into the texture array."""
    size = pixels.shape[0]
    if icon_kind == "home":
        margin = max(5, size // 4)
        pixels[margin:size - margin, margin:size - margin] = icon_color
        return

    if icon_kind not in {"previous", "next"}:
        raise ValueError(f"Unsupported button icon kind: {icon_kind}")

    next_arrow_pixels = np.zeros((size, size), dtype=bool)
    margin = max(4, size // 6)
    center = size // 2
    tail_half_height = max(2, size // 10)
    tail_start = margin
    head_base_x = size - margin - max(6, size // 4)
    tip_x = size - margin

    next_arrow_pixels[
        center - tail_half_height:center + tail_half_height + 1,
        tail_start:head_base_x,
    ] = True

    head_half_height = max(5, size // 4)
    for row_offset in range(-head_half_height, head_half_height + 1):
        row_index = center + row_offset
        if row_index < 0 or row_index >= size:
            continue

        head_tip_offset = int(
            round((1.0 - abs(row_offset) / max(head_half_height, 1)) * (tip_x - head_base_x))
        )
        head_end = head_base_x + max(head_tip_offset, 1)
        next_arrow_pixels[row_index, head_base_x:head_end] = True

    arrow_pixels = next_arrow_pixels
    if icon_kind == "previous":
        arrow_pixels = np.flip(next_arrow_pixels, axis=1)

    pixels[arrow_pixels] = icon_color


def create_button_image_data(pv: Any, pixels: np.ndarray) -> Any:
    """Convert a texture RGB array into the image object expected by VTK buttons."""
    size = int(pixels.shape[0])
    image_data = pv.ImageData(dimensions=(size, size, 1))
    image_data.point_data["texture"] = pixels.reshape(size * size, 3).astype(np.uint8)
    return image_data


def create_textured_button_widget(
    plotter: Any,
    pv: Any,
    *,
    label: str,
    position: tuple[float, float],
    size: int,
    texture_off: np.ndarray,
    texture_on: np.ndarray,
    callback: Callable[[bool], None],
) -> Any:
    """Create one low-level textured VTK button widget."""
    vtk = pv._vtk

    button_representation = vtk.vtkTexturedButtonRepresentation2D()
    button_representation.SetNumberOfStates(2)
    button_representation.SetState(0)
    button_representation.SetButtonTexture(0, create_button_image_data(pv, texture_off))
    button_representation.SetButtonTexture(1, create_button_image_data(pv, texture_on))
    button_representation.SetPlaceFactor(1)
    button_representation.PlaceWidget(
        [
            position[0],
            position[0] + size,
            position[1],
            position[1] + size,
            0.0,
            0.0,
        ]
    )

    button_widget = vtk.vtkButtonWidget()
    button_widget.SetInteractor(plotter.iren.interactor)
    button_widget.SetRepresentation(button_representation)
    button_widget.SetCurrentRenderer(plotter.renderer)
    button_widget.On()

    def handle_state_change(widget: Any, _event: Any) -> None:
        state = bool(widget.GetRepresentation().GetState())
        callback(state)

    button_widget.AddObserver(vtk.vtkCommand.StateChangedEvent, handle_state_change)
    return button_widget


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
        self._plotter = build_plotter(
            config.detectors,
            gui_config,
            reserve_bottom_px=BOTTOM_STACK_RESERVE_PX,
            shift_axes_right_px=AXES_HORIZONTAL_SHIFT_PX,
        )
        self._initial_camera_position = build_startup_camera_position(
            detector_scene_bounds(config.detectors),
            viewport_aspect_ratio=plotter_viewport_aspect_ratio(self._plotter),
        )
        self._button_widgets: list[Any] = []

    def show(self) -> None:
        """Register callbacks, draw the first state, and open the window."""
        self._plotter.add_key_event("Right", self._show_next_state)
        self._plotter.add_key_event("Left", self._show_previous_state)
        self._plotter.add_key_event("q", self._close)
        self._plotter.add_key_event("Escape", self._close)
        self._render_current_state()
        apply_camera_position(self._plotter, self._initial_camera_position)
        self._add_navigation_buttons()
        self._add_nav_help_text()
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

    def _reset_view(self) -> None:
        """Restore the initial camera without changing event navigation state."""
        apply_camera_position(self._plotter, self._initial_camera_position)
        self._plotter.render()

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

        detector_event_opacities = self._build_detector_opacity_map(state)
        render_detector_colors(
            self._plotter,
            self._simulation_result.detectors,
            self._gui_config,
            detector_event_colors,
            detector_event_opacities,
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

        window_height = float(self._plotter.window_size[1])
        legend_top_y = (
            window_height
            - LEGEND_TOP_MARGIN_PX
            - LEGEND_LINE_COUNT * LEGEND_LINE_HEIGHT_PX
        )
        self._render_legend(state, legend_top_y)
        self._plotter.render()

    def _render_legend(self, state: EventDisplayState, legend_top_y: float) -> None:
        """Draw the merged status/legend block as one framed box plus one colored sentence.

        This is one visually seamless box built from three layers of text
        actors, all sharing the same anchor position:

        - ``legend_box``: the framed box, sized and positioned from the
          real eight-line content, but drawn in white (matching
          ``background_color``) and bold. Because its text is invisible
          (white on white), only its white fill and black frame border are
          actually seen -- but because it is real, bold content (not
          filler), PyVista/VTK sizes the frame to fit the eventual bold
          "Given .../ Numerator ..." sentence, so long ``given``/
          ``numerator`` expressions or that sentence simply widen the box
          instead of being clipped.
        - ``legend_text``: the actual visible content, in plain (non-bold)
          black, positioned identically but with no background/frame of
          its own so it sits transparently on top of ``legend_box``'s
          white fill. Its last line is left blank -- if it instead
          repeated the real sentence text in non-bold black, that copy
          would peek out from under the bold colored overlay below,
          because bold and non-bold renderings of the same string use
          different glyph shapes and spacing and never align
          pixel-for-pixel (this was the original "ghosting" bug).
        - ``legend_sentence``: just the final "Given .../ Numerator ..."
          line, bold and colored with ``state.track_color``, with no
          background/frame of its own. Because nothing non-bold sits
          directly underneath it (``legend_box``'s copy is invisible,
          ``legend_text``'s copy is blank), it renders cleanly with no
          double-image artifact.

        ``legend_box`` (bold) and ``legend_text`` (non-bold) may have very
        slightly different internal line-to-line pitch for lines 1-7,
        since bold and non-bold fonts can have marginally different line
        height metrics. That's harmless here: those lines are either
        invisible (in ``legend_box``) or the only visible copy (in
        ``legend_text``), so the two never need to align the way the
        bold/colored sentence line does.
        """
        legend_lines = _build_legend_lines(state, self._simulation_result.n_events)

        sizing_text = "\n".join(legend_lines)
        legend_box_actor = self._plotter.add_text(
            sizing_text,
            position=(LEGEND_LEFT_MARGIN_PX, legend_top_y),
            font_size=LEGEND_FONT_SIZE,
            color="white",
            name="legend_box",
        )
        legend_box_actor.prop.background_color = "white"
        legend_box_actor.prop.background_opacity = 1.0
        legend_box_actor.prop.frame_color = "black"
        legend_box_actor.prop.frame_width = 1
        legend_box_actor.prop.show_frame = True
        legend_box_actor.prop.bold = True

        # The sentence line is blanked here -- it is rendered only by the
        # bold `legend_sentence` overlay below.
        visible_text = "\n".join(legend_lines[:-1] + [""])
        text_actor = self._plotter.add_text(
            visible_text,
            position=(LEGEND_LEFT_MARGIN_PX, legend_top_y),
            font_size=LEGEND_FONT_SIZE,
            color="black",
            name="legend_text",
        )
        text_actor.prop.show_frame = False

        sentence_actor = self._plotter.add_text(
            _build_legend_sentence_text(state),
            position=(LEGEND_LEFT_MARGIN_PX, legend_top_y),
            font_size=LEGEND_FONT_SIZE,
            color=state.track_color,
            name="legend_sentence",
        )
        sentence_actor.prop.show_frame = False
        sentence_actor.prop.bold = True

    def _build_detector_opacity_map(self, state: EventDisplayState) -> dict[str, float]:
        """Dim detectors not referenced by the active conditional."""
        detector_opacities: dict[str, float] = {}
        for detector in self._simulation_result.detectors:
            if detector.name in state.involved_detector_names:
                detector_opacities[detector.name] = 0.35
            else:
                detector_opacities[detector.name] = 0.05
        return detector_opacities

    def _add_navigation_buttons(self) -> None:
        """Add one horizontal row of icon-only action buttons under the axes widget."""
        action_map: dict[str, Callable[[], None]] = {
            "Home": self._reset_view,
            "Previous": self._show_previous_state,
            "Next": self._show_next_state,
        }

        for button_spec in build_navigation_button_specs():
            action = action_map[button_spec.name]
            self._add_action_button(button_spec, action)

    def _add_action_button(
        self,
        button_spec: NavigationButtonSpec,
        action: Callable[[], None],
    ) -> None:
        """Create one textured action button and keep its widget alive."""
        pv = _require_pyvista()
        widget_holder: dict[str, Any] = {}

        def callback(is_checked: bool) -> None:
            if not is_checked:
                return

            action()

            # These widgets are checkbox-style in the installed PyVista version.
            # Reset them immediately so they behave like stateless action buttons.
            widget = widget_holder.get("widget")
            if widget is not None:
                widget.GetRepresentation().SetState(0)

        texture_off = build_button_texture_pixels(button_spec.icon_kind, is_pressed=False)
        texture_on = build_button_texture_pixels(button_spec.icon_kind, is_pressed=True)
        widget_holder["widget"] = create_textured_button_widget(
            self._plotter,
            pv,
            label=button_spec.name,
            position=button_spec.position,
            size=BUTTON_SIZE_PX,
            texture_off=texture_off,
            texture_on=texture_on,
            callback=callback,
        )
        self._button_widgets.append(widget_holder["widget"])

    def _add_nav_help_text(self) -> None:
        """Draw the static key-binding hint text once, at the bottom of the axes/button stack.

        This text never changes between navigation steps, so it is added
        once here (like the button widgets) instead of being redrawn on
        every `_render_current_state` call.
        """
        self._plotter.add_text(
            NAV_HELP_TEXT,
            position=(BUTTON_LEFT_PADDING_PX, STACK_BOTTOM_MARGIN_PX),
            font_size=LEGEND_FONT_SIZE,
            name="nav_help_text",
        )


def _build_legend_lines(state: EventDisplayState, total_events: int) -> list[str]:
    """Build the fixed eight-line status/legend content shown in the boxed overlay.

    The two blank spacer lines are purely cosmetic grouping (event/track
    counters, then the state counter, then the given/numerator
    expressions) -- they carry no meaning of their own. The final line is
    the single dynamic "Given .../ Numerator ..." sentence; it is built by
    `_build_legend_sentence_text` and reused verbatim here so this plain,
    non-bold copy and the bold colored overlay drawn on top of it (see
    `EventDisplayController._render_legend`) can never drift out of sync.
    """
    return [
        f"Event: {state.event_index + 1} / {total_events}",
        f"Relevant track: {state.relevant_event_index + 1} / {state.relevant_event_count}",
        "",
        f"State in event: {state.step_index_within_event + 1} / {state.step_count_within_event}",
        "",
        f'numerator: "{state.numerator_expression}"',
        f'given: "{state.given_expression}"',
        _build_legend_sentence_text(state),
    ]


def _build_legend_sentence_text(state: EventDisplayState) -> str:
    """Build the single dynamic 'Given .../ Numerator ...' sentence line.

    `numerator_fired` is shown as its real computed boolean even when
    `given_fired` is False, not "N/A" -- the numerator condition is
    evaluated independently of the given condition in
    `build_event_states_for_event`, so it always has a well-defined value.
    """
    given_text = "YES" if state.given_fired else "NO"
    numerator_text = "YES" if state.numerator_fired else "NO"
    return f"Given {given_text} / Numerator {numerator_text}"


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
