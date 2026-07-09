"""Public entry points for the toy cosmic-ray Monte Carlo engine."""

from .config import Config, ConfigError, ConditionalConfig, load_config
from .geometry import Detector
from .rates import ProbabilityEstimate, RateEstimate
from .simulation import SimulationResult, run_simulation
from .tracks import Tracks

__all__ = [
    "Config",
    "ConfigError",
    "ConditionalConfig",
    "Detector",
    "ProbabilityEstimate",
    "RateEstimate",
    "SimulationResult",
    "Tracks",
    "load_config",
    "run_simulation",
]
