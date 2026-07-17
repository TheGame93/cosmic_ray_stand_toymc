"""Load and validate YAML configuration data for the engine; returns Config."""

from __future__ import annotations

from dataclasses import dataclass, field
import pathlib
from typing import Any

import yaml

from .geometry import Detector
from .logic import extract_names


class ConfigError(ValueError):
    """Signal invalid or missing YAML configuration data; returns no value."""


class SourceModelConfig:
    """Mark the discriminated `source_model` config union."""


@dataclass(frozen=True)
class CosmicSourceConfig(SourceModelConfig):
    """Store cosmic-ray source settings for a downward sky intensity model."""

    model: str
    flux_hz_per_cm2: float


@dataclass(frozen=True)
class BeamSourceConfig(SourceModelConfig):
    """Store directed beam source settings that travel in `+z`."""

    profile: str
    center: tuple[float, float]
    size: tuple[float, ...]
    flux_hz_per_cm2: float


@dataclass(frozen=True)
class ObjectSourceConfig(SourceModelConfig):
    """Store mounted disk source settings for one-sided hemisphere emission."""

    center: tuple[float, float, float]
    diameter: float
    normal: tuple[float, float, float]
    angular_model: str
    activity_bq: float | None
    yield_per_decay: float
    surface_emission_rate_hz: float | None

    def front_emission_rate_hz(self) -> float:
        """Return the front-side particle emission rate; returns float."""
        if self.surface_emission_rate_hz is not None:
            return self.surface_emission_rate_hz
        if self.activity_bq is None:
            raise ValueError("activity_bq must be present when no surface_emission_rate_hz is configured.")
        return 0.5 * self.activity_bq * self.yield_per_decay


@dataclass(frozen=True)
class MonteCarloConfig:
    """Store Monte Carlo controls loaded from YAML."""

    n_events: int


@dataclass(frozen=True)
class GeometryCommonGroupCenterConfig:
    """Store the shared center-shift sigma for one geometry common group."""

    sigma: tuple[float, float, float]


@dataclass(frozen=True)
class GeometryCommonGroupConfig:
    """Store one named geometry common-group definition."""

    center: GeometryCommonGroupCenterConfig


@dataclass(frozen=True)
class GeometrySystematicsConfig:
    """Store top-level geometry-systematics controls and shared groups."""

    n_replicas: int
    seed: int | None
    common_groups: dict[str, GeometryCommonGroupConfig] = field(default_factory=dict)


@dataclass(frozen=True)
class CenterUncertaintyConfig:
    """Store detector-center uncertainty metadata separate from nominal geometry."""

    sigma: tuple[float, float, float] | None = None
    common_group: str | None = None
    extra_sigma: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class SizeUncertaintyConfig:
    """Store detector-size uncertainty metadata separate from nominal geometry."""

    sigma: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class DetectorGeometryUncertaintyConfig:
    """Store one detector's optional geometry-systematics metadata."""

    center: CenterUncertaintyConfig | None = None
    size: SizeUncertaintyConfig | None = None


@dataclass(frozen=True)
class ConditionalConfig:
    """Store one conditional probability request from the config."""

    name: str
    numerator: str
    given: str


@dataclass(frozen=True)
class OutputConfig:
    """Store CLI formatting settings loaded from YAML."""

    detector_rate_decimals: int = 1
    logic_rate_decimals: int = 1


@dataclass(frozen=True)
class Config:
    """Store the validated engine configuration."""

    seed: int | None
    source_model: SourceModelConfig
    monte_carlo: MonteCarloConfig
    detectors: list[Detector]
    logic_expressions: list[str]
    conditionals: list[ConditionalConfig]
    output: OutputConfig
    gui: dict[str, Any] | None
    geometry_systematics: GeometrySystematicsConfig | None = None
    detector_systematics: dict[str, DetectorGeometryUncertaintyConfig] = field(default_factory=dict)


