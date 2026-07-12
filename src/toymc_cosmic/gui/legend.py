"""Legend text builders for the event-display GUI.

Pure string building -- no PyVista here. Turns one `EventDisplayState`
(see `gui/event_state.py`) into the plain-text lines shown in the boxed
legend overlay. See `EventDisplayController._render_legend` in
`gui/viewer.py` for how these strings are actually drawn (as a white
"sizing" copy, a black visible copy, and a bold colored sentence overlay).

`build_legend_lines`/`build_legend_sentence_text` were private helpers
(leading underscore) while they lived inside `viewer.py`; now that the
controller imports them from a sibling module, the underscore was dropped
since they are legitimately public across this module boundary.
"""

from __future__ import annotations

from .event_state import EventDisplayState


def build_legend_lines(state: EventDisplayState, total_events: int) -> list[str]:
    """Build the fixed eight-line status/legend content shown in the boxed overlay.

    The two blank spacer lines are purely cosmetic grouping (event/track
    counters, then the state counter, then the given/numerator
    expressions) -- they carry no meaning of their own. The final line is
    the single dynamic "Given .../ Numerator ..." sentence; it is built by
    `build_legend_sentence_text` and reused verbatim here so this plain,
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
        build_legend_sentence_text(state),
    ]


def build_legend_sentence_text(state: EventDisplayState) -> str:
    """Build the single dynamic 'Given .../ Numerator ...' sentence line.

    `numerator_fired` is shown as its real computed boolean even when
    `given_fired` is False, not "N/A" -- the numerator condition is
    evaluated independently of the given condition in
    `build_event_states_for_event`, so it always has a well-defined value.
    """
    given_text = "YES" if state.given_fired else "NO"
    numerator_text = "YES" if state.numerator_fired else "NO"
    return f"Given {given_text} / Numerator {numerator_text}"
