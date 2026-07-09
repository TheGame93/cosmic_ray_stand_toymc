# toyMC_cosmic - engine implementation plan

## Summary

This plan covers only the standalone Monte Carlo engine described in
[desiderata.md](/home/matteo/programmi/toyMC_cosmic/docs/desiderata.md).
The deliverable is a reusable Python package plus a terminal-only CLI runner.
No GUI code, `pyvista` dependency, viewer logic, or visual CLI flags belong in
this phase.

Locked architectural rule:

- The engine must be complete and usable on its own.
- The future GUI must consume engine APIs and engine results only.
- Engine code must not contain visualization-specific behavior.

## Package layout

```text
toyMC_cosmic/
├── docs/
│   ├── desiderata.md
│   ├── plan.md
│   ├── plan_engine.md
│   └── plan_GUI.md
├── pyproject.toml
├── configs/
│   └── example.yaml
├── scripts/
│   └── run_toymc.py
├── src/toymc_cosmic/
│   ├── __init__.py
│   ├── geometry.py
│   ├── angular.py
│   ├── tracks.py
│   ├── response.py
│   ├── logic.py
│   ├── rates.py
│   ├── config.py
│   ├── simulation.py
│   └── cli.py
└── tests/
    ├── conftest.py
    ├── test_geometry.py
    ├── test_angular.py
    ├── test_config.py
    ├── test_tracks.py
    ├── test_response.py
    ├── test_logic.py
    ├── test_rates.py
    └── test_simulation.py
```

Core dependencies for this phase:

- `numpy`
- `pyyaml`

No GUI dependency is part of this plan.

## Public API and data ownership

The engine public surface should be stable enough for the future GUI to consume
without re-running physics or reimplementing logic.

### Core types

```python
@dataclass(frozen=True)
class Detector:
    name: str
    center: np.ndarray
    size: np.ndarray
    efficiency: float
```

`Detector` contains only physical information. It must not own color, material,
or any visualization field.

```python
@dataclass
class Tracks:
    origins: np.ndarray
    directions: np.ndarray
```

```python
@dataclass
class SimulationResult:
    tracks: Tracks
    crossed: dict[str, np.ndarray]
    fired: dict[str, np.ndarray]
    detectors: list[Detector]
    area_gen: float
    flux: float
    theta_max: float
    seed: int
    n_events: int
```

`SimulationResult` must expose enough information for a later event display:

- generated tracks
- per-detector geometric crossing booleans
- per-detector fired booleans
- detector definitions
- generation area
- flux
- `theta_max`
- resolved seed
- event count

### Engine entry points

- `load_config(path) -> Config`
- `run_simulation(config) -> SimulationResult`
- logic evaluators for boolean detector expressions
- rate and conditional-probability helpers
- a terminal CLI that loads YAML, runs the simulation, and prints results

## Physics and Monte Carlo design

The physics decisions from the original full plan remain unchanged in the
engine split unless they were GUI-coupled.

### Coordinate conventions

- `z` is vertical.
- Cosmic rays travel from `+z` toward `-z`.
- `phi` is uniform in `[0, 2*pi)`.
- `theta` is measured from the vertical downward direction.
- First version uses `theta_max = 80 deg`.

### Geometry and strict crossing rule

Each detector is an axis-aligned box with center `(x, y, z)`, size
`(dx, dy, dz)`, and efficiency in `[0, 1]`.

Crossing is determined with a vectorized slab-based ray/AABB intersection:

- compute `t_enter` and `t_exit` from the detector slabs
- a detector is crossed only if `t_enter < t_exit` and `t_exit > 0`
- the strict inequality is required so a surface-only, edge-only, or
  corner-only touch does not count as a crossing

Use the highest detector top face as the reference `z` plane for track origins.

### Generation region

The generation region must not depend on the logic expression under study.
Build it from geometry only:

- take the global detector bounding box in `x` and `y`
- compute total vertical extent `H`
- expand the box by `H * tan(theta_max)`
- sample `x0, y0` uniformly in that rectangle

This keeps the sampling unbiased with respect to any detector logic expression.

### Angular model and flux normalization

Use a pluggable angular-model interface. The first implementation is `cos^2`,
but the code structure must allow replacement later.

Sample directions from the normalized physical shape over the simulated cone:

- `h(theta) = g(theta) * cos(theta) * sin(theta)`
- for the default model, `g(theta) = cos^2(theta)`
- sample only over `theta in [0, theta_max]`

Flux interpretation for this project:

- input `flux_hz_per_cm2` is the total downward flux integrated over the same
  simulated cone `[0, theta_max]`
- if tracks are sampled directly from the normalized physical angular density,
  each event carries equal weight
- rates can therefore be estimated from plain binomial fractions

For any observable `O`:

```text
R_O = flux * A_gen * (N_O / N_gen)
sigma(R_O) = flux * A_gen * sqrt(p * (1 - p) / N_gen)
```

with `p = N_O / N_gen`.

Conditional probabilities are dimensionless and use the standard binomial
uncertainty on `N_joint / N_cond`.

