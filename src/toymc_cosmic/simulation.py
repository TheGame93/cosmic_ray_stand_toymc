"""Top-level simulation orchestration for the engine."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

import numpy as np

from .angular import Cos2AngularModel
from .config import Config
from .geometry import Detector, generation_region, intersect
from .response import apply_response
from .tracks import Tracks, generate_tracks


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
        area_gen: Generation area in cm^2.
        flux: Total downward flux over the simulated angular cone.
        theta_max: Maximum zenith angle in radians.
        seed: Resolved random seed used for the run.
        n_events: Number of generated events.
    """

    tracks: Tracks
    crossed: dict[str, np.ndarray]
    fired: dict[str, np.ndarray]
    detectors: list[Detector]
    area_gen: float
    flux: float
    theta_max: float
    seed: int
    n_events: int


def run_simulation(
    config: Config,
    progress_callback: ProgressCallback | None = None,
) -> SimulationResult:
    """Run the full headless Monte Carlo pipeline.

    Args:
        config: Validated engine configuration.
        progress_callback: Optional callable notified after each completed
            simulation chunk. The callback receives the processed event count,
            the total event count, and the completion fraction in percent.
    """
    seed = config.seed if config.seed is not None else int(time.time() * 1000)
    rng = np.random.default_rng(seed)

    angular_model = _build_angular_model(config)
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

        chunk_tracks = generate_tracks(
            count=chunk_size,
            detectors=config.detectors,
            theta_max=config.theta_max,
            angular_model=angular_model,
            rng=rng,
        )
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

    _, _, _, _, area_gen = generation_region(config.detectors, config.theta_max)

    return SimulationResult(
        tracks=tracks,
        crossed=crossed,
        fired=fired,
        detectors=config.detectors,
        area_gen=area_gen,
        flux=config.flux_hz_per_cm2,
        theta_max=config.theta_max,
        seed=seed,
        n_events=config.monte_carlo.n_events,
    )


def _build_angular_model(config: Config) -> Cos2AngularModel:
    """Build the configured angular model.

    The engine currently supports only the default cos^2 model, but keeping this
    helper separate makes the future extension path easier to follow.
    """

    if config.angular_model.type == "cos2":
        return Cos2AngularModel()
    raise ValueError(f"Unsupported angular model type: {config.angular_model.type}")
