"""Integration tests for the full engine pipeline."""

from __future__ import annotations

import math
import pathlib
import tempfile
import textwrap
import unittest

import numpy as np

from toymc_cosmic.config import load_config
from toymc_cosmic.geometry import generation_region
from toymc_cosmic.logic import evaluate
from toymc_cosmic.simulation import PROGRESS_UPDATE_INTERVAL, run_simulation


class SimulationTests(unittest.TestCase):
    """Check end-to-end simulation sanity conditions."""

    def test_total_rate_hz_matches_flux_times_generation_area(self) -> None:
        """SimulationResult.total_rate_hz must match the cosmic source's flux * area_gen."""
        config = load_config(self._write_config())
        result = run_simulation(config)

        _, _, _, _, area_gen = generation_region(config.detectors, math.radians(80.0))
        self.assertAlmostEqual(result.total_rate_hz, 0.01 * area_gen)

    def test_fired_events_are_subset_of_crossed_events(self) -> None:
        """Detector response must never create fired events without a crossing."""
        config = load_config(self._write_config())
        result = run_simulation(config)

        for detector in result.detectors:
            crossed = result.crossed[detector.name]
            fired = result.fired[detector.name]
            self.assertTrue(np.all(fired <= crossed))

        rate_a = evaluate("T1 and T2", result.crossed)
        rate_b = evaluate("T1", result.crossed)
        self.assertLessEqual(np.count_nonzero(rate_a), np.count_nonzero(rate_b))

    def test_progress_callback_reports_each_chunk_and_final_partial_chunk(self) -> None:
        """The simulation should report cumulative progress after every chunk."""
        total_events = (2 * PROGRESS_UPDATE_INTERVAL) + 5000
        config = load_config(self._write_config(n_events=total_events))
        progress_calls: list[tuple[int, int, float]] = []

        def record_progress(processed: int, total: int, percent: float) -> None:
            """Store the callback data so the test can inspect it."""
            progress_calls.append((processed, total, percent))

        run_simulation(config, progress_callback=record_progress)

        self.assertEqual(len(progress_calls), 3)
        self.assertEqual(progress_calls[0][0], PROGRESS_UPDATE_INTERVAL)
        self.assertEqual(progress_calls[1][0], 2 * PROGRESS_UPDATE_INTERVAL)
        self.assertEqual(progress_calls[2][0], total_events)
        self.assertTrue(all(total == total_events for _, total, _ in progress_calls))
        self.assertTrue(all(a[0] < b[0] for a, b in zip(progress_calls, progress_calls[1:])))
        self.assertAlmostEqual(progress_calls[-1][2], 100.0)

    def test_small_run_still_reports_one_final_progress_update(self) -> None:
        """A run smaller than one chunk should still emit a 100% update."""
        config = load_config(self._write_config(n_events=2000))
        progress_calls: list[tuple[int, int, float]] = []

        def record_progress(processed: int, total: int, percent: float) -> None:
            """Store the callback data so the test can inspect it."""
            progress_calls.append((processed, total, percent))

        run_simulation(config, progress_callback=record_progress)

        self.assertEqual(progress_calls, [(2000, 2000, 100.0)])

    def _write_config(self, n_events: int = 2000) -> pathlib.Path:
        """Write a small but non-trivial simulation config file."""
        config_text = f"""
        seed: 11
        source_model:
          type: cosmic
          model: cos2
          theta_max_deg: 80.0
          flux_hz_per_cm2: 0.01
        monte_carlo:
          n_events: {n_events}
        detectors:
          - name: T1
            center: [0, 0, 10]
            size: [10, 10, 1]
            efficiency: 0.9
          - name: T2
            center: [0, 0, 0]
            size: [10, 10, 1]
            efficiency: 0.8
        logic:
          expressions:
            - "T1 and T2"
        """

        temp_dir = tempfile.mkdtemp()
        path = pathlib.Path(temp_dir) / "sim.yaml"
        path.write_text(textwrap.dedent(config_text).strip() + "\n")
        return path
