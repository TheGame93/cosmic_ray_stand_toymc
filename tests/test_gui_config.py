"""Tests for GUI-specific configuration normalization."""

from __future__ import annotations

import pathlib
import tempfile
import textwrap
import unittest

from toymc_cosmic.config import load_config
from toymc_cosmic.gui.config import load_gui_config


class GuiConfigTests(unittest.TestCase):
    """Check normalization of the optional `gui:` config section."""

    def test_missing_gui_section_uses_defaults(self) -> None:
        """The GUI config should fall back to readable defaults."""
        config = load_config(self._write_config(""))

        gui_config = load_gui_config(config)

        self.assertEqual(gui_config.background_color, "black")
        self.assertEqual(gui_config.default_detector_color, "lightgray")
        self.assertEqual(gui_config.default_track_color, "white")
        self.assertEqual(gui_config.track_color_geometric_only, "orange")
        self.assertEqual(gui_config.track_color_fired_given_only, "gold")
        self.assertEqual(gui_config.track_color_fired_joint, "lime")
        self.assertEqual(gui_config.line_width, 4.0)
        self.assertEqual(gui_config.source_color, "orange")
        self.assertEqual(gui_config.source_opacity, 0.25)

    def test_gui_overrides_load(self) -> None:
        """Detector and track colors should load from the raw GUI mapping."""
        config = load_config(
            self._write_config(
                """
                gui:
                  background_color: navy
                  default_detector_color: silver
                  detector_colors:
                    T1: tomato
                  default_track_color: white
                  track_color_geometric_only: orange
                  track_color_fired_given_only: [0.8, 0.8, 0.1]
                  track_color_fired_joint: "#00ff00"
                  line_width: 6
                  source_color: crimson
                  source_opacity: 0.5
                """
            )
        )

        gui_config = load_gui_config(config)

        self.assertEqual(gui_config.background_color, "navy")
        self.assertEqual(gui_config.default_detector_color, "silver")
        self.assertEqual(gui_config.detector_colors["T1"], "tomato")
        self.assertEqual(gui_config.track_color_fired_given_only, (0.8, 0.8, 0.1))
        self.assertEqual(gui_config.track_color_fired_joint, "#00ff00")
        self.assertEqual(gui_config.line_width, 6.0)
        self.assertEqual(gui_config.source_color, "crimson")
        self.assertEqual(gui_config.source_opacity, 0.5)

    def test_source_opacity_out_of_range_raises(self) -> None:
        """gui.source_opacity must stay within the inclusive [0, 1] range."""
        config = load_config(
            self._write_config(
                """
                gui:
                  source_opacity: 1.5
                """
            )
        )

        with self.assertRaises(ValueError):
            load_gui_config(config)

    def test_unknown_detector_override_raises(self) -> None:
        """GUI detector color overrides must reference known detector names."""
        config = load_config(
            self._write_config(
                """
                gui:
                  detector_colors:
                    T2: orange
                """
            )
        )

        with self.assertRaises(ValueError):
            load_gui_config(config)

    def _write_config(self, extra_text: str) -> pathlib.Path:
        """Write a minimal config file with optional extra GUI content."""
        base_config_text = """
        source_model:
          type: cosmic
          model: cos2
          theta_max_deg: 80.0
          flux_hz_per_cm2: 0.01
        monte_carlo:
          n_events: 10
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """
        config_text = textwrap.dedent(base_config_text).strip()
        extra_block = textwrap.dedent(extra_text).strip()
        if extra_block:
            config_text = f"{config_text}\n{extra_block}"

        temp_dir = tempfile.mkdtemp()
        path = pathlib.Path(temp_dir) / "gui_config.yaml"
        path.write_text(config_text + "\n")
        return path
