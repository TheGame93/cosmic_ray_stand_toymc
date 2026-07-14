"""GUI-specific configuration parsing and normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import Config


ColorValue = str | tuple[float, float, float]

COLOR_EXAMPLE_TEXT = (
    "Accepted color examples: named colors such as 'black' or 'lightgray', "
    "hex strings such as '#ff8800', or RGB triples such as [0.2, 0.6, 1.0]."
)


@dataclass(frozen=True)
class GUIConfig:
    """Normalized visualization settings for the optional GUI."""

    background_color: ColorValue
    default_detector_color: ColorValue
    detector_colors: dict[str, ColorValue]
    default_track_color: ColorValue
    track_color_geometric_only: ColorValue
    track_color_fired_given_only: ColorValue
    track_color_fired_joint: ColorValue
    line_width: float
    source_color: ColorValue
    source_opacity: float

    def detector_color(self, detector_name: str) -> ColorValue:
        """Return the configured base color for one detector."""
        return self.detector_colors.get(detector_name, self.default_detector_color)


def load_gui_config(config: Config) -> GUIConfig:
    """Normalize the optional `gui:` mapping from the engine config."""
    raw_gui = config.gui or {}

    if not isinstance(raw_gui, dict):
        raise ValueError("gui must be a mapping when provided.")

    detector_names = {detector.name for detector in config.detectors}

    raw_detector_colors = raw_gui.get("detector_colors", {})
    if not isinstance(raw_detector_colors, dict):
        raise ValueError("gui.detector_colors must be a mapping when provided.")

    detector_colors: dict[str, ColorValue] = {}
    for detector_name, raw_color in raw_detector_colors.items():
        if detector_name not in detector_names:
            raise ValueError(f"Unknown detector name in gui.detector_colors: {detector_name}")
        detector_colors[detector_name] = _read_color(
            raw_color,
            f"gui.detector_colors.{detector_name}",
        )

    return GUIConfig(
        background_color=_read_color(raw_gui.get("background_color", "black"), "gui.background_color"),
        default_detector_color=_read_color(
            raw_gui.get("default_detector_color", "lightgray"),
            "gui.default_detector_color",
        ),
        detector_colors=detector_colors,
        default_track_color=_read_color(
            raw_gui.get("default_track_color", "white"),
            "gui.default_track_color",
        ),
        track_color_geometric_only=_read_color(
            raw_gui.get("track_color_geometric_only", "orange"),
            "gui.track_color_geometric_only",
        ),
        track_color_fired_given_only=_read_color(
            raw_gui.get("track_color_fired_given_only", "gold"),
            "gui.track_color_fired_given_only",
        ),
        track_color_fired_joint=_read_color(
            raw_gui.get("track_color_fired_joint", "lime"),
            "gui.track_color_fired_joint",
        ),
        line_width=_read_positive_float(raw_gui.get("line_width", 4.0), "gui.line_width"),
        source_color=_read_color(raw_gui.get("source_color", "orange"), "gui.source_color"),
        source_opacity=_read_unit_interval_float(raw_gui.get("source_opacity", 0.25), "gui.source_opacity"),
    )


def _read_color(value: Any, field_name: str) -> ColorValue:
    """Read a GUI color value as a named string or RGB triple."""
    if isinstance(value, str):
        if not value.strip():
            raise ValueError(f"{field_name} must not be empty.")
        return value

    if isinstance(value, (list, tuple)) and len(value) == 3:
        components: list[float] = []
        for component in value:
            if isinstance(component, bool) or not isinstance(component, (int, float)):
                raise ValueError(f"{field_name} must contain numeric RGB components.")
            components.append(float(component))
        return tuple(components)

    raise ValueError(f"{field_name} must be a color string or a 3-element RGB list.")


def _read_float_value(value: Any, field_name: str) -> float:
    """Read a numeric field and convert it to float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric.")
    return float(value)


def _read_positive_float(value: Any, field_name: str) -> float:
    """Read a strictly positive float from the GUI settings."""
    numeric_value = _read_float_value(value, field_name)
    if numeric_value <= 0.0:
        raise ValueError(f"{field_name} must be strictly positive.")
    return numeric_value


def _read_unit_interval_float(value: Any, field_name: str) -> float:
    """Read a float in the inclusive `[0, 1]` range from the GUI settings."""
    numeric_value = _read_float_value(value, field_name)
    if not 0.0 <= numeric_value <= 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1.")
    return numeric_value
