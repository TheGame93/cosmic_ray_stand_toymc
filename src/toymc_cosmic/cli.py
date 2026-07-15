"""Terminal entry point for the headless engine."""

from __future__ import annotations

import argparse
import math
import sys
from typing import TextIO
from typing import Sequence

from .config import BeamSourceConfig, CosmicSourceConfig, ObjectSourceConfig, load_config
from .gui import show_event_display, show_geometry_only
from .rates import conditional_probability, detector_rates, logic_rates
from .simulation import run_simulation


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Run the toy cosmic-ray Monte Carlo engine.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Enable GUI mode.",
    )
    gui_mode_group = parser.add_mutually_exclusive_group()
    gui_mode_group.add_argument(
        "--geometry-only",
        action="store_true",
        help="Show detector geometry only without running the Monte Carlo.",
    )
    gui_mode_group.add_argument(
        "--event-display",
        action="store_true",
        help="Run the Monte Carlo and open the step-by-step event display.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI either in headless or GUI mode; returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_gui_arguments(parser, args)

    config = load_config(args.config)

    if args.gui and args.geometry_only:
        show_geometry_only(config)
        return 0

    simulation_result = run_simulation(config, progress_callback=_render_progress)
    _print_headless_summary(config, simulation_result)

    if args.gui and args.event_display:
        try:
            show_event_display(config, simulation_result)
        except ValueError as exc:
            parser.error(str(exc))

    return 0


def _validate_gui_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Reject incompatible GUI argument combinations."""
    gui_mode_requested = args.geometry_only or args.event_display
    if gui_mode_requested and not args.gui:
        parser.error("--geometry-only and --event-display require --gui.")
    if args.gui and not gui_mode_requested:
        parser.error("--gui requires either --geometry-only or --event-display.")


def _print_headless_summary(config, simulation_result) -> None:
    """Print the standard terminal summary for one simulation result."""
    print(f"Seed: {simulation_result.seed}")
    print(f"Generated events: {simulation_result.n_events}  ({_format_source_header(config.source_model)})")
    print()

    detector_rate_map = detector_rates(simulation_result)
    print("Detector rates:")
    print(
        _format_detector_rate_table(
            simulation_result,
            detector_rate_map,
            rate_decimals=config.output.detector_rate_decimals,
        )
    )
    print()

    if config.logic_expressions:
        print("Logic expressions:")
        for expression in config.logic_expressions:
            rate_map = logic_rates(expression, simulation_result)
            geometric_rate = rate_map["geometric"]
            fired_rate = rate_map["fired"]
            print(
                f"  {expression}\n"
                f"    geometric: {_format_rate_hz(geometric_rate, config.output.logic_rate_decimals)}\n"
                f"    fired:     {_format_rate_hz(fired_rate, config.output.logic_rate_decimals)}"
            )
        print()

    if config.conditionals:
        print("Conditional probabilities:")
        for conditional in config.conditionals:
            fired_estimate = conditional_probability(
                conditional.numerator,
                conditional.given,
                simulation_result,
                mode="fired",
            )
            geometric_estimate = conditional_probability(
                conditional.numerator,
                conditional.given,
                simulation_result,
                mode="geometric",
            )
            print(f"  {conditional.name}")
            print(f"    fired:     {_format_probability(fired_estimate)}")
            print(f"    geometric: {_format_probability(geometric_estimate)}")


def _format_detector_rate_table(
    simulation_result,
    detector_rate_map: dict[str, dict],
    rate_decimals: int,
) -> str:
    """Return a detector rate table with aligned geometric and fired columns."""
    detector_names = [detector.name for detector in simulation_result.detectors]
    geometric_texts = [
        _format_rate_hz(detector_rate_map[name]["geometric"], rate_decimals)
        for name in detector_names
    ]
    fired_texts = [
        _format_rate_hz(detector_rate_map[name]["fired"], rate_decimals)
        for name in detector_names
    ]

    det_width = max(len("det"), *(len(name) for name in detector_names))
    geometric_width = max(len("geometric"), *(len(text) for text in geometric_texts))
    fired_width = max(len("fired"), *(len(text) for text in fired_texts))

    lines = [
        f"  {'det':<{det_width}}  {'geometric':<{geometric_width}}  {'fired':<{fired_width}}"
    ]
    for name, geometric_text, fired_text in zip(detector_names, geometric_texts, fired_texts):
        lines.append(
            f"  {name:<{det_width}}  {geometric_text:<{geometric_width}}  {fired_text:<{fired_width}}"
        )
    return "\n".join(lines)


def _format_rate_hz(estimate, decimals: int) -> str:
    """Format a rate estimate with a configurable number of decimal digits."""
    format_spec = f".{decimals}f"
    return f"{format(estimate.value, format_spec)} +/- {format(estimate.error, format_spec)} Hz"


def _format_probability(estimate) -> str:
    """Format a conditional probability with per-thousand precision."""
    if math.isnan(estimate.value):
        value_text = "nan"
        error_text = "nan"
    else:
        value_text = f"{estimate.value:.3f}"
        error_text = f"{estimate.error:.3f}"
    return f"{value_text} +/- {error_text} (n_cond={estimate.n_cond})"


def _format_source_header(source_config) -> str:
    """Format the source-specific header summary; returns text."""
    if isinstance(source_config, CosmicSourceConfig):
        return f"cosmic flux = {source_config.flux_hz_per_cm2:.6g} Hz/cm2"
    if isinstance(source_config, BeamSourceConfig):
        return f"beam flux = {source_config.flux_hz_per_cm2:.6g} Hz/cm2"
    if isinstance(source_config, ObjectSourceConfig):
        activity_text = "n/a" if source_config.activity_bq is None else f"{source_config.activity_bq:.6g} Bq"
        return (
            f"source activity = {activity_text}, "
            f"front emission = {source_config.front_emission_rate_hz():.6g} Hz"
        )
    raise ValueError(f"Unsupported source config type: {type(source_config).__name__}")


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
