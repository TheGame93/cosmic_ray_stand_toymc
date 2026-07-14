"""Step-by-step event display for the optional GUI.

This is the PyVista-facing orchestrator: `show_event_display` wires the
pure-logic pieces together (event/conditional navigation from
`gui/event_state.py`, track clipping from `gui/track_bounds.py`, button
widgets from `gui/buttons.py`, legend text from `gui/legend.py`, and
screen-position constants from `gui/layout.py`), and
`EventDisplayController` owns the actual PyVista scene and redraws it as
the user steps through events. None of those sibling modules import
PyVista themselves -- this file (plus `gui/scene.py`) is the only place
that does, and only lazily, via `_require_pyvista`.
"""

from __future__ import annotations

from typing import Any, Callable

from ..config import Config
from ..simulation import SimulationResult
from ..source import build_source_model
from .buttons import (
    NavigationButtonSpec,
    build_button_texture_pixels,
    build_navigation_button_specs,
    create_textured_button_widget,
)
from .config import GUIConfig, load_gui_config
from .event_state import (
    EventDisplayState,
    EventNavigator,
    collect_relevant_event_indices,
    prepare_conditionals,
)
from .layout import (
    AXES_HORIZONTAL_SHIFT_PX,
    BOTTOM_STACK_RESERVE_PX,
    BUTTON_LEFT_PADDING_PX,
    BUTTON_SIZE_PX,
    LEGEND_FONT_SIZE,
    LEGEND_LEFT_MARGIN_PX,
    LEGEND_LINE_COUNT,
    LEGEND_LINE_HEIGHT_PX,
    LEGEND_TOP_MARGIN_PX,
    NAV_HELP_TEXT,
    STACK_BOTTOM_MARGIN_PX,
)
from .legend import build_legend_lines, build_legend_sentence_text
from .scene import (
    apply_camera_position,
    build_plotter,
    build_startup_camera_position,
    detector_scene_bounds,
    plotter_viewport_aspect_ratio,
    render_detector_colors,
    startup_view_up,
)
from .track_bounds import DisplayBounds, clip_line_to_bounds, compute_display_bounds


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
    source_model = build_source_model(config.source_model)
    display_bounds = compute_display_bounds(config.detectors, source_model)
    navigator = EventNavigator(relevant_event_indices, prepared_conditionals, gui_config)
    controller = EventDisplayController(
        config=config,
        simulation_result=simulation_result,
        gui_config=gui_config,
        navigator=navigator,
        display_bounds=display_bounds,
    )
    controller.show()


class EventDisplayController:
    """PyVista scene controller that redraws as the user steps through events."""

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
            config.source_model,
            reserve_bottom_px=BOTTOM_STACK_RESERVE_PX,
            shift_axes_right_px=AXES_HORIZONTAL_SHIFT_PX,
        )
        self._initial_camera_position = build_startup_camera_position(
            detector_scene_bounds(config.detectors),
            viewport_aspect_ratio=plotter_viewport_aspect_ratio(self._plotter),
            view_up=startup_view_up(config.source_model),
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
        legend_lines = build_legend_lines(state, self._simulation_result.n_events)

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
            build_legend_sentence_text(state),
            position=(LEGEND_LEFT_MARGIN_PX, legend_top_y),
            font_size=LEGEND_FONT_SIZE,
            color=state.track_color,
            name="legend_sentence",
        )
        sentence_actor.prop.show_frame = False
        sentence_actor.prop.bold = True

    def _build_detector_opacity_map(self, state: EventDisplayState) -> dict[str, float]:
        """Dim detectors not referenced by the active conditional; returns the per-detector opacity map."""
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
