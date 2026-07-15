"""Tests for CLI-specific helpers."""

from __future__ import annotations

import io
import unittest
from unittest import mock

from toymc_cosmic.cli import (
    _format_detector_rate_table,
    _format_probability,
    _format_rate_hz,
    _format_source_header,
    _render_progress,
    _validate_gui_arguments,
    build_parser,
    main,
)
from toymc_cosmic.config import BeamSourceConfig, CosmicSourceConfig, ObjectSourceConfig
from toymc_cosmic.geometry import Detector
from toymc_cosmic.rates import ProbabilityEstimate, RateEstimate


class CliTests(unittest.TestCase):
    """Check terminal progress rendering behavior."""

    def test_progress_renderer_includes_absolute_count_and_percent(self) -> None:
        """The progress line should show both count and percentage."""
        stream = io.StringIO()
        _render_progress(10000, 25000, 40.0, stream=stream)
        self.assertEqual(stream.getvalue(), "\rProgress: 10000 / 25000 (40.00%)")

    def test_progress_renderer_adds_newline_when_complete(self) -> None:
        """The final update should terminate the progress line cleanly."""
        stream = io.StringIO()
        _render_progress(25000, 25000, 100.0, stream=stream)
        self.assertEqual(stream.getvalue(), "\rProgress: 25000 / 25000 (100.00%)\n")

    def test_rate_formatter_uses_one_decimal_digit(self) -> None:
        """Rate text should be rounded to one digit after the decimal point."""
        estimate = RateEstimate(value=109.426561, error=0.580031, n_pass=1, n_total=1)
        self.assertEqual(_format_rate_hz(estimate, 1), "109.4 +/- 0.6 Hz")

    def test_rate_formatter_uses_configured_decimal_digits(self) -> None:
        """Rate text should respect the requested number of decimal digits."""
        estimate = RateEstimate(value=0.123456, error=0.004321, n_pass=1, n_total=1)
        self.assertEqual(_format_rate_hz(estimate, 3), "0.123 +/- 0.004 Hz")

    def test_probability_formatter_uses_three_decimal_digits(self) -> None:
        """Conditional probabilities should use per-thousand precision."""
        estimate = ProbabilityEstimate(value=0.941176, error=0.00619, n_joint=1, n_cond=1445)
        self.assertEqual(_format_probability(estimate), "0.941 +/- 0.006 (n_cond=1445)")

    def test_source_header_formats_cosmic_flux(self) -> None:
        """Cosmic headers should report the configured plane flux."""
        self.assertEqual(
            _format_source_header(CosmicSourceConfig(model="cos2", flux_hz_per_cm2=0.01)),
            "cosmic flux = 0.01 Hz/cm2",
        )

    def test_source_header_formats_beam_flux(self) -> None:
        """Beam headers should report the configured beam flux."""
        self.assertEqual(
            _format_source_header(
                BeamSourceConfig(profile="uniform", center=(0.0, 0.0), size=(1.0,), flux_hz_per_cm2=3.5)
            ),
            "beam flux = 3.5 Hz/cm2",
        )

    def test_source_header_formats_object_activity_and_front_emission(self) -> None:
        """Object headers should report both activity and front emission when known."""
        self.assertEqual(
            _format_source_header(
                ObjectSourceConfig(
                    center=(0.0, 0.0, 0.0),
                    diameter=1.0,
                    normal=(0.0, 0.0, 1.0),
                    angular_model="uniform",
                    activity_bq=1000.0,
                    yield_per_decay=0.5,
                    surface_emission_rate_hz=None,
                )
            ),
            "source activity = 1000 Bq, front emission = 250 Hz",
        )

    def test_source_header_formats_object_activity_as_na_when_missing(self) -> None:
        """Object headers should print `n/a` when only the front-emission override is known."""
        self.assertEqual(
            _format_source_header(
                ObjectSourceConfig(
                    center=(0.0, 0.0, 0.0),
                    diameter=1.0,
                    normal=(0.0, 0.0, 1.0),
                    angular_model="uniform",
                    activity_bq=None,
                    yield_per_decay=1.0,
                    surface_emission_rate_hz=12.5,
                )
            ),
            "source activity = n/a, front emission = 12.5 Hz",
        )

    def test_detector_rate_table_contains_three_columns(self) -> None:
        """Detector output should be printed as one combined table."""
        detector = Detector("T1", [0.0, 0.0, 0.0], [1.0, 1.0, 1.0], 1.0)

        class DummyResult:
            """Minimal result object exposing detectors in config order."""

            detectors = [detector]

        table = _format_detector_rate_table(
            DummyResult(),
            {
                "T1": {
                    "geometric": RateEstimate(109.426561, 0.580031, 1, 1),
                    "fired": RateEstimate(87.607777, 0.519085, 1, 1),
                }
            },
            rate_decimals=1,
        )
        self.assertIn("det", table)
        self.assertIn("geometric", table)
        self.assertIn("fired", table)
        self.assertIn("T1", table)
        self.assertIn("109.4 +/- 0.6 Hz", table)
        self.assertIn("87.6 +/- 0.5 Hz", table)

    def test_detector_rate_table_uses_configured_precision(self) -> None:
        """Detector tables should use the configured detector precision."""
        detector = Detector("T1", [0.0, 0.0, 0.0], [1.0, 1.0, 1.0], 1.0)

        class DummyResult:
            """Minimal result object exposing detectors in config order."""

            detectors = [detector]

        table = _format_detector_rate_table(
            DummyResult(),
            {
                "T1": {
                    "geometric": RateEstimate(1.123456, 0.004321, 1, 1),
                    "fired": RateEstimate(0.987654, 0.003210, 1, 1),
                }
            },
            rate_decimals=3,
        )
        self.assertIn("1.123 +/- 0.004 Hz", table)
        self.assertIn("0.988 +/- 0.003 Hz", table)

    def test_gui_mode_requires_one_gui_submode(self) -> None:
        """The CLI should reject bare `--gui` without a mode."""
        parser = build_parser()
        args = parser.parse_args(["config.yaml", "--gui"])
        with self.assertRaises(SystemExit):
            _validate_gui_arguments(parser, args)

    def test_gui_submode_requires_gui_flag(self) -> None:
        """The CLI should reject GUI submodes unless `--gui` is present."""
        parser = build_parser()
        args = parser.parse_args(["config.yaml", "--event-display"])
        with self.assertRaises(SystemExit):
            _validate_gui_arguments(parser, args)

    @mock.patch("toymc_cosmic.cli.run_simulation")
    @mock.patch("toymc_cosmic.cli.show_geometry_only")
    @mock.patch("toymc_cosmic.cli.load_config")
    def test_geometry_only_mode_skips_simulation(
        self,
        load_config_mock: mock.Mock,
        show_geometry_only_mock: mock.Mock,
        run_simulation_mock: mock.Mock,
    ) -> None:
        """Geometry-only GUI mode should not run the Monte Carlo."""
        config = object()
        load_config_mock.return_value = config

        exit_code = main(["config.yaml", "--gui", "--geometry-only"])

        self.assertEqual(exit_code, 0)
        show_geometry_only_mock.assert_called_once_with(config)
        run_simulation_mock.assert_not_called()

    @mock.patch("toymc_cosmic.cli._print_headless_summary")
    @mock.patch("toymc_cosmic.cli.show_event_display")
    @mock.patch("toymc_cosmic.cli.run_simulation")
    @mock.patch("toymc_cosmic.cli.load_config")
    def test_event_display_mode_runs_simulation_then_opens_gui(
        self,
        load_config_mock: mock.Mock,
        run_simulation_mock: mock.Mock,
        show_event_display_mock: mock.Mock,
        print_summary_mock: mock.Mock,
    ) -> None:
        """Event-display GUI mode should simulate first, then open the viewer."""
        config = object()
        simulation_result = object()
        load_config_mock.return_value = config
        run_simulation_mock.return_value = simulation_result

        exit_code = main(["config.yaml", "--gui", "--event-display"])

        self.assertEqual(exit_code, 0)
        run_simulation_mock.assert_called_once()
        print_summary_mock.assert_called_once_with(config, simulation_result)
        show_event_display_mock.assert_called_once_with(config, simulation_result)

    @mock.patch("toymc_cosmic.cli._print_headless_summary")
    @mock.patch("toymc_cosmic.cli.show_event_display")
    @mock.patch("toymc_cosmic.cli.run_simulation")
    @mock.patch("toymc_cosmic.cli.load_config")
    def test_event_display_mode_exits_cleanly_when_no_conditionals_are_configured(
        self,
        load_config_mock: mock.Mock,
        run_simulation_mock: mock.Mock,
        show_event_display_mock: mock.Mock,
        print_summary_mock: mock.Mock,
    ) -> None:
        """Event-display GUI mode should surface a clean error instead of a traceback."""
        config = object()
        simulation_result = object()
        load_config_mock.return_value = config
        run_simulation_mock.return_value = simulation_result
        show_event_display_mock.side_effect = ValueError(
            "Event display requires at least one logic.conditional entry because relevant tracks are conditional-driven."
        )

        with self.assertRaises(SystemExit):
            main(["config.yaml", "--gui", "--event-display"])

        print_summary_mock.assert_called_once_with(config, simulation_result)

    @mock.patch("toymc_cosmic.cli._print_headless_summary")
    @mock.patch("toymc_cosmic.cli.show_event_display")
    @mock.patch("toymc_cosmic.cli.run_simulation")
    @mock.patch("toymc_cosmic.cli.load_config")
    def test_event_display_mode_exits_cleanly_when_no_relevant_tracks_exist(
        self,
        load_config_mock: mock.Mock,
        run_simulation_mock: mock.Mock,
        show_event_display_mock: mock.Mock,
        print_summary_mock: mock.Mock,
    ) -> None:
        """Event-display GUI mode should stop cleanly when no relevant tracks exist."""
        config = object()
        simulation_result = object()
        load_config_mock.return_value = config
        run_simulation_mock.return_value = simulation_result
        show_event_display_mock.side_effect = ValueError(
            "No geometrically relevant tracks were found for the configured conditionals."
        )

        with self.assertRaises(SystemExit):
            main(["config.yaml", "--gui", "--event-display"])

        print_summary_mock.assert_called_once_with(config, simulation_result)
