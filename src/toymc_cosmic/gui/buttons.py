"""Low-level VTK button-widget factory for the event display's nav row.

Builds the icon textures and the raw `vtkButtonWidget`/
`vtkTexturedButtonRepresentation2D` objects used for the Home/Previous/Next
buttons. Self-contained and generic: nothing here knows about event/
conditional navigation state (see `gui/event_state.py` for that) -- these
functions only take plain positions, pixel sizes, and a `pv`/`plotter`
object passed in by the caller, so this module never imports `pyvista`
itself (kept lazy, per this project's engine/GUI dependency rule -- see
`gui/viewer.py`'s `_require_pyvista`). See `gui/layout.py` for the button
size/position constants consumed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from .layout import (
    BUTTON_BACKGROUND_RGB,
    BUTTON_BORDER_PX,
    BUTTON_BORDER_RGB,
    BUTTON_GAP_PX,
    BUTTON_ICON_RGB,
    BUTTON_LEFT_PADDING_PX,
    BUTTON_PRESSED_FILL_RGB,
    BUTTON_PRESSED_ICON_RGB,
    BUTTON_ROW_Y_PX,
    BUTTON_SIZE_PX,
)


@dataclass(frozen=True)
class NavigationButtonSpec:
    """One icon-only action button shown in the event display."""

    name: str
    icon_kind: str
    position: tuple[float, float]


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
