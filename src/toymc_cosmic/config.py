"""YAML configuration loading and validation for the engine."""

from __future__ import annotations

from dataclasses import dataclass
import math
import pathlib
from typing import Any

import yaml

from .geometry import Detector
from .logic import extract_names


class ConfigError(ValueError):
    """Raised when the YAML configuration is missing or contains invalid data."""


class SourceModelConfig:
    """Marker base for the discriminated `source_model` config union."""


@dataclass(frozen=True)
class CosmicSourceConfig(SourceModelConfig):
    """Cosmic-ray source settings: zenith-angle sampling over a downward cone.

    Attributes:
        theta_max: Maximum zenith angle in radians.
        model: Angular model name; only `"cos2"` is supported today.
        flux_hz_per_cm2: Total downward flux over the simulated angular cone.
    """

    theta_max: float
    model: str
    flux_hz_per_cm2: float


@dataclass(frozen=True)
class BeamSourceConfig(SourceModelConfig):
    """Directed beam source settings; travels in `+z` (upstream to downstream).

    Attributes:
        profile: Transverse profile name: `"uniform"`, `"gaussian"`, or `"divergence"`.
        center: Transverse profile center `(xc, yc)`.
        size: Profile size parameters; meaning depends on `profile`
            (`uniform`: `[diameter]`, `gaussian`: `[FWHM_x, FWHM_y]`,
            `divergence`: unvalidated, format not yet defined).
        flux_hz_per_cm2: `uniform`: the (spatially constant) flux; `gaussian`:
            the average flux over the FWHM ellipse.
    """

    profile: str
    center: tuple[float, float]
    size: tuple[float, ...]
    flux_hz_per_cm2: float


@dataclass(frozen=True)
class ObjectSourceConfig(SourceModelConfig):
    """Radioactive point/volume source settings; emits isotropically over 4*pi.

    Attributes:
        shape: Volume shape: `"sphere"`, `"disk"`, or `"box"`.
        center: Volume center `(xc, yc, zc)`.
        size: Shape size parameters (`sphere`: `[diameter]`, `disk`:
            `[diameter_xy, wz]`, `box`: `[wx, wy, wz]`).
        activity_hz: Total emission rate in Hz.
    """

    shape: str
    center: tuple[float, float, float]
    size: tuple[float, ...]
    activity_hz: float


@dataclass(frozen=True)
class MonteCarloConfig:
    """Monte Carlo controls stored in the YAML file."""

    n_events: int


@dataclass(frozen=True)
class ConditionalConfig:
    """Configuration for a conditional probability request."""

    name: str
    numerator: str
    given: str


@dataclass(frozen=True)
class OutputConfig:
    """CLI formatting settings loaded from YAML."""

    detector_rate_decimals: int = 1
    logic_rate_decimals: int = 1


@dataclass(frozen=True)
class Config:
    """Validated engine configuration.

    Attributes:
        seed: Optional fixed seed. `None` means resolve from local time at runtime.
        source_model: Validated source settings; one of `CosmicSourceConfig`,
            `BeamSourceConfig`, or `ObjectSourceConfig`.
        monte_carlo: Monte Carlo controls such as event count.
        detectors: Physical detector definitions.
        logic_expressions: Expressions whose rates should be reported.
        conditionals: Conditional probability requests to evaluate.
        output: CLI formatting settings.
        gui: Optional GUI config preserved as opaque data for the future GUI layer.
    """

    seed: int | None
    source_model: SourceModelConfig
    monte_carlo: MonteCarloConfig
    detectors: list[Detector]
    logic_expressions: list[str]
    conditionals: list[ConditionalConfig]
    output: OutputConfig
    gui: dict[str, Any] | None


def load_config(path: str | pathlib.Path) -> Config:
    """Load, validate, and normalize a YAML configuration file; returns the resulting Config."""
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
    detectors = _parse_detectors(raw_data.get("detectors"))
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
    )


