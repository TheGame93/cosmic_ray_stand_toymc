"""Compute rate and probability estimates from simulation outputs; returns estimates."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING

import numpy as np

from .logic import evaluate

if TYPE_CHECKING:
    from .simulation import SimulationResult


@dataclass(frozen=True)
class SystematicEstimateSummary:
    """Store one geometry-systematics summary for an observable."""

    syst_error: float
    quality_warning: str | None = None


@dataclass(frozen=True)
class RateEstimate:
    """Store one rate estimate with statistical and optional systematic uncertainty."""

    value: float
    error: float
    n_pass: int
    n_total: int
    stat_error: float | None = None
    syst_error: float | None = None
    quality_warning: str | None = None

    def __post_init__(self) -> None:
        """Normalize derived uncertainty fields for backward compatibility; returns None."""
        if self.stat_error is None:
            object.__setattr__(self, "stat_error", self.error)


@dataclass(frozen=True)
class ProbabilityEstimate:
    """Store one conditional probability estimate with optional systematic uncertainty."""

    value: float
    error: float
    n_joint: int
    n_cond: int
    stat_error: float | None = None
    syst_error: float | None = None
    quality_warning: str | None = None

    def __post_init__(self) -> None:
        """Normalize derived uncertainty fields for backward compatibility; returns None."""
        if self.stat_error is None:
            object.__setattr__(self, "stat_error", self.error)


def binomial_rate(n_pass: int, n_total: int, total_rate_hz: float) -> RateEstimate:
    """Convert one pass count into a rate estimate; returns RateEstimate."""
    if n_total <= 0:
        raise ValueError("n_total must be positive.")

    pass_fraction = n_pass / n_total
    variance = pass_fraction * (1.0 - pass_fraction) / n_total

    value = total_rate_hz * pass_fraction
    error = total_rate_hz * math.sqrt(max(variance, 0.0))
    return RateEstimate(value=value, error=error, n_pass=n_pass, n_total=n_total)


def binomial_probability(n_joint: int, n_cond: int) -> ProbabilityEstimate:
    """Convert one joint and conditional count into a probability estimate; returns ProbabilityEstimate."""
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


def detector_rates(
    simulation_result: SimulationResult,
    systematic_summaries: dict[str, dict[str, SystematicEstimateSummary]] | None = None,
) -> dict[str, dict[str, RateEstimate]]:
    """Return geometric and fired rates for every detector; returns nested dict."""
    results: dict[str, dict[str, RateEstimate]] = {}

    for detector in simulation_result.detectors:
        name = detector.name
        geometric_count = int(np.count_nonzero(simulation_result.crossed[name]))
        fired_count = int(np.count_nonzero(simulation_result.fired[name]))

        geometric_estimate = binomial_rate(
            geometric_count,
            simulation_result.n_events,
            simulation_result.total_rate_hz,
        )
        fired_estimate = binomial_rate(
            fired_count,
            simulation_result.n_events,
            simulation_result.total_rate_hz,
        )
        detector_summaries = systematic_summaries.get(name) if systematic_summaries is not None else None

        results[name] = {
            "geometric": _apply_rate_systematics(
                geometric_estimate,
                detector_summaries.get("geometric") if detector_summaries is not None else None,
            ),
            "fired": _apply_rate_systematics(
                fired_estimate,
                detector_summaries.get("fired") if detector_summaries is not None else None,
            ),
        }

    return results


def logic_rates(
    expression: str,
    simulation_result: SimulationResult,
    systematic_summaries: dict[str, SystematicEstimateSummary] | None = None,
) -> dict[str, RateEstimate]:
    """Return geometric and fired rates for one logic expression; returns dict."""
    geometric_values = evaluate(expression, simulation_result.crossed)
    fired_values = evaluate(expression, simulation_result.fired)

    geometric_count = int(np.count_nonzero(geometric_values))
    fired_count = int(np.count_nonzero(fired_values))

    geometric_estimate = binomial_rate(
        geometric_count,
        simulation_result.n_events,
        simulation_result.total_rate_hz,
    )
    fired_estimate = binomial_rate(
        fired_count,
        simulation_result.n_events,
        simulation_result.total_rate_hz,
    )

    return {
        "geometric": _apply_rate_systematics(
            geometric_estimate,
            systematic_summaries.get("geometric") if systematic_summaries is not None else None,
        ),
        "fired": _apply_rate_systematics(
            fired_estimate,
            systematic_summaries.get("fired") if systematic_summaries is not None else None,
        ),
    }


def conditional_probability(
    numerator_expression: str,
    given_expression: str,
    simulation_result: SimulationResult,
    mode: str = "fired",
    systematic_summary: SystematicEstimateSummary | None = None,
) -> ProbabilityEstimate:
    """Return `P(numerator | given)` in one mode; returns ProbabilityEstimate."""
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
    return _apply_probability_systematics(
        binomial_probability(n_joint, n_cond),
        systematic_summary,
    )


def _apply_rate_systematics(
    estimate: RateEstimate,
    summary: SystematicEstimateSummary | None,
) -> RateEstimate:
    """Attach optional systematic uncertainty to one rate estimate; returns RateEstimate."""
    if summary is None:
        return estimate

    total_error = math.sqrt((estimate.stat_error or 0.0) ** 2 + summary.syst_error ** 2)
    return RateEstimate(
        value=estimate.value,
        error=total_error,
        n_pass=estimate.n_pass,
        n_total=estimate.n_total,
        stat_error=estimate.stat_error,
        syst_error=summary.syst_error,
        quality_warning=summary.quality_warning,
    )


def _apply_probability_systematics(
    estimate: ProbabilityEstimate,
    summary: SystematicEstimateSummary | None,
) -> ProbabilityEstimate:
    """Attach optional systematic uncertainty to one probability estimate; returns ProbabilityEstimate."""
    if summary is None:
        return estimate

    if estimate.stat_error is None or math.isnan(estimate.stat_error):
        total_error = math.nan
    else:
        total_error = math.sqrt((estimate.stat_error) ** 2 + summary.syst_error ** 2)

    return ProbabilityEstimate(
        value=estimate.value,
        error=total_error,
        n_joint=estimate.n_joint,
        n_cond=estimate.n_cond,
        stat_error=estimate.stat_error,
        syst_error=summary.syst_error,
        quality_warning=summary.quality_warning,
    )
