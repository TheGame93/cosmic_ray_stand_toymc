"""Rate and probability estimators for Monte Carlo observables."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING

import numpy as np

from .logic import evaluate

if TYPE_CHECKING:
    from .simulation import SimulationResult


@dataclass(frozen=True)
class RateEstimate:
    """Rate estimate with a simple binomial statistical uncertainty."""

    value: float
    error: float
    n_pass: int
    n_total: int


@dataclass(frozen=True)
class ProbabilityEstimate:
    """Conditional probability estimate with binomial uncertainty."""

    value: float
    error: float
    n_joint: int
    n_cond: int


def binomial_rate(n_pass: int, n_total: int, flux: float, area: float) -> RateEstimate:
    """Convert a passing-event count into a rate estimate."""
    if n_total <= 0:
        raise ValueError("n_total must be positive.")

    pass_fraction = n_pass / n_total
    variance = pass_fraction * (1.0 - pass_fraction) / n_total

    scale = flux * area
    value = scale * pass_fraction
    error = scale * math.sqrt(max(variance, 0.0))
    return RateEstimate(value=value, error=error, n_pass=n_pass, n_total=n_total)


def binomial_probability(n_joint: int, n_cond: int) -> ProbabilityEstimate:
    """Convert joint and conditional counts into a probability estimate."""
    if n_cond < 0:
        raise ValueError("n_cond must be non-negative.")
    if n_joint < 0:
        raise ValueError("n_joint must be non-negative.")
    if n_joint > n_cond:
        raise ValueError("n_joint cannot exceed n_cond.")

    if n_cond == 0:
        return ProbabilityEstimate(value=math.nan, error=math.nan, n_joint=n_joint, n_cond=n_cond)

    probability = n_joint / n_cond
    variance = probability * (1.0 - probability) / n_cond
    error = math.sqrt(max(variance, 0.0))
    return ProbabilityEstimate(value=probability, error=error, n_joint=n_joint, n_cond=n_cond)


def detector_rates(simulation_result: SimulationResult) -> dict[str, dict[str, RateEstimate]]:
    """Return geometric and fired rates for every detector."""
    results: dict[str, dict[str, RateEstimate]] = {}

    for detector in simulation_result.detectors:
        name = detector.name
        geometric_count = int(np.count_nonzero(simulation_result.crossed[name]))
        fired_count = int(np.count_nonzero(simulation_result.fired[name]))

        results[name] = {
            "geometric": binomial_rate(
                geometric_count,
                simulation_result.n_events,
                simulation_result.flux,
                simulation_result.area_gen,
            ),
            "fired": binomial_rate(
                fired_count,
                simulation_result.n_events,
                simulation_result.flux,
                simulation_result.area_gen,
            ),
        }

    return results


def logic_rates(expression: str, simulation_result: SimulationResult) -> dict[str, RateEstimate]:
    """Return geometric and fired rates for a detector logic expression."""
    geometric_values = evaluate(expression, simulation_result.crossed)
    fired_values = evaluate(expression, simulation_result.fired)

    geometric_count = int(np.count_nonzero(geometric_values))
    fired_count = int(np.count_nonzero(fired_values))

    return {
        "geometric": binomial_rate(
            geometric_count,
            simulation_result.n_events,
            simulation_result.flux,
            simulation_result.area_gen,
        ),
        "fired": binomial_rate(
            fired_count,
            simulation_result.n_events,
            simulation_result.flux,
            simulation_result.area_gen,
        ),
    }


def conditional_probability(
    numerator_expression: str,
    given_expression: str,
    simulation_result: SimulationResult,
    mode: str = "fired",
) -> ProbabilityEstimate:
    """Return `P(numerator | given)` evaluated in one detector-response mode."""
    if mode == "fired":
        context = simulation_result.fired
    elif mode == "geometric":
        context = simulation_result.crossed
    else:
        raise ValueError("mode must be either 'fired' or 'geometric'.")

    numerator_values = evaluate(numerator_expression, context)
    given_values = evaluate(given_expression, context)

    joint_values = numerator_values & given_values
    n_joint = int(np.count_nonzero(joint_values))
    n_cond = int(np.count_nonzero(given_values))
    return binomial_probability(n_joint, n_cond)