def load_config(path: str | pathlib.Path) -> Config:
    """Load, validate, and normalize a YAML configuration file; returns Config."""
    config_path = pathlib.Path(path)
    try:
        raw_data = yaml.safe_load(config_path.read_text())
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file not found: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in configuration file: {config_path}") from exc

    if not isinstance(raw_data, dict):
        raise ConfigError("Top-level YAML content must be a mapping.")

    seed = _read_optional_seed(raw_data.get("seed"))
    source_model = _parse_source_model(raw_data.get("source_model"))
    monte_carlo = _parse_monte_carlo(raw_data.get("monte_carlo"))
    geometry_systematics = _parse_systematics(raw_data.get("systematics"))
    detectors, detector_systematics = _parse_detectors(raw_data.get("detectors"))
    _validate_geometry_systematics(monte_carlo, geometry_systematics, detector_systematics)

    detector_names = {detector.name for detector in detectors}
    logic_expressions, conditionals = _parse_logic(raw_data.get("logic"), detector_names)
    output = _parse_output(raw_data.get("output"))
    gui = _parse_gui(raw_data.get("gui"))

    return Config(
        seed=seed,
        source_model=source_model,
        monte_carlo=monte_carlo,
        detectors=detectors,
        logic_expressions=logic_expressions,
        conditionals=conditionals,
        output=output,
        gui=gui,
        geometry_systematics=geometry_systematics,
        detector_systematics=detector_systematics,
    )


