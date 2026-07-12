"""Screen-position and size constants for the event-display GUI.

Single source of truth for "where does X appear on screen" -- button
sizes/positions, the top-left legend box, and the bottom-left stack of
[axes triad] above [button row] above [key-hint text]. Kept as one
constants-only module (no functions, no PyVista) so it stays cheap to load
and so the bottom-stack constants, which are deliberately coupled to each
other (see the block comment below), cannot be edited in isolation by only
looking at one of several files.

Consumed by `gui/buttons.py` (button sizing/position) and `gui/viewer.py`
(legend box position, bottom-stack position, axes nudging).
"""

from __future__ import annotations

import numpy as np


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