### Detector response

After a geometric crossing, each detector fires independently with a Bernoulli
draw using its efficiency.

The engine API must keep geometric crossing and fired response explicitly
separate in both the data model and the reported results.

## Module responsibilities

### `geometry.py`

- `Detector`
- detector bounds helpers
- global bounding box and vertical extent
- generation-region calculation
- reference `z` calculation
- vectorized detector-crossing computation

### `angular.py`

- angular model interface
- default `cos^2` implementation with direct inverse-CDF sampling
- small generic fallback for future tabulated angular models

### `tracks.py`

- generation of event origins and directions
- unit-vector construction from sampled `theta` and `phi`

### `response.py`

- Bernoulli detector response from crossing booleans and efficiencies

### `logic.py`

- safe AST-based evaluation of expressions such as `T1 and T2 and not D1`
- allow only detector names plus boolean `and`, `or`, `not`
- reject calls, arithmetic, comparisons, or other Python syntax

### `rates.py`

- rate estimate container
- probability estimate container
- single-detector geometric and fired rates
- logic-expression rates in geometric and fired mode
- conditional probabilities in geometric or fired mode

### `config.py`

- YAML loading with `yaml.safe_load`
- validation of detector definitions and Monte Carlo settings
- duplicate detector-name checks
- detector size and efficiency checks
- `theta_max` and event-count checks
- logic-reference validation against detector names
- optional `gui:` section accepted but not used by the engine runtime

The engine may either ignore `gui:` content after parsing or preserve it as
opaque config data, but the engine must not depend on it for validation of
physics behavior or for normal execution.

### `simulation.py`

- orchestration entry point for geometry, track generation, response, and
  result packaging
- no printing, no plotting, no GUI branches

### `cli.py`

- terminal-only entry point
- parse config path
- run the simulation
- print detector rates, logic rates, conditional probabilities, generation
  area, event count, and resolved seed

No `--gui` or `--event-display` flag belongs in this phase.

## YAML schema for the engine phase

Use one YAML format for the whole project. In the engine phase, the core schema
must include:

```yaml
seed: null
theta_max_deg: 80.0

angular_model:
  type: cos2

flux_hz_per_cm2: 1.0e-2

monte_carlo:
  n_events: 100000

detectors:
  - name: T1
    center: [0.0, 0.0, 100.0]
    size: [20.0, 20.0, 1.0]
    efficiency: 0.98

logic:
  expressions:
    - "T1 and T2 and D1"
  conditional:
    - name: "P(D1 fires | T1 and T2 fire)"
      numerator: "D1"
      given: "T1 and T2"
      mode: fired

gui:
  background_color: black
```

In this phase:

- everything outside `gui:` is engine-owned
- `gui:` is optional
- `gui:` must not be required for headless execution

## Implementation order

1. Create package scaffolding, `pyproject.toml`, `configs/example.yaml`, and
   the thin `scripts/run_toymc.py` wrapper.
2. Implement `geometry.py` and unit tests for hit, miss, and tangent cases.
3. Implement `angular.py` and tests for sampling correctness and normalization.
4. Implement `config.py` and validation tests, including duplicate-name and
   bad-parameter failures.
5. Implement `tracks.py` and tests for bounds, downward direction, and unit
   vectors.
6. Implement `response.py` and tests for efficiency edge cases and statistical
   behavior.
7. Implement `logic.py` and tests for valid expressions and rejected syntax.
8. Implement `rates.py` and tests for hand-checkable small examples and
   uncertainty formulas.
9. Implement `simulation.py` and integration tests over a small detector setup.
10. Implement the terminal CLI and a manual smoke run using `configs/example.yaml`.
11. Run the full engine test suite and confirm the project is fully usable
    without any GUI package installed.

## Test plan

Unit and integration coverage in this phase must demonstrate a complete
headless workflow.

Required tests:

- geometry intersection correctness, including strict exclusion of zero-length
  surface touches
- angular sampling sanity against the expected truncated distribution
- YAML config loading and validation failure paths
- track generation inside the derived generation region
- detector response behavior for efficiencies `0`, `1`, and a statistical
  intermediate value
- safe logic parsing and evaluation for geometric and fired contexts
- rate and conditional-probability formulas
- end-to-end simulation sanity:
  - `fired <= crossed` for every detector
  - `rate(A and B) <= rate(A)`
  - probabilities stay in `[0, 1]` when conditioning is defined

Manual verification:

- `python scripts/run_toymc.py configs/example.yaml`
- inspect the printed seed, event count, detector rates, logic rates, and
  conditional probabilities

Completion criterion for this plan:

- the package, tests, and CLI all work in a headless environment
- no GUI dependency is needed
- the resulting `SimulationResult` is rich enough for the later GUI plan

## Assumptions and defaults

- The engine CLI is part of the engine deliverable.
- `numpy` and `pyyaml` are the only runtime dependencies in this phase.
- GUI-specific settings remain isolated under an optional top-level `gui:` key.
- The future GUI is expected to consume `Config` and `SimulationResult` only.
