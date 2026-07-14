"""Tests for YAML configuration loading and validation."""

from __future__ import annotations

import pathlib
import tempfile
import textwrap
import unittest

from toymc_cosmic.config import (
    BeamSourceConfig,
    ConfigError,
    CosmicSourceConfig,
    ObjectSourceConfig,
    load_config,
)


class ConfigTests(unittest.TestCase):
    """Check valid and invalid configuration paths."""

    def test_valid_config_loads(self) -> None:
        """A valid configuration file should load into a Config object."""
        config_text = """
        seed: 1
        source_model:
          type: cosmic
          model: cos2
          theta_max_deg: 80.0
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
        self.assertIsInstance(config.source_model, CosmicSourceConfig)

    def test_output_precision_settings_load(self) -> None:
        """Output precision settings should load from the YAML file."""
        config_text = """
        source_model:
          type: cosmic
          model: cos2
          theta_max_deg: 80.0
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
        source_model:
          type: cosmic
          model: cos2
          theta_max_deg: 80.0
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
        source_model:
          type: cosmic
          model: cos2
          theta_max_deg: 80.0
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
        source_model:
          type: cosmic
          model: cos2
          theta_max_deg: 80.0
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
        source_model:
          type: cosmic
          model: cos2
          theta_max_deg: 80.0
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
        source_model:
          type: cosmic
          model: cos2
          theta_max_deg: 80.0
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
        source_model:
          type: cosmic
          model: cos2
          theta_max_deg: 80.0
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

    def test_missing_source_model_raises(self) -> None:
        """A missing source_model block must be rejected."""
        config_text = """
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def test_unknown_source_model_type_raises(self) -> None:
        """An unrecognized source_model.type must be rejected."""
        config_text = """
        source_model:
          type: supernova
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def test_cosmic_theta_max_out_of_range_raises(self) -> None:
        """source_model.theta_max_deg must be strictly between 0 and 90."""
        config_text = """
        source_model:
          type: cosmic
          model: cos2
          theta_max_deg: 90.0
          flux_hz_per_cm2: 0.01
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def test_cosmic_unsupported_model_raises(self) -> None:
        """source_model.model must be 'cos2' for cosmic sources."""
        config_text = """
        source_model:
          type: cosmic
          model: flat
          theta_max_deg: 80.0
          flux_hz_per_cm2: 0.01
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def test_beam_uniform_loads(self) -> None:
        """A valid uniform beam source should load with a 1-element size."""
        config_text = """
        source_model:
          type: beam
          profile: uniform
          center: [0.0, 1.0]
          size: [10.0]
          flux_hz_per_cm2: 100.0
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        config = load_config(self._write_config(config_text))
        self.assertIsInstance(config.source_model, BeamSourceConfig)
        assert isinstance(config.source_model, BeamSourceConfig)
        self.assertEqual(config.source_model.profile, "uniform")
        self.assertEqual(config.source_model.center, (0.0, 1.0))
        self.assertEqual(config.source_model.size, (10.0,))

    def test_beam_gaussian_loads(self) -> None:
        """A valid gaussian beam source should load with a 2-element size."""
        config_text = """
        source_model:
          type: beam
          profile: gaussian
          center: [0.0, 0.0]
          size: [10.0, 8.0]
          flux_hz_per_cm2: 100.0
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        config = load_config(self._write_config(config_text))
        assert isinstance(config.source_model, BeamSourceConfig)
        self.assertEqual(config.source_model.size, (10.0, 8.0))

    def test_beam_uniform_wrong_size_length_raises(self) -> None:
        """A uniform beam profile must have exactly one size element."""
        config_text = """
        source_model:
          type: beam
          profile: uniform
          center: [0.0, 0.0]
          size: [10.0, 8.0]
          flux_hz_per_cm2: 100.0
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def test_beam_divergence_rejected(self) -> None:
        """The unimplemented divergence profile must be rejected at config-load time."""
        config_text = """
        source_model:
          type: beam
          profile: divergence
          center: [0.0, 0.0]
          size: [1.0, 2.0, 3.0, 4.0]
          flux_hz_per_cm2: 100.0
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def test_beam_unsupported_profile_raises(self) -> None:
        """Beam profile must be one of the recognized names."""
        config_text = """
        source_model:
          type: beam
          profile: pencil
          center: [0.0, 0.0]
          size: [10.0]
          flux_hz_per_cm2: 100.0
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def test_object_sphere_loads(self) -> None:
        """A valid sphere object source should load with a 1-element size."""
        config_text = """
        source_model:
          type: object
          shape: sphere
          center: [0.0, 0.0, -5.0]
          size: [2.0]
          activity_hz: 1000.0
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        config = load_config(self._write_config(config_text))
        self.assertIsInstance(config.source_model, ObjectSourceConfig)
        assert isinstance(config.source_model, ObjectSourceConfig)
        self.assertEqual(config.source_model.shape, "sphere")
        self.assertEqual(config.source_model.center, (0.0, 0.0, -5.0))
        self.assertEqual(config.source_model.size, (2.0,))
        self.assertEqual(config.source_model.activity_hz, 1000.0)

    def test_object_disk_and_box_size_lengths(self) -> None:
        """disk needs a 2-element size and box needs a 3-element size."""
        disk_text = """
        source_model:
          type: object
          shape: disk
          center: [0.0, 0.0, 0.0]
          size: [4.0, 1.0]
          activity_hz: 1000.0
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """
        box_text = """
        source_model:
          type: object
          shape: box
          center: [0.0, 0.0, 0.0]
          size: [4.0, 1.0, 2.0]
          activity_hz: 1000.0
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        disk_config = load_config(self._write_config(disk_text))
        box_config = load_config(self._write_config(box_text))
        assert isinstance(disk_config.source_model, ObjectSourceConfig)
        assert isinstance(box_config.source_model, ObjectSourceConfig)
        self.assertEqual(disk_config.source_model.size, (4.0, 1.0))
        self.assertEqual(box_config.source_model.size, (4.0, 1.0, 2.0))

    def test_object_wrong_size_length_raises(self) -> None:
        """A sphere object source must have exactly one size element."""
        config_text = """
        source_model:
          type: object
          shape: sphere
          center: [0.0, 0.0, 0.0]
          size: [2.0, 3.0]
          activity_hz: 1000.0
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def test_object_unsupported_shape_raises(self) -> None:
        """Object shape must be one of the recognized names."""
        config_text = """
        source_model:
          type: object
          shape: cube
          center: [0.0, 0.0, 0.0]
          size: [2.0]
          activity_hz: 1000.0
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def test_object_non_positive_activity_raises(self) -> None:
        """source_model.activity_hz must be strictly positive."""
        config_text = """
        source_model:
          type: object
          shape: sphere
          center: [0.0, 0.0, 0.0]
          size: [2.0]
          activity_hz: 0.0
        monte_carlo:
          n_events: 100
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [2, 2, 1]
            efficiency: 0.9
        """

        with self.assertRaises(ConfigError):
            load_config(self._write_config(config_text))

    def _write_config(self, config_text: str) -> pathlib.Path:
        """Write a temporary YAML config file and return its path."""
        temp_dir = tempfile.mkdtemp()
        path = pathlib.Path(temp_dir) / "config.yaml"
        path.write_text(textwrap.dedent(config_text).strip() + "\n")
        return path
