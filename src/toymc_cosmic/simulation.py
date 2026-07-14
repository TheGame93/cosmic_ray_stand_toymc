"""Top-level simulation orchestration for the engine."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

import numpy as np

from .config import Config
from .geometry import Detector, intersect
from .response import apply_response
from .source import build_source_model
from .tracks import Tracks


ProgressCallback = Callable[[int, int, float], None]
PROGRESS_UPDATE_INTERVAL = 1000_000


@dataclass
class SimulationResult:
    """Container for the data produced by one Monte Carlo run.

    Attributes:
        tracks: Generated track origins and directions.
        crossed: Per-detector geometric crossing arrays keyed by detector name.
        fired: Per-detector fired-response arrays keyed by detector name.
        detectors: Detector definitions used in the run.
        total_rate_hz: Total physical event rate the source's sampling represents, in Hz.
        seed: Resolved random seed used for the run.
        n_events: Number of generated events.
    """

    tracks: Tracks
    crossed: dict[str, np.ndarray]
    fired: dict[str, np.ndarray]
    detectors: list[Detector]
    total_rate_hz: float
    seed: int
    n_events: int


def run_simulation(
    config: Config,
    progress_callback: ProgressCallback | None = None,
) -> SimulationResult:
    """Run the full headless Monte Carlo pipeline; returns the completed SimulationResult.

    Args:
        config: Validated engine configuration.
        progress_callback: Optional callable notified after each completed
            simulation chunk. The callback receives the processed event count,
            the total event count, and the completion fraction in percent.
    """
    seed = config.seed if config.seed is not None else int(time.time() * 1000)
    rng = np.random.default_rng(seed)

    source_model = build_source_model(config.source_model)
    efficiencies = np.array([detector.efficiency for detector in config.detectors], dtype=float)

    track_origin_chunks: list[np.ndarray] = []
    track_direction_chunks: list[np.ndarray] = []
    crossed_chunks: list[np.ndarray] = []
    fired_chunks: list[np.ndarray] = []

    total_events = config.monte_carlo.n_events
    processed_events = 0

    for chunk_start in range(0, total_events, PROGRESS_UPDATE_INTERVAL):
        remaining_events = total_events - chunk_start
        chunk_size = min(PROGRESS_UPDATE_INTERVAL, remaining_events)

        chunk_tracks = source_model.generate(chunk_size, config.detectors, rng)
        chunk_crossed = intersect(chunk_tracks.origins, chunk_tracks.directions, config.detectors)
        chunk_fired = apply_response(chunk_crossed, efficiencies, rng)

        track_origin_chunks.append(chunk_tracks.origins)
        track_direction_chunks.append(chunk_tracks.directions)
        crossed_chunks.append(chunk_crossed)
        fired_chunks.append(chunk_fired)

        processed_events += chunk_size
        if progress_callback is not None:
            percent_complete = 100.0 * processed_events / total_events
            progress_callback(processed_events, total_events, percent_complete)

    tracks = Tracks(
        origins=np.concatenate(track_origin_chunks, axis=0),
        directions=np.concatenate(track_direction_chunks, axis=0),
    )
    crossed_matrix = np.concatenate(crossed_chunks, axis=0)
    fired_matrix = np.concatenate(fired_chunks, axis=0)

    detector_names = [detector.name for detector in config.detectors]

    # We keep the results keyed by detector name because that is the same naming
    # scheme used by the logic expressions and future GUI consumers.
    crossed = {
        detector_name: crossed_matrix[:, index].copy()
        for index, detector_name in enumerate(detector_names)
    }
    fired = {
        detector_name: fired_matrix[:, index].copy()
        for index, detector_name in enumerate(detector_names)
    }

    return SimulationResult(
        tracks=tracks,
        crossed=crossed,
        fired=fired,
        detectors=config.detectors,
        total_rate_hz=source_model.total_rate_hz(config.detectors),
        seed=seed,
        n_events=config.monte_carlo.n_events,
    )
