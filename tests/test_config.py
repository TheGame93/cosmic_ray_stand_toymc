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

    def test_valid_cosmic_config_loads(self) -> None:
        """A valid cosmic config should load into a Config object."""
        config = load_config(
            self._write_config(
                """
                seed: 1
                source_model:
                  type: cosmic
                  model: cos2
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
            )
        )

        self.assertEqual(config.seed, 1)
        self.assertEqual(config.logic_expressions, ["T1"])
        self.assertIsInstance(config.source_model, CosmicSourceConfig)

    def test_output_precision_settings_load(self) -> None:
        """Output precision settings should load from the YAML file."""
        config = load_config(
            self._write_config(
                """
                source_model:
                  type: cosmic
                  model: cos2
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
            )
        )

        self.assertEqual(config.output.detector_rate_decimals, 3)
        self.assertEqual(config.output.logic_rate_decimals, 4)

    def test_negative_output_precision_raises(self) -> None:
        """Output precision values must be non-negative."""
        with self.assertRaises(ConfigError):
            load_config(
                self._write_config(
                    """
                    source_model:
                      type: cosmic
                      model: cos2
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
                )
            )

    def test_conditional_with_mode_raises(self) -> None:
        """Conditionals must not define mode."""
        with self.assertRaises(ConfigError):
            load_config(
                self._write_config(
                    """
                    source_model:
                      type: cosmic
                      model: cos2
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
                )
            )

    def test_duplicate_detector_names_raise(self) -> None:
        """Duplicate detector names must be rejected."""
        with self.assertRaises(ConfigError):
            load_config(
                self._write_config(
                    """
                    source_model:
                      type: cosmic
                      model: cos2
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
                )
            )

    def test_unknown_detector_name_in_logic_raises(self) -> None:
        """Logic expressions must reference known detectors only."""
        with self.assertRaises(ConfigError):
            load_config(
                self._write_config(
                    """
                    source_model:
                      type: cosmic
                      model: cos2
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
                )
            )

    def test_missing_source_model_raises(self) -> None:
        """A missing source_model block must be rejected."""
        with self.assertRaises(ConfigError):
            load_config(
                self._write_config(
                    """
                    monte_carlo:
                      n_events: 100
                    detectors:
                      - name: T1
                        center: [0, 0, 10]
                        size: [2, 2, 1]
                        efficiency: 0.9
                    """
                )
            )

    def test_unknown_source_model_type_raises(self) -> None:
        """An unrecognized source_model.type must be rejected."""
        with self.assertRaises(ConfigError):
            load_config(
                self._write_config(
                    """
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
                )
            )

    def test_cosmic_unsupported_model_raises(self) -> None:
        """source_model.model must be 'cos2' for cosmic sources."""
        with self.assertRaises(ConfigError):
            load_config(
                self._write_config(
                    """
                    source_model:
                      type: cosmic
                      model: flat
                      flux_hz_per_cm2: 0.01
                    monte_carlo:
                      n_events: 100
                    detectors:
                      - name: T1
                        center: [0, 0, 10]
                        size: [2, 2, 1]
                        efficiency: 0.9
                    """
                )
            )

    def test_beam_uniform_loads(self) -> None:
        """A valid uniform beam source should load with a one-element size."""
        config = load_config(
            self._write_config(
                """
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
            )
        )

        self.assertIsInstance(config.source_model, BeamSourceConfig)
        assert isinstance(config.source_model, BeamSourceConfig)
        self.assertEqual(config.source_model.profile, "uniform")
        self.assertEqual(config.source_model.center, (0.0, 1.0))
        self.assertEqual(config.source_model.size, (10.0,))

    def test_beam_gaussian_loads(self) -> None:
        """A valid gaussian beam source should load with a two-element size."""
        config = load_config(
            self._write_config(
                """
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
            )
        )

        assert isinstance(config.source_model, BeamSourceConfig)
        self.assertEqual(config.source_model.size, (10.0, 8.0))

    def test_beam_uniform_wrong_size_length_raises(self) -> None:
        """A uniform beam profile must have exactly one size element."""
        with self.assertRaises(ConfigError):
            load_config(
                self._write_config(
                    """
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
                )
            )

    def test_beam_divergence_rejected(self) -> None:
        """The unimplemented divergence profile must be rejected at config-load time."""
        with self.assertRaises(ConfigError):
            load_config(
                self._write_config(
                    """
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
                )
            )

    def test_object_config_loads_with_derived_front_emission(self) -> None:
        """An object source should derive front emission from activity and yield."""
        config = load_config(
            self._write_config(
                """
                source_model:
                  type: object
                  center: [0.0, 0.0, -5.0]
                  diameter: 2.0
                  normal: [1.0, 1.0, 0.0]
                  angular_model: uniform
                  activity_bq: 1000.0
                  yield_per_decay: 0.5
                monte_carlo:
                  n_events: 100
                detectors:
                  - name: T1
                    center: [0, 0, 10]
                    size: [2, 2, 1]
                    efficiency: 0.9
                """
            )
        )

        assert isinstance(config.source_model, ObjectSourceConfig)
        self.assertEqual(config.source_model.center, (0.0, 0.0, -5.0))
        self.assertEqual(config.source_model.diameter, 2.0)
        self.assertEqual(config.source_model.normal, (1.0, 1.0, 0.0))
        self.assertEqual(config.source_model.angular_model, "uniform")
        self.assertEqual(config.source_model.activity_bq, 1000.0)
        self.assertEqual(config.source_model.yield_per_decay, 0.5)
        self.assertIsNone(config.source_model.surface_emission_rate_hz)
        self.assertEqual(config.source_model.front_emission_rate_hz(), 250.0)

    def test_object_override_only_loads(self) -> None:
        """An object source may specify only the authoritative front-emission override."""
        config = load_config(
            self._write_config(
                """
                source_model:
                  type: object
                  center: [0.0, 0.0, -5.0]
                  diameter: 2.0
                  normal: [0.0, 0.0, 1.0]
                  angular_model: cosine-weighted
                  surface_emission_rate_hz: 321.0
                monte_carlo:
                  n_events: 100
                detectors:
                  - name: T1
                    center: [0, 0, 10]
                    size: [2, 2, 1]
                    efficiency: 0.9
                """
            )
        )

        assert isinstance(config.source_model, ObjectSourceConfig)
        self.assertIsNone(config.source_model.activity_bq)
        self.assertEqual(config.source_model.yield_per_decay, 1.0)
        self.assertEqual(config.source_model.front_emission_rate_hz(), 321.0)

    def test_object_requires_activity_or_override(self) -> None:
        """An object source must define either activity or front emission."""
        with self.assertRaises(ConfigError):
            load_config(
                self._write_config(
                    """
                    source_model:
                      type: object
                      center: [0.0, 0.0, 0.0]
                      diameter: 2.0
                      normal: [0.0, 0.0, 1.0]
                      angular_model: uniform
                    monte_carlo:
                      n_events: 100
                    detectors:
                      - name: T1
                        center: [0, 0, 10]
                        size: [2, 2, 1]
                        efficiency: 0.9
                    """
                )
            )

    def test_object_zero_normal_raises(self) -> None:
        """The object-source normal vector must be non-zero."""
        with self.assertRaises(ConfigError):
            load_config(
                self._write_config(
                    """
                    source_model:
                      type: object
                      center: [0.0, 0.0, 0.0]
                      diameter: 2.0
                      normal: [0.0, 0.0, 0.0]
                      angular_model: uniform
                      activity_bq: 1000.0
                    monte_carlo:
                      n_events: 100
                    detectors:
                      - name: T1
                        center: [0, 0, 10]
                        size: [2, 2, 1]
                        efficiency: 0.9
                    """
                )
            )

    def test_object_material_dependent_rejected(self) -> None:
        """The unimplemented material-dependent model must be rejected at config-load time."""
        with self.assertRaises(ConfigError):
            load_config(
                self._write_config(
                    """
                    source_model:
                      type: object
                      center: [0.0, 0.0, 0.0]
                      diameter: 2.0
                      normal: [0.0, 0.0, 1.0]
                      angular_model: material-dependent
                      activity_bq: 1000.0
                    monte_carlo:
                      n_events: 100
                    detectors:
                      - name: T1
                        center: [0, 0, 10]
                        size: [2, 2, 1]
                        efficiency: 0.9
                    """
                )
            )

    def test_object_yield_requires_activity(self) -> None:
        """yield_per_decay must not be supplied without activity_bq."""
        with self.assertRaises(ConfigError):
            load_config(
                self._write_config(
                    """
                    source_model:
                      type: object
                      center: [0.0, 0.0, 0.0]
                      diameter: 2.0
                      normal: [0.0, 0.0, 1.0]
                      angular_model: uniform
                      yield_per_decay: 0.8
                      surface_emission_rate_hz: 50.0
                    monte_carlo:
                      n_events: 100
                    detectors:
                      - name: T1
                        center: [0, 0, 10]
                        size: [2, 2, 1]
                        efficiency: 0.9
                    """
                )
            )

    def _write_config(self, config_text: str) -> pathlib.Path:
        """Write a temporary YAML config file and return its path."""
        temp_dir = tempfile.mkdtemp()
        path = pathlib.Path(temp_dir) / "config.yaml"
        path.write_text(textwrap.dedent(config_text).strip() + "\n")
        return path
