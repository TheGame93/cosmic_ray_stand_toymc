"""Public entry points for the toy cosmic-ray Monte Carlo engine."""

from .config import (
    BeamSourceConfig,
    Config,
    ConfigError,
    ConditionalConfig,
    CosmicSourceConfig,
    ObjectSourceConfig,
    SourceModelConfig,
    load_config,
)
from .geometry import Detector
from .rates import ProbabilityEstimate, RateEstimate
from .simulation import SimulationResult, run_simulation
from .tracks import Tracks

__all__ = [
    "BeamSourceConfig",
    "Config",
    "ConfigError",
    "ConditionalConfig",
    "CosmicSourceConfig",
    "Detector",
    "ObjectSourceConfig",
    "ProbabilityEstimate",
    "RateEstimate",
    "SimulationResult",
    "SourceModelConfig",
    "Tracks",
    "load_config",
    "run_simulation",
]
