"""Tests for geometry-systematics orchestration and summaries."""

from __future__ import annotations

import math
import pathlib
import tempfile
import textwrap
import unittest

from toymc_cosmic.config import load_config
from toymc_cosmic.geometry_systematics import resolve_geometry_event_split, run_geometry_systematics
from toymc_cosmic.rates import conditional_probability, detector_rates, logic_rates


class GeometrySystematicsTests(unittest.TestCase):
    """Check event splitting, determinism, and estimate attachment for geometry systematics."""

    def test_event_split_assigns_remainder_to_nominal(self) -> None:
        """Event splitting should keep the remainder on the nominal run."""
        config = load_config(self._write_config(n_events=11, n_replicas=2))
        split = resolve_geometry_event_split(config)

        self.assertEqual(split.total_events, 11)
        self.assertEqual(split.nominal_events, 5)
        self.assertEqual(split.replica_events, 3)
        self.assertEqual(split.n_replicas, 2)

    def test_geometry_systematics_progress_reports_global_cumulative_events(self) -> None:
        """Replica orchestration should report cumulative progress against the configured total."""
        config = load_config(self._write_config(n_events=10, n_replicas=2))
        progress_calls: list[tuple[int, int, float]] = []

        def record_progress(processed: int, total: int, percent: float) -> None:
            """Store progress updates for later assertions."""
            progress_calls.append((processed, total, percent))

        run_geometry_systematics(config, progress_callback=record_progress)

        self.assertEqual(progress_calls, [(4, 10, 40.0), (7, 10, 70.0), (10, 10, 100.0)])

    def test_seeded_geometry_execution_is_deterministic_even_when_geometry_seed_is_derived(self) -> None:
        """Derived geometry seeds should still reproduce identical nominal and replica summaries."""
        config = load_config(self._write_config(n_events=90, n_replicas=2, geometry_seed=None))

        first = run_geometry_systematics(config)
        second = run_geometry_systematics(config)

        self.assertEqual(first.nominal_result.seed, second.nominal_result.seed)
        self.assertEqual(first.geometry_seed, second.geometry_seed)
        self.assertEqual(first.detector_rate_summaries, second.detector_rate_summaries)
        self.assertEqual(first.logic_rate_summaries, second.logic_rate_summaries)
        self.assertEqual(first.conditional_probability_summaries, second.conditional_probability_summaries)
        self.assertEqual(first.nominal_result.crossed["FIX"].tolist(), second.nominal_result.crossed["FIX"].tolist())
        self.assertEqual(first.nominal_result.crossed["VAR"].tolist(), second.nominal_result.crossed["VAR"].tolist())

    def test_affected_and_unaffected_observables_receive_the_expected_uncertainty_fields(self) -> None:
        """Only geometry-dependent observables should receive systematic summaries."""
        config = load_config(self._write_config(n_events=180, n_replicas=2, geometry_seed=456))
        result = run_geometry_systematics(config)

        detector_rate_map = detector_rates(result.nominal_result, result.detector_rate_summaries)
        fixed_rate = detector_rate_map["FIX"]["geometric"]
        variable_rate = detector_rate_map["VAR"]["geometric"]

        self.assertIsNone(fixed_rate.syst_error)
        self.assertIsNotNone(variable_rate.syst_error)
        assert variable_rate.stat_error is not None
        assert variable_rate.syst_error is not None
        self.assertAlmostEqual(
            variable_rate.error ** 2,
            variable_rate.stat_error ** 2 + variable_rate.syst_error ** 2,
        )

        unaffected_logic = logic_rates(
            config.logic_expressions[0],
            result.nominal_result,
            result.logic_rate_summaries[0],
        )["geometric"]
        affected_logic = logic_rates(
            config.logic_expressions[1],
            result.nominal_result,
            result.logic_rate_summaries[1],
        )["geometric"]
        self.assertIsNone(unaffected_logic.syst_error)
        self.assertIsNotNone(affected_logic.syst_error)

        affected_probability = conditional_probability(
            config.conditionals[0].numerator,
            config.conditionals[0].given,
            result.nominal_result,
            mode="geometric",
            systematic_summary=result.conditional_probability_summaries[0]["geometric"],
        )
        self.assertIsNotNone(affected_probability.syst_error)
        assert affected_probability.stat_error is not None
        assert affected_probability.syst_error is not None
        self.assertAlmostEqual(
            affected_probability.error ** 2,
            affected_probability.stat_error ** 2 + affected_probability.syst_error ** 2,
        )

    def test_sparse_replica_counts_emit_warnings_only_below_threshold(self) -> None:
        """Replica warnings should appear only when the relevant replica counts are sparse."""
        sparse_config = load_config(self._write_config(n_events=11, n_replicas=2, geometry_seed=456))
        sparse_result = run_geometry_systematics(sparse_config)
        sparse_detector_rate = detector_rates(sparse_result.nominal_result, sparse_result.detector_rate_summaries)["VAR"][
            "geometric"
        ]
        assert sparse_detector_rate.quality_warning is not None
        self.assertTrue(sparse_detector_rate.quality_warning.startswith("replica_min_n_pass="))
        self.assertLess(int(sparse_detector_rate.quality_warning.split("=")[1]), 20)

        dense_config = load_config(self._write_config(n_events=210, n_replicas=2, geometry_seed=456))
        dense_result = run_geometry_systematics(dense_config)
        dense_detector_rate = detector_rates(dense_result.nominal_result, dense_result.detector_rate_summaries)["VAR"][
            "geometric"
        ]
        self.assertIsNone(dense_detector_rate.quality_warning)

        sparse_probability = conditional_probability(
            sparse_config.conditionals[0].numerator,
            sparse_config.conditionals[0].given,
            sparse_result.nominal_result,
            mode="geometric",
            systematic_summary=sparse_result.conditional_probability_summaries[0]["geometric"],
        )
        self.assertTrue(
            sparse_probability.quality_warning is None
            or sparse_probability.quality_warning.startswith("replica_min_n_cond=")
        )
        self.assertFalse(math.isnan(sparse_probability.error))

    def _write_config(self, *, n_events: int, n_replicas: int, geometry_seed: int | None = 456) -> pathlib.Path:
        """Write one beam config that mixes affected and unaffected observables; returns path."""
        geometry_seed_block = "" if geometry_seed is None else f"            seed: {geometry_seed}\n"
        config_text = f"""
        seed: 123
        source_model:
          type: beam
          profile: uniform
          center: [0.0, 0.0]
          size: [2.0]
          flux_hz_per_cm2: 1.0
        monte_carlo:
          n_events: {n_events}
        systematics:
          geometry:
            n_replicas: {n_replicas}
{geometry_seed_block}        detectors:
          - name: FIX
            center: [0.0, 0.0, 0.5]
            size: [2.2, 2.2, 1.0]
            efficiency: 1.0
          - name: VAR
            center:
              value: [0.0, 0.0, 1.5]
              sigma: [0.35, 0.0, 0.0]
            size: [1.0, 2.2, 1.0]
            efficiency: 1.0
        logic:
          expressions:
            - "FIX"
            - "FIX and VAR"
          conditional:
            - name: "P(VAR|FIX)"
              numerator: "VAR"
              given: "FIX"
        """

        temp_dir = tempfile.mkdtemp()
        path = pathlib.Path(temp_dir) / "geometry.yaml"
        path.write_text(textwrap.dedent(config_text).strip() + "\n")
        return path
