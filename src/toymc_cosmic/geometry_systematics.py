"""Run nominal plus geometry-replica simulations; returns systematic summaries."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math

import numpy as np

from .config import (
    Config,
    DetectorGeometryUncertaintyConfig,
    GeometrySystematicsConfig,
    MonteCarloConfig,
)
from .geometry import Detector
from .logic import extract_names
from .rates import (
    SystematicEstimateSummary,
    conditional_probability,
    detector_rates,
    logic_rates,
)
from .simulation import ProgressCallback, SimulationResult, resolve_seed, run_simulation

_SPARSE_REPLICA_WARNING_THRESHOLD = 20
_GEOMETRY_SEED_OFFSET = 0x9E3779B97F4A7C15
_UINT63_MASK = (1 << 63) - 1


@dataclass(frozen=True)
class GeometryEventSplit:
    """Store the nominal and replica event-budget layout."""

    total_events: int
    nominal_events: int
    replica_events: int
    n_replicas: int


@dataclass(frozen=True)
class GeometrySystematicsResult:
    """Store nominal results plus geometry-systematics summaries for the CLI."""

    nominal_result: SimulationResult
    geometry_seed: int
    event_split: GeometryEventSplit
    detector_rate_summaries: dict[str, dict[str, SystematicEstimateSummary]]
    logic_rate_summaries: list[dict[str, SystematicEstimateSummary] | None]
    conditional_probability_summaries: list[dict[str, SystematicEstimateSummary] | None]


@dataclass
class _ObservableAccumulator:
    """Accumulate replica deviations for one observable and mode."""

    nominal_value: float
    warning_key: str
    sum_squared_delta: float = 0.0
    finite_replica_count: int = 0
    min_relevant_count: int | None = None

    def add_replica(self, replica_value: float, relevant_count: int) -> None:
        """Accumulate one replica estimate and count; returns None."""
        if self.min_relevant_count is None:
            self.min_relevant_count = relevant_count
        else:
            self.min_relevant_count = min(self.min_relevant_count, relevant_count)

        if not math.isfinite(self.nominal_value) or not math.isfinite(replica_value):
            return

        delta = replica_value - self.nominal_value
        self.sum_squared_delta += delta * delta
        self.finite_replica_count += 1

    def build_summary(self) -> SystematicEstimateSummary:
        """Convert accumulated replica deviations into a summary; returns SystematicEstimateSummary."""
        if self.finite_replica_count == 0:
            syst_error = 0.0
        else:
            syst_error = math.sqrt(self.sum_squared_delta / self.finite_replica_count)

        quality_warning = None
        if self.min_relevant_count is not None and self.min_relevant_count < _SPARSE_REPLICA_WARNING_THRESHOLD:
            quality_warning = f"{self.warning_key}={self.min_relevant_count}"
        return SystematicEstimateSummary(syst_error=syst_error, quality_warning=quality_warning)


def geometry_systematics_enabled(config: Config) -> bool:
    """Check whether geometry systematics are enabled; returns bool."""
    return getattr(config, "geometry_systematics", None) is not None


def geometry_variable_detector_names(config: Config) -> set[str]:
    """Collect detector names with effective geometry uncertainty; returns set."""
    geometry_config = config.geometry_systematics
    if geometry_config is None:
        return set()

    variable_names: set[str] = set()
    for detector in config.detectors:
        metadata = config.detector_systematics.get(detector.name)
        if metadata is None:
            continue
        if _detector_is_geometry_variable(metadata, geometry_config):
            variable_names.add(detector.name)
    return variable_names


def resolve_geometry_event_split(config: Config) -> GeometryEventSplit:
    """Resolve the geometry-systematics event split; returns GeometryEventSplit."""
    geometry_config = _require_geometry_systematics(config)
    total_runs = 1 + geometry_config.n_replicas
    replica_events = config.monte_carlo.n_events // total_runs
    nominal_events = config.monte_carlo.n_events - (geometry_config.n_replicas * replica_events)
    return GeometryEventSplit(
        total_events=config.monte_carlo.n_events,
        nominal_events=nominal_events,
        replica_events=replica_events,
        n_replicas=geometry_config.n_replicas,
    )


def build_perturbed_detectors(config: Config, rng: np.random.Generator) -> list[Detector]:
    """Build one perturbed detector list from nominal geometry; returns list[Detector]."""
    geometry_config = _require_geometry_systematics(config)
    common_center_shifts = _sample_common_center_shifts(geometry_config, rng)

    perturbed_detectors: list[Detector] = []
    for detector in config.detectors:
        metadata = config.detector_systematics.get(detector.name)
        if metadata is None:
            perturbed_detectors.append(detector)
            continue

        center_shift = _sample_local_center_shift(metadata, common_center_shifts, rng)
        size_shift = _sample_size_shift(detector, metadata, rng)
        perturbed_detectors.append(
            Detector(
                name=detector.name,
                center=detector.center + center_shift,
                size=detector.size + size_shift,
                efficiency=detector.efficiency,
            )
        )

    return perturbed_detectors


def run_geometry_systematics(
    config: Config,
    progress_callback: ProgressCallback | None = None,
) -> GeometrySystematicsResult:
    """Run the nominal plus replica geometry workflow; returns GeometrySystematicsResult."""
    geometry_config = _require_geometry_systematics(config)
    event_split = resolve_geometry_event_split(config)

    resolved_mc_seed = resolve_seed(config.seed)
    resolved_geometry_seed = (
        geometry_config.seed
        if geometry_config.seed is not None
        else ((resolved_mc_seed + _GEOMETRY_SEED_OFFSET) & _UINT63_MASK)
    )

    nominal_config = _build_run_config(
        config=config,
        seed=resolved_mc_seed,
        n_events=event_split.nominal_events,
        detectors=config.detectors,
    )
    nominal_result = run_simulation(
        nominal_config,
        progress_callback=_offset_progress_callback(
            progress_callback,
            processed_offset=0,
            total_events=event_split.total_events,
        ),
    )

    variable_detector_names = geometry_variable_detector_names(config)
    detector_accumulators = _build_detector_accumulators(nominal_result, variable_detector_names)
    logic_accumulators = _build_logic_accumulators(config, nominal_result, variable_detector_names)
    conditional_accumulators = _build_conditional_accumulators(config, nominal_result, variable_detector_names)

    for replica_index in range(1, geometry_config.n_replicas + 1):
        geometry_rng = np.random.default_rng(resolved_geometry_seed + replica_index)
        perturbed_detectors = build_perturbed_detectors(config, geometry_rng)
        replica_config = _build_run_config(
            config=config,
            seed=resolved_mc_seed + replica_index,
            n_events=event_split.replica_events,
            detectors=perturbed_detectors,
        )
        replica_result = run_simulation(
            replica_config,
            progress_callback=_offset_progress_callback(
                progress_callback,
                processed_offset=event_split.nominal_events + ((replica_index - 1) * event_split.replica_events),
                total_events=event_split.total_events,
            ),
        )
        _update_detector_accumulators(replica_result, detector_accumulators)
        _update_logic_accumulators(config, replica_result, logic_accumulators)
        _update_conditional_accumulators(config, replica_result, conditional_accumulators)

    return GeometrySystematicsResult(
        nominal_result=nominal_result,
        geometry_seed=resolved_geometry_seed,
        event_split=event_split,
        detector_rate_summaries=_finalize_detector_accumulators(detector_accumulators),
        logic_rate_summaries=_finalize_optional_accumulators(logic_accumulators),
        conditional_probability_summaries=_finalize_optional_accumulators(conditional_accumulators),
    )


def _build_run_config(config: Config, seed: int, n_events: int, detectors: list[Detector]) -> Config:
    """Clone one config for a fixed-geometry sub-run; returns Config."""
    return replace(
        config,
        seed=seed,
        monte_carlo=MonteCarloConfig(n_events=n_events),
        detectors=detectors,
    )


def _offset_progress_callback(
    progress_callback: ProgressCallback | None,
    *,
    processed_offset: int,
    total_events: int,
) -> ProgressCallback | None:
    """Wrap one per-run progress callback into global totals; returns callback or None."""
    if progress_callback is None:
        return None

    def wrapped(processed_events: int, _ignored_total: int, _ignored_percent: float) -> None:
        """Translate one per-run progress update into global totals; returns None."""
        cumulative_processed = processed_offset + processed_events
        percent_complete = 100.0 * cumulative_processed / total_events
        progress_callback(cumulative_processed, total_events, percent_complete)

    return wrapped


def _build_detector_accumulators(
    nominal_result: SimulationResult,
    variable_detector_names: set[str],
) -> dict[str, dict[str, _ObservableAccumulator]]:
    """Build detector-rate accumulators from nominal estimates; returns nested dict."""
    nominal_detector_rates = detector_rates(nominal_result)
    accumulators: dict[str, dict[str, _ObservableAccumulator]] = {}
    for detector_name in sorted(variable_detector_names):
        nominal_rate_map = nominal_detector_rates[detector_name]
        accumulators[detector_name] = {
            "geometric": _ObservableAccumulator(
                nominal_value=nominal_rate_map["geometric"].value,
                warning_key="replica_min_n_pass",
            ),
            "fired": _ObservableAccumulator(
                nominal_value=nominal_rate_map["fired"].value,
                warning_key="replica_min_n_pass",
            ),
        }
    return accumulators


def _build_logic_accumulators(
    config: Config,
    nominal_result: SimulationResult,
    variable_detector_names: set[str],
) -> list[dict[str, _ObservableAccumulator] | None]:
    """Build logic-rate accumulators from nominal estimates; returns list."""
    accumulators: list[dict[str, _ObservableAccumulator] | None] = []
    for expression in config.logic_expressions:
        if not (extract_names(expression) & variable_detector_names):
            accumulators.append(None)
            continue

        nominal_rate_map = logic_rates(expression, nominal_result)
        accumulators.append(
            {
                "geometric": _ObservableAccumulator(
                    nominal_value=nominal_rate_map["geometric"].value,
                    warning_key="replica_min_n_pass",
                ),
                "fired": _ObservableAccumulator(
                    nominal_value=nominal_rate_map["fired"].value,
                    warning_key="replica_min_n_pass",
                ),
            }
        )
    return accumulators


def _build_conditional_accumulators(
    config: Config,
    nominal_result: SimulationResult,
    variable_detector_names: set[str],
) -> list[dict[str, _ObservableAccumulator] | None]:
    """Build conditional-probability accumulators from nominal estimates; returns list."""
    accumulators: list[dict[str, _ObservableAccumulator] | None] = []
    for conditional in config.conditionals:
        referenced_names = extract_names(conditional.numerator) | extract_names(conditional.given)
        if not (referenced_names & variable_detector_names):
            accumulators.append(None)
            continue

        fired_estimate = conditional_probability(
            conditional.numerator,
            conditional.given,
            nominal_result,
            mode="fired",
        )
        geometric_estimate = conditional_probability(
            conditional.numerator,
            conditional.given,
            nominal_result,
            mode="geometric",
        )
        accumulators.append(
            {
                "geometric": _ObservableAccumulator(
                    nominal_value=geometric_estimate.value,
                    warning_key="replica_min_n_cond",
                ),
                "fired": _ObservableAccumulator(
                    nominal_value=fired_estimate.value,
                    warning_key="replica_min_n_cond",
                ),
            }
        )
    return accumulators


def _update_detector_accumulators(
    replica_result: SimulationResult,
    detector_accumulators: dict[str, dict[str, _ObservableAccumulator]],
) -> None:
    """Update detector-rate accumulators from one replica result; returns None."""
    if not detector_accumulators:
        return

    replica_detector_rates = detector_rates(replica_result)
    for detector_name, per_mode in detector_accumulators.items():
        geometric_estimate = replica_detector_rates[detector_name]["geometric"]
        fired_estimate = replica_detector_rates[detector_name]["fired"]
        per_mode["geometric"].add_replica(geometric_estimate.value, geometric_estimate.n_pass)
        per_mode["fired"].add_replica(fired_estimate.value, fired_estimate.n_pass)


def _update_logic_accumulators(
    config: Config,
    replica_result: SimulationResult,
    logic_accumulators: list[dict[str, _ObservableAccumulator] | None],
) -> None:
    """Update logic-rate accumulators from one replica result; returns None."""
    for expression, per_mode in zip(config.logic_expressions, logic_accumulators):
        if per_mode is None:
            continue

        rate_map = logic_rates(expression, replica_result)
        per_mode["geometric"].add_replica(rate_map["geometric"].value, rate_map["geometric"].n_pass)
        per_mode["fired"].add_replica(rate_map["fired"].value, rate_map["fired"].n_pass)


def _update_conditional_accumulators(
    config: Config,
    replica_result: SimulationResult,
    conditional_accumulators: list[dict[str, _ObservableAccumulator] | None],
) -> None:
    """Update conditional-probability accumulators from one replica result; returns None."""
    for conditional, per_mode in zip(config.conditionals, conditional_accumulators):
        if per_mode is None:
            continue

        fired_estimate = conditional_probability(
            conditional.numerator,
            conditional.given,
            replica_result,
            mode="fired",
        )
        geometric_estimate = conditional_probability(
            conditional.numerator,
            conditional.given,
            replica_result,
            mode="geometric",
        )
        per_mode["geometric"].add_replica(geometric_estimate.value, geometric_estimate.n_cond)
        per_mode["fired"].add_replica(fired_estimate.value, fired_estimate.n_cond)


def _finalize_detector_accumulators(
    detector_accumulators: dict[str, dict[str, _ObservableAccumulator]],
) -> dict[str, dict[str, SystematicEstimateSummary]]:
    """Convert detector accumulators into summaries; returns nested dict."""
    summaries: dict[str, dict[str, SystematicEstimateSummary]] = {}
    for detector_name, per_mode in detector_accumulators.items():
        summaries[detector_name] = {
            "geometric": per_mode["geometric"].build_summary(),
            "fired": per_mode["fired"].build_summary(),
        }
    return summaries


def _finalize_optional_accumulators(
    accumulators: list[dict[str, _ObservableAccumulator] | None],
) -> list[dict[str, SystematicEstimateSummary] | None]:
    """Convert optional accumulators into summaries; returns list."""
    summaries: list[dict[str, SystematicEstimateSummary] | None] = []
    for per_mode in accumulators:
        if per_mode is None:
            summaries.append(None)
            continue
        summaries.append(
            {
                "geometric": per_mode["geometric"].build_summary(),
                "fired": per_mode["fired"].build_summary(),
            }
        )
    return summaries


def _sample_common_center_shifts(
    geometry_config: GeometrySystematicsConfig,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """Sample one common center shift per configured group; returns dict."""
    common_shifts: dict[str, np.ndarray] = {}
    for group_name in sorted(geometry_config.common_groups):
        sigma = np.asarray(geometry_config.common_groups[group_name].center.sigma, dtype=float)
        common_shifts[group_name] = rng.normal(loc=0.0, scale=sigma, size=3)
    return common_shifts


def _sample_local_center_shift(
    metadata: DetectorGeometryUncertaintyConfig,
    common_center_shifts: dict[str, np.ndarray],
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample one detector-local center shift; returns ndarray."""
    center_metadata = metadata.center
    if center_metadata is None:
        return np.zeros(3, dtype=float)

    if center_metadata.sigma is not None:
        sigma = np.asarray(center_metadata.sigma, dtype=float)
        return rng.normal(loc=0.0, scale=sigma, size=3)

    center_shift = np.array(common_center_shifts[center_metadata.common_group], copy=True)
    if center_metadata.extra_sigma is not None:
        extra_sigma = np.asarray(center_metadata.extra_sigma, dtype=float)
        center_shift += rng.normal(loc=0.0, scale=extra_sigma, size=3)
    return center_shift


