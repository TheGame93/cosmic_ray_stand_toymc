# Goal

`toymc_cosmic` is a geometric toy Monte Carlo for cosmic-ray detector stands.
Given a YAML description of detector geometry, efficiencies, and boolean
trigger logic, it estimates:

- per-detector rates, in both a purely geometric sense (did a track cross the
  volume) and a "fired" sense (did the detector also pass its efficiency
  roll)
- rates for arbitrary boolean logic expressions over detectors (e.g.
  `T1 and T2`)
- conditional probabilities between two expressions (e.g. `D1|T1*T2`), again
  in both geometric and fired modes, with binomial uncertainties

## Non-goals

The engine is intentionally simple. It does not simulate energy loss,
material interactions, multiple scattering, secondaries, pileup, or timing
requirements. It is not GEANT4, and nothing in this codebase should grow
toward being GEANT4 without an explicit decision to change scope.

## Intended use

Estimating trigger rates and conditional detector efficiencies for small
cosmic-ray stands (scintillator telescopes, RPC gap efficiency setups, etc.)
from a geometry + logic description, before or instead of building/running
the physical stand.

## Operating modes

- **Headless CLI**: loads a config, runs the simulation, prints rate/logic/
  conditional-probability tables to stdout. No GUI dependency needed for
  this mode.
- **Optional GUI** (PyVista): `--geometry-only` shows a static rotatable 3D
  view of the detector stack without running the simulation;
  `--event-display` runs the simulation once and then steps through
  geometrically relevant tracks, colored by their fired-mode outcome.

## Known extensibility gap (current-state fact, not a promise)

The engine already has an `AngularModel` abstract base class in
`angular.py`, plus an unused `TabulatedAngularModel` implementation built for
arbitrary zenith-angle weight functions. `config.py` currently hard-rejects
any `angular_model.type` other than `"cos2"`, so this pluggable-model path
exists at the Python level but is not yet exposed through YAML. Treat this as
a fact about the current codebase, not a commitment — see
`docs/human/plan_engine.md` for the original design intent.