def _read_optional_seed(value: Any) -> int | None:
    """Read the optional random seed from YAML; returns int or None."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("seed must be an integer or null.")
    return value


_BEAM_PROFILE_SIZE_LENGTHS = {"uniform": 1, "gaussian": 2}
_OBJECT_ANGULAR_MODELS = {"uniform", "cosine-weighted"}


def _parse_source_model(raw_source_model: Any) -> SourceModelConfig:
    """Parse and validate the `source_model` block; returns SourceModelConfig."""
    if not isinstance(raw_source_model, dict):
        raise ConfigError("source_model must be a mapping.")

    source_type = raw_source_model.get("type")
    if source_type == "cosmic":
        return _parse_cosmic_source(raw_source_model)
    if source_type == "beam":
        return _parse_beam_source(raw_source_model)
    if source_type == "object":
        return _parse_object_source(raw_source_model)
    raise ConfigError("source_model.type must be one of 'cosmic', 'beam', 'object'.")


def _parse_cosmic_source(raw: dict[str, Any]) -> CosmicSourceConfig:
    """Parse a `source_model.type: cosmic` block; returns CosmicSourceConfig."""
    model = raw.get("model")
    if model != "cos2":
        raise ConfigError("Only source_model.model = 'cos2' is supported for type 'cosmic'.")

    flux_hz_per_cm2 = _read_positive_float(raw.get("flux_hz_per_cm2"), "source_model.flux_hz_per_cm2")
    return CosmicSourceConfig(model=model, flux_hz_per_cm2=flux_hz_per_cm2)


def _parse_beam_source(raw: dict[str, Any]) -> BeamSourceConfig:
    """Parse a `source_model.type: beam` block; returns BeamSourceConfig."""
    profile = raw.get("profile")
    if profile not in _BEAM_PROFILE_SIZE_LENGTHS:
        raise ConfigError("source_model.profile must be one of 'uniform', 'gaussian'.")

    center = _read_float_tuple(raw.get("center"), 2, "source_model.center")
    size = _read_float_tuple(
        raw.get("size"), _BEAM_PROFILE_SIZE_LENGTHS[profile], "source_model.size", positive=True
    )
    flux_hz_per_cm2 = _read_positive_float(raw.get("flux_hz_per_cm2"), "source_model.flux_hz_per_cm2")
    return BeamSourceConfig(profile=profile, center=center, size=size, flux_hz_per_cm2=flux_hz_per_cm2)


def _parse_object_source(raw: dict[str, Any]) -> ObjectSourceConfig:
    """Parse a `source_model.type: object` block; returns ObjectSourceConfig."""
    center = _read_float_tuple(raw.get("center"), 3, "source_model.center")
    diameter = _read_positive_float(raw.get("diameter"), "source_model.diameter")
    normal = _read_float_tuple(raw.get("normal"), 3, "source_model.normal")
    if all(component == 0.0 for component in normal):
        raise ConfigError("source_model.normal must not be the zero vector.")

    angular_model = raw.get("angular_model")
    if angular_model == "material-dependent":
        raise ConfigError("source_model.angular_model = 'material-dependent' is not yet implemented.")
    if angular_model not in _OBJECT_ANGULAR_MODELS:
        raise ConfigError(
            "source_model.angular_model must be one of 'uniform', 'cosine-weighted', 'material-dependent'."
        )

    activity_raw = raw.get("activity_bq")
    activity_bq = (
        _read_positive_float(activity_raw, "source_model.activity_bq")
        if activity_raw is not None
        else None
    )

    emission_raw = raw.get("surface_emission_rate_hz")
    surface_emission_rate_hz = (
        _read_positive_float(emission_raw, "source_model.surface_emission_rate_hz")
        if emission_raw is not None
        else None
    )

    if activity_bq is None and surface_emission_rate_hz is None:
        raise ConfigError(
            "At least one of source_model.activity_bq or source_model.surface_emission_rate_hz must be provided."
        )

    yield_raw = raw.get("yield_per_decay", 1.0)
    yield_per_decay = _read_positive_float(yield_raw, "source_model.yield_per_decay")
    if activity_bq is None and "yield_per_decay" in raw:
        raise ConfigError(
            "source_model.yield_per_decay requires source_model.activity_bq because it only affects the derived emission rate."
        )

    return ObjectSourceConfig(
        center=center,
        diameter=diameter,
        normal=normal,
        angular_model=angular_model,
        activity_bq=activity_bq,
        yield_per_decay=yield_per_decay,
        surface_emission_rate_hz=surface_emission_rate_hz,
    )


def _read_float_tuple(
    value: Any, length: int, field_name: str, *, positive: bool = False
) -> tuple[float, ...]:
    """Read a fixed-length numeric list as floats; returns tuple."""
    if not isinstance(value, list) or len(value) != length:
        raise ConfigError(f"{field_name} must be a list of {length} number(s).")

    components = tuple(_read_float(component, field_name) for component in value)
    if positive and any(component <= 0.0 for component in components):
        raise ConfigError(f"{field_name} must contain only strictly positive numbers.")
    return components


def _parse_monte_carlo(raw_monte_carlo: Any) -> MonteCarloConfig:
    """Parse Monte Carlo settings; returns MonteCarloConfig."""
    if not isinstance(raw_monte_carlo, dict):
        raise ConfigError("monte_carlo must be a mapping.")

    n_events = raw_monte_carlo.get("n_events")
    if isinstance(n_events, bool) or not isinstance(n_events, int) or n_events <= 0:
        raise ConfigError("monte_carlo.n_events must be a positive integer.")
    return MonteCarloConfig(n_events=n_events)


def _parse_systematics(raw_systematics: Any) -> GeometrySystematicsConfig | None:
    """Parse optional systematics settings; returns GeometrySystematicsConfig or None."""
    if raw_systematics is None:
        return None
    if not isinstance(raw_systematics, dict):
        raise ConfigError("systematics must be a mapping when provided.")

    raw_geometry = raw_systematics.get("geometry")
    if raw_geometry is None:
        return None
    if not isinstance(raw_geometry, dict):
        raise ConfigError("systematics.geometry must be a mapping when provided.")

    n_replicas = raw_geometry.get("n_replicas")
    if isinstance(n_replicas, bool) or not isinstance(n_replicas, int) or n_replicas <= 0:
        raise ConfigError("systematics.geometry.n_replicas must be a positive integer.")

    seed = _read_optional_seed(raw_geometry.get("seed"))
    common_groups = _parse_common_groups(raw_geometry.get("common_groups", {}))
    return GeometrySystematicsConfig(n_replicas=n_replicas, seed=seed, common_groups=common_groups)


def _parse_common_groups(raw_common_groups: Any) -> dict[str, GeometryCommonGroupConfig]:
    """Parse shared geometry common groups; returns dict."""
    if not isinstance(raw_common_groups, dict):
        raise ConfigError("systematics.geometry.common_groups must be a mapping when provided.")

    common_groups: dict[str, GeometryCommonGroupConfig] = {}
    for group_name, raw_group in raw_common_groups.items():
        if not isinstance(group_name, str) or not group_name:
            raise ConfigError("Each systematics.geometry.common_groups key must be a non-empty string.")
        if not isinstance(raw_group, dict):
            raise ConfigError(f"systematics.geometry.common_groups.{group_name} must be a mapping.")
        _reject_unknown_keys(raw_group, {"center"}, f"systematics.geometry.common_groups.{group_name}")

        raw_center = raw_group.get("center")
        if not isinstance(raw_center, dict):
            raise ConfigError(f"systematics.geometry.common_groups.{group_name}.center must be a mapping.")
        _reject_unknown_keys(raw_center, {"sigma"}, f"systematics.geometry.common_groups.{group_name}.center")
        sigma = _read_sigma_tuple(raw_center.get("sigma"), f"systematics.geometry.common_groups.{group_name}.center.sigma")
        common_groups[group_name] = GeometryCommonGroupConfig(center=GeometryCommonGroupCenterConfig(sigma=sigma))

    return common_groups


def _parse_detectors(raw_detectors: Any) -> tuple[list[Detector], dict[str, DetectorGeometryUncertaintyConfig]]:
    """Parse and validate detector definitions; returns detectors plus metadata."""
    if not isinstance(raw_detectors, list) or not raw_detectors:
        raise ConfigError("detectors must be a non-empty list.")

    detectors: list[Detector] = []
    detector_systematics: dict[str, DetectorGeometryUncertaintyConfig] = {}
    seen_names: set[str] = set()

    for raw_detector in raw_detectors:
        if not isinstance(raw_detector, dict):
            raise ConfigError("Each detector entry must be a mapping.")

        name = raw_detector.get("name")
        if not isinstance(name, str) or not name:
            raise ConfigError("Each detector must have a non-empty string name.")
        if name in seen_names:
            raise ConfigError(f"Duplicate detector name: {name}")
        seen_names.add(name)

        center_value, center_metadata = _parse_detector_center(raw_detector.get("center"), name)
        size_value, size_metadata = _parse_detector_size(raw_detector.get("size"), name)
        efficiency = _read_float(raw_detector.get("efficiency"), f"efficiency for detector {name!r}")

        try:
            detector = Detector(name=name, center=center_value, size=size_value, efficiency=efficiency)
        except ValueError as exc:
            raise ConfigError(f"Invalid detector {name!r}: {exc}") from exc

        detectors.append(detector)

        geometry_metadata = DetectorGeometryUncertaintyConfig(center=center_metadata, size=size_metadata)
        if _detector_declares_geometry_uncertainty(geometry_metadata):
            detector_systematics[name] = geometry_metadata

    return detectors, detector_systematics


def _parse_detector_center(value: Any, detector_name: str) -> tuple[tuple[float, float, float], CenterUncertaintyConfig | None]:
    """Parse one detector center field; returns nominal center plus metadata."""
    field_name = f"detectors[{detector_name}].center"
    if isinstance(value, list):
        return _read_float_tuple(value, 3, field_name), None
    if not isinstance(value, dict):
        raise ConfigError(f"{field_name} must be either a 3-element list or a mapping.")

    _reject_unknown_keys(value, {"value", "sigma", "common_group", "extra_sigma"}, field_name)
    nominal_value = _read_float_tuple(value.get("value"), 3, f"{field_name}.value")
    sigma = value.get("sigma")
    common_group = value.get("common_group")
    extra_sigma = value.get("extra_sigma")

    if sigma is not None:
        if common_group is not None or extra_sigma is not None:
            raise ConfigError(f"{field_name}.sigma cannot be combined with common_group or extra_sigma.")
        return nominal_value, CenterUncertaintyConfig(
            sigma=_read_sigma_tuple(sigma, f"{field_name}.sigma"),
        )

    if extra_sigma is not None and common_group is None:
        raise ConfigError(f"{field_name}.extra_sigma requires {field_name}.common_group.")
    if common_group is None:
        raise ConfigError(f"{field_name} must define either sigma or common_group.")
    if not isinstance(common_group, str) or not common_group:
        raise ConfigError(f"{field_name}.common_group must be a non-empty string.")

    parsed_extra_sigma = (
        _read_sigma_tuple(extra_sigma, f"{field_name}.extra_sigma")
        if extra_sigma is not None
        else None
    )
    return nominal_value, CenterUncertaintyConfig(common_group=common_group, extra_sigma=parsed_extra_sigma)


def _parse_detector_size(value: Any, detector_name: str) -> tuple[tuple[float, float, float], SizeUncertaintyConfig | None]:
    """Parse one detector size field; returns nominal size plus metadata."""
    field_name = f"detectors[{detector_name}].size"
    if isinstance(value, list):
        return _read_float_tuple(value, 3, field_name), None
    if not isinstance(value, dict):
        raise ConfigError(f"{field_name} must be either a 3-element list or a mapping.")

    _reject_unknown_keys(value, {"value", "sigma"}, field_name)
    nominal_value = _read_float_tuple(value.get("value"), 3, f"{field_name}.value")
    sigma = value.get("sigma")
    if sigma is None:
        return nominal_value, None
    return nominal_value, SizeUncertaintyConfig(sigma=_read_sigma_tuple(sigma, f"{field_name}.sigma"))


def _read_sigma_tuple(value: Any, field_name: str) -> tuple[float, float, float]:
    """Read one non-negative sigma vector from YAML; returns tuple."""
    components = _read_float_tuple(value, 3, field_name)
    if any(component < 0.0 for component in components):
        raise ConfigError(f"{field_name} must contain only non-negative numbers.")
    return components


def _validate_geometry_systematics(
    monte_carlo: MonteCarloConfig,
    geometry_systematics: GeometrySystematicsConfig | None,
    detector_systematics: dict[str, DetectorGeometryUncertaintyConfig],
) -> None:
    """Validate cross-field geometry-systematics rules; returns None."""
    if detector_systematics and geometry_systematics is None:
        raise ConfigError(
            "Detector geometry-uncertainty fields require a systematics.geometry block."
        )

    if geometry_systematics is None:
        return

    total_runs = 1 + geometry_systematics.n_replicas
    if monte_carlo.n_events < total_runs:
        raise ConfigError(
            f"monte_carlo.n_events must be at least {total_runs} when geometry systematics are enabled."
        )

    for detector_name, metadata in detector_systematics.items():
        center_metadata = metadata.center
        if center_metadata is None or center_metadata.common_group is None:
            continue
        if center_metadata.common_group not in geometry_systematics.common_groups:
            raise ConfigError(
                f"Detector {detector_name!r} references unknown geometry common_group {center_metadata.common_group!r}."
            )

    if not any(
        _detector_has_effective_geometry_uncertainty(metadata, geometry_systematics.common_groups)
        for metadata in detector_systematics.values()
    ):
        raise ConfigError(
            "systematics.geometry requires at least one effective nonzero detector geometry uncertainty."
        )


def _detector_declares_geometry_uncertainty(metadata: DetectorGeometryUncertaintyConfig) -> bool:
    """Check whether a detector declares any geometry-uncertainty fields; returns bool."""
    center_metadata = metadata.center
    if center_metadata is not None:
        if center_metadata.sigma is not None:
            return True
        if center_metadata.common_group is not None:
            return True
        if center_metadata.extra_sigma is not None:
            return True

    size_metadata = metadata.size
    if size_metadata is not None and size_metadata.sigma is not None:
        return True
    return False


def _detector_has_effective_geometry_uncertainty(
    metadata: DetectorGeometryUncertaintyConfig,
    common_groups: dict[str, GeometryCommonGroupConfig],
) -> bool:
    """Check whether a detector can vary geometrically; returns bool."""
    center_metadata = metadata.center
    if center_metadata is not None:
        if _has_nonzero_sigma(center_metadata.sigma):
            return True
        if _has_nonzero_sigma(center_metadata.extra_sigma):
            return True
        if center_metadata.common_group is not None:
            group_sigma = common_groups[center_metadata.common_group].center.sigma
            if _has_nonzero_sigma(group_sigma):
                return True

    size_metadata = metadata.size
    if size_metadata is not None and _has_nonzero_sigma(size_metadata.sigma):
        return True
    return False


def _has_nonzero_sigma(sigma: tuple[float, float, float] | None) -> bool:
    """Check whether a sigma vector has any non-zero component; returns bool."""
    return sigma is not None and any(component > 0.0 for component in sigma)


def _parse_logic(raw_logic: Any, detector_names: set[str]) -> tuple[list[str], list[ConditionalConfig]]:
    """Parse logic expressions and conditionals; returns validated lists."""
    if raw_logic is None:
        return [], []
    if not isinstance(raw_logic, dict):
        raise ConfigError("logic must be a mapping when provided.")

    expressions = raw_logic.get("expressions", [])
    if not isinstance(expressions, list):
        raise ConfigError("logic.expressions must be a list.")

    validated_expressions: list[str] = []
    for expression in expressions:
        if not isinstance(expression, str):
            raise ConfigError("Each logic expression must be a string.")
        _validate_expression_names(expression, detector_names)
        validated_expressions.append(expression)

    raw_conditionals = raw_logic.get("conditional", [])
    if not isinstance(raw_conditionals, list):
        raise ConfigError("logic.conditional must be a list.")

    conditionals: list[ConditionalConfig] = []
    for raw_conditional in raw_conditionals:
        if not isinstance(raw_conditional, dict):
            raise ConfigError("Each conditional entry must be a mapping.")

        name = raw_conditional.get("name")
        numerator = raw_conditional.get("numerator")
        given = raw_conditional.get("given")

        if not isinstance(name, str) or not name:
            raise ConfigError("Each conditional entry must have a non-empty string name.")
        if not isinstance(numerator, str) or not numerator:
            raise ConfigError(f"Conditional {name!r} must provide a numerator expression.")
        if not isinstance(given, str) or not given:
            raise ConfigError(f"Conditional {name!r} must provide a given expression.")
        if "mode" in raw_conditional:
            raise ConfigError(
                f"Conditional {name!r} must not define mode; both fired and geometric are reported automatically."
            )

        _validate_expression_names(numerator, detector_names)
        _validate_expression_names(given, detector_names)
        conditionals.append(ConditionalConfig(name=name, numerator=numerator, given=given))

    return validated_expressions, conditionals


def _validate_expression_names(expression: str, detector_names: set[str]) -> None:
    """Validate detector references inside one logic expression; returns None."""
    try:
        referenced_names = extract_names(expression)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc

    missing_names = sorted(referenced_names - detector_names)
    if missing_names:
        joined = ", ".join(missing_names)
        raise ConfigError(f"Logic expression references unknown detector names: {joined}")


def _parse_gui(raw_gui: Any) -> dict[str, Any] | None:
    """Preserve optional GUI configuration as opaque data; returns mapping or None."""
    if raw_gui is None:
        return None
    if not isinstance(raw_gui, dict):
        raise ConfigError("gui must be a mapping when provided.")
    return raw_gui


def _parse_output(raw_output: Any) -> OutputConfig:
    """Parse optional CLI formatting settings; returns OutputConfig."""
    if raw_output is None:
        return OutputConfig()
    if not isinstance(raw_output, dict):
        raise ConfigError("output must be a mapping when provided.")

    detector_rate_decimals = _read_non_negative_int(
        raw_output.get("detector_rate_decimals", 1),
        "output.detector_rate_decimals",
    )
    logic_rate_decimals = _read_non_negative_int(
        raw_output.get("logic_rate_decimals", 1),
        "output.logic_rate_decimals",
    )
    return OutputConfig(
        detector_rate_decimals=detector_rate_decimals,
        logic_rate_decimals=logic_rate_decimals,
    )


def _read_float(value: Any, field_name: str) -> float:
    """Read one numeric field as float; returns float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{field_name} must be numeric.")
    return float(value)


def _read_positive_float(value: Any, field_name: str) -> float:
    """Read one strictly positive numeric field; returns float."""
    numeric_value = _read_float(value, field_name)
    if numeric_value <= 0.0:
        raise ConfigError(f"{field_name} must be strictly positive.")
    return numeric_value


def _read_non_negative_int(value: Any, field_name: str) -> int:
    """Read one non-negative integer field; returns int."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{field_name} must be an integer.")
    if value < 0:
        raise ConfigError(f"{field_name} must be non-negative.")
    return value


def _reject_unknown_keys(raw_mapping: dict[str, Any], allowed_keys: set[str], field_name: str) -> None:
    """Reject unknown keys inside a structured mapping; returns None."""
    unknown_keys = sorted(set(raw_mapping) - allowed_keys)
    if unknown_keys:
        joined = ", ".join(unknown_keys)
        raise ConfigError(f"{field_name} contains unknown key(s): {joined}")