def _read_optional_seed(value: Any) -> int | None:
    """Read the optional random seed from the YAML file."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("seed must be an integer or null.")
    return value


_BEAM_PROFILES = ("uniform", "gaussian", "divergence")
_BEAM_PROFILE_SIZE_LENGTHS = {"uniform": 1, "gaussian": 2}
_OBJECT_SHAPE_SIZE_LENGTHS = {"sphere": 1, "disk": 2, "box": 3}


def _parse_source_model(raw_source_model: Any) -> SourceModelConfig:
    """Parse and validate the `source_model` block; returns the matching config dataclass."""
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
    """Parse a `source_model.type: cosmic` block."""
    theta_max_deg = _read_float(raw.get("theta_max_deg"), "source_model.theta_max_deg")
    if not 0.0 < theta_max_deg < 90.0:
        raise ConfigError("source_model.theta_max_deg must be between 0 and 90.")

    model = raw.get("model")
    if model != "cos2":
        raise ConfigError("Only source_model.model = 'cos2' is supported for type 'cosmic'.")

    flux_hz_per_cm2 = _read_float(raw.get("flux_hz_per_cm2"), "source_model.flux_hz_per_cm2")
    if flux_hz_per_cm2 <= 0.0:
        raise ConfigError("source_model.flux_hz_per_cm2 must be strictly positive.")

    return CosmicSourceConfig(
        theta_max=math.radians(theta_max_deg),
        model=model,
        flux_hz_per_cm2=flux_hz_per_cm2,
    )


def _parse_beam_source(raw: dict[str, Any]) -> BeamSourceConfig:
    """Parse a `source_model.type: beam` block."""
    profile = raw.get("profile")
    if profile not in _BEAM_PROFILES:
        raise ConfigError("source_model.profile must be one of 'uniform', 'gaussian', 'divergence'.")

    center = _read_float_tuple(raw.get("center"), 2, "source_model.center")
    size = _read_size_list(raw.get("size"))

    expected_length = _BEAM_PROFILE_SIZE_LENGTHS.get(profile)
    if expected_length is not None:
        _validate_size_length(size, expected_length, f"profile {profile!r}")

    flux_hz_per_cm2 = _read_float(raw.get("flux_hz_per_cm2"), "source_model.flux_hz_per_cm2")
    if flux_hz_per_cm2 <= 0.0:
        raise ConfigError("source_model.flux_hz_per_cm2 must be strictly positive.")

    return BeamSourceConfig(profile=profile, center=center, size=size, flux_hz_per_cm2=flux_hz_per_cm2)


def _parse_object_source(raw: dict[str, Any]) -> ObjectSourceConfig:
    """Parse a `source_model.type: object` block."""
    shape = raw.get("shape")
    if shape not in _OBJECT_SHAPE_SIZE_LENGTHS:
        raise ConfigError("source_model.shape must be one of 'sphere', 'disk', 'box'.")

    center = _read_float_tuple(raw.get("center"), 3, "source_model.center")
    size = _read_size_list(raw.get("size"))
    _validate_size_length(size, _OBJECT_SHAPE_SIZE_LENGTHS[shape], f"shape {shape!r}")

    activity_hz = _read_float(raw.get("activity_hz"), "source_model.activity_hz")
    if activity_hz <= 0.0:
        raise ConfigError("source_model.activity_hz must be strictly positive.")

    return ObjectSourceConfig(shape=shape, center=center, size=size, activity_hz=activity_hz)


def _read_size_list(value: Any) -> tuple[float, ...]:
    """Read `source_model.size` as a non-empty tuple of floats."""
    if not isinstance(value, list) or not value:
        raise ConfigError("source_model.size must be a non-empty list.")
    return tuple(_read_float(component, "source_model.size") for component in value)


def _validate_size_length(size: tuple[float, ...], expected_length: int, context: str) -> None:
    """Validate that `size` has the expected length and strictly positive components."""
    if len(size) != expected_length or any(component <= 0.0 for component in size):
        raise ConfigError(
            f"source_model.size for {context} must be a list of "
            f"{expected_length} strictly positive number(s)."
        )


def _read_float_tuple(value: Any, length: int, field_name: str) -> tuple[float, ...]:
    """Read a fixed-length list of numeric values as a tuple of floats."""
    if not isinstance(value, list) or len(value) != length:
        raise ConfigError(f"{field_name} must be a list of {length} number(s).")
    return tuple(_read_float(component, field_name) for component in value)


def _parse_monte_carlo(raw_monte_carlo: Any) -> MonteCarloConfig:
    """Parse Monte Carlo settings."""
    if not isinstance(raw_monte_carlo, dict):
        raise ConfigError("monte_carlo must be a mapping.")

    n_events = raw_monte_carlo.get("n_events")
    if isinstance(n_events, bool) or not isinstance(n_events, int) or n_events <= 0:
        raise ConfigError("monte_carlo.n_events must be a positive integer.")
    return MonteCarloConfig(n_events=n_events)


def _parse_detectors(raw_detectors: Any) -> list[Detector]:
    """Parse and validate detector definitions."""
    if not isinstance(raw_detectors, list) or not raw_detectors:
        raise ConfigError("detectors must be a non-empty list.")

    detectors: list[Detector] = []
    seen_names: set[str] = set()

    for raw_detector in raw_detectors:
        if not isinstance(raw_detector, dict):
            raise ConfigError("Each detector entry must be a mapping.")

        name = raw_detector.get("name")
        center = raw_detector.get("center")
        size = raw_detector.get("size")
        efficiency = _read_float(raw_detector.get("efficiency"), f"efficiency for detector {name!r}")

        if not isinstance(name, str) or not name:
            raise ConfigError("Each detector must have a non-empty string name.")
        if name in seen_names:
            raise ConfigError(f"Duplicate detector name: {name}")
        seen_names.add(name)

        try:
            detector = Detector(name=name, center=center, size=size, efficiency=efficiency)
        except ValueError as exc:
            raise ConfigError(f"Invalid detector {name!r}: {exc}") from exc

        detectors.append(detector)

    return detectors


def _parse_logic(raw_logic: Any, detector_names: set[str]) -> tuple[list[str], list[ConditionalConfig]]:
    """Parse logic expressions and validate detector references; returns the validated expressions and conditional configs."""
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

        conditionals.append(
            ConditionalConfig(name=name, numerator=numerator, given=given)
        )

    return validated_expressions, conditionals


def _validate_expression_names(expression: str, detector_names: set[str]) -> None:
    """Validate that a logic expression references known detectors only."""
    try:
        referenced_names = extract_names(expression)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc

    missing_names = sorted(referenced_names - detector_names)
    if missing_names:
        joined = ", ".join(missing_names)
        raise ConfigError(f"Logic expression references unknown detector names: {joined}")


def _parse_gui(raw_gui: Any) -> dict[str, Any] | None:
    """Preserve optional GUI configuration without engine-level interpretation."""
    if raw_gui is None:
        return None
    if not isinstance(raw_gui, dict):
        raise ConfigError("gui must be a mapping when provided.")
    return raw_gui


def _parse_output(raw_output: Any) -> OutputConfig:
    """Parse optional CLI output-format settings."""
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
    """Read a numeric field and convert it to float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{field_name} must be numeric.")
    return float(value)


def _read_non_negative_int(value: Any, field_name: str) -> int:
    """Read a non-negative integer setting from the YAML file."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{field_name} must be an integer.")
    if value < 0:
        raise ConfigError(f"{field_name} must be non-negative.")
    return value
