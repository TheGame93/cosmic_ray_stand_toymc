"""Terminal entry point for the headless engine."""

from __future__ import annotations

import argparse
import math
import sys
from typing import TextIO
from typing import Sequence

from .config import load_config
from .rates import conditional_probability, detector_rates, logic_rates
from .simulation import run_simulation


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Run the toy cosmic-ray Monte Carlo engine.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the headless CLI and print the requested observables."""
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    simulation_result = run_simulation(config, progress_callback=_render_progress)

    print(f"Seed: {simulation_result.seed}")
    print(
        "Generated events: "
        f"{simulation_result.n_events}  (A_gen = {simulation_result.area_gen:.3f} cm^2)"
    )
    print()

    detector_rate_map = detector_rates(simulation_result)
    print("Geometric crossing rates:")
    for detector in simulation_result.detectors:
        rate = detector_rate_map[detector.name]["geometric"]
        print(f"  {detector.name}: {rate.value:.6f} +/- {rate.error:.6f} Hz")
    print()

    print("Fired rates:")
    for detector in simulation_result.detectors:
        rate = detector_rate_map[detector.name]["fired"]
        print(f"  {detector.name}: {rate.value:.6f} +/- {rate.error:.6f} Hz")
    print()

    if config.logic_expressions:
        print("Logic expressions:")
        for expression in config.logic_expressions:
            rate_map = logic_rates(expression, simulation_result)
            geometric_rate = rate_map["geometric"]
            fired_rate = rate_map["fired"]
            print(
                f"  {expression}\n"
                f"    geometric: {geometric_rate.value:.6f} +/- {geometric_rate.error:.6f} Hz\n"
                f"    fired:     {fired_rate.value:.6f} +/- {fired_rate.error:.6f} Hz"
            )
        print()

    if config.conditionals:
        print("Conditional probabilities:")
        for conditional in config.conditionals:
            estimate = conditional_probability(
                conditional.numerator,
                conditional.given,
                simulation_result,
                mode=conditional.mode,
            )
            if math.isnan(estimate.value):
                value_text = "nan"
                error_text = "nan"
            else:
                value_text = f"{estimate.value:.6f}"
                error_text = f"{estimate.error:.6f}"
            print(
                f"  {conditional.name} = {value_text} +/- {error_text} "
                f"(n_cond={estimate.n_cond})"
            )

    return 0


def _render_progress(
    processed_events: int,
    total_events: int,
    percent_complete: float,
    stream: TextIO = sys.stdout,
) -> None:
    """Render a single-line progress indicator for the CLI.

    The simulation may run for a long time at large event counts. This helper
    keeps the user informed without printing a full history of progress lines.
    """

    progress_text = (
        f"\rProgress: {processed_events} / {total_events} ({percent_complete:.2f}%)"
    )
    stream.write(progress_text)

    # Flush immediately so the terminal shows the updated counter while the
    # simulation is still running.
    if processed_events >= total_events:
        stream.write("\n")
    stream.flush()