def _sample_size_shift(
    detector: Detector,
    metadata: DetectorGeometryUncertaintyConfig,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample one detector-size shift with positivity resampling; returns ndarray."""
    size_metadata = metadata.size
    if size_metadata is None or size_metadata.sigma is None:
        return np.zeros(3, dtype=float)

    sigma = np.asarray(size_metadata.sigma, dtype=float)
    if not np.any(sigma > 0.0):
        return np.zeros(3, dtype=float)

    while True:
        size_shift = rng.normal(loc=0.0, scale=sigma, size=3)
        if np.all(detector.size + size_shift > 0.0):
            return size_shift


def _detector_is_geometry_variable(
    metadata: DetectorGeometryUncertaintyConfig,
    geometry_config: GeometrySystematicsConfig,
) -> bool:
    """Check whether one detector can vary geometrically; returns bool."""
    center_metadata = metadata.center
    if center_metadata is not None:
        if center_metadata.sigma is not None and any(component > 0.0 for component in center_metadata.sigma):
            return True
        if center_metadata.extra_sigma is not None and any(component > 0.0 for component in center_metadata.extra_sigma):
            return True
        if center_metadata.common_group is not None:
            group_sigma = geometry_config.common_groups[center_metadata.common_group].center.sigma
            if any(component > 0.0 for component in group_sigma):
                return True

    size_metadata = metadata.size
    if size_metadata is not None and size_metadata.sigma is not None:
        if any(component > 0.0 for component in size_metadata.sigma):
            return True
    return False


def _require_geometry_systematics(config: Config) -> GeometrySystematicsConfig:
    """Require geometry systematics to be enabled; returns GeometrySystematicsConfig."""
    if config.geometry_systematics is None:
        raise ValueError("Geometry systematics are not enabled for this config.")
    return config.geometry_systematics
