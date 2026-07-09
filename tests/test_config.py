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
        self.assertEqual(config.output.detector_rate_decimals, 1)
        self.assertEqual(config.output.logic_rate_decimals, 1)

    def test_output_precision_settings_load(self) -> None:
        """Output precision settings should load from the YAML file."""
        config_text = """
        theta_max_deg: 80.0
        angular_model:
          type: cos2
        flux_hz_per_cm2: 0.01
        monte_carlo:
          n_events: 100
        output:
          detector_rate_decimals: 3
          logic_rate_decimals: 4
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        config = load_config(self._write_config(config_text))
        self.assertEqual(config.output.detector_rate_decimals, 3)
        self.assertEqual(config.output.logic_rate_decimals, 4)

    def test_negative_output_precision_raises(self) -> None:
        """Output precision values must be non-negative."""
        config_text = """
        theta_max_deg: 80.0
        angular_model:
          type: cos2
        flux_hz_per_cm2: 0.01
        monte_carlo:
          n_events: 100
        output:
          detector_rate_decimals: -1
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def test_non_integer_output_precision_raises(self) -> None:
        """Output precision values must be integers."""
        config_text = """
        theta_max_deg: 80.0
        angular_model:
          type: cos2
        flux_hz_per_cm2: 0.01
        monte_carlo:
          n_events: 100
        output:
          detector_rate_decimals: 1.5
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def test_conditional_without_mode_loads(self) -> None:
        """Conditionals should load without a mode field."""
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
          conditional:
            - name: "P(T1 | T1)"
              numerator: "T1"
              given: "T1"
        """

        config = load_config(self._write_config(config_text))
        self.assertEqual(len(config.conditionals), 1)
        self.assertEqual(config.conditionals[0].name, "P(T1 | T1)")

    def test_conditional_with_mode_raises(self) -> None:
        """Conditionals must not define mode anymore."""
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
          conditional:
            - name: "P(T1 | T1)"
              numerator: "T1"
              given: "T1"
              mode: fired
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

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
