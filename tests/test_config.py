"""Tests for YAML configuration loading and validation."""

from __future__ import annotations

import pathlib
import tempfile
import textwrap
import unittest

from toymc_cosmic.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    """Check valid and invalid configuration paths."""

    def test_valid_config_loads(self) -> None:
        """A valid configuration file should load into a Config object."""
        config_text = """
        seed: 1
        theta_max_deg: 80.0
        angular_model:
          type: cos2
        flux_hz_per_cm2: 0.01
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        logic:
          expressions:
            - "T1"
        """

        config = load_config(self._write_config(config_text))
        self.assertEqual(config.seed, 1)
        self.assertEqual(len(config.detectors), 1)
        self.assertEqual(config.logic_expressions, ["T1"])

    def test_duplicate_detector_names_raise(self) -> None:
        """Duplicate detector names must be rejected."""
        config_text = """
        theta_max_deg: 80.0
        angular_model:
          type: cos2
        flux_hz_per_cm2: 0.01
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
          - name: T1
            center: [0, 0, 0]
            size: [2, 2, 1]
            efficiency: 0.8
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def test_unknown_detector_name_in_logic_raises(self) -> None:
        """Logic expressions must reference known detectors only."""
        config_text = """
        theta_max_deg: 80.0
        angular_model:
          type: cos2
        flux_hz_per_cm2: 0.01
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        logic:
          expressions:
            - "T2"
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def _write_config(self, config_text: str) -> pathlib.Path:
        """Write a temporary YAML config file and return its path."""
        temp_dir = tempfile.mkdtemp()
        path = pathlib.Path(temp_dir) / "config.yaml"
        path.write_text(textwrap.dedent(config_text).strip() + "\n")
        return path
