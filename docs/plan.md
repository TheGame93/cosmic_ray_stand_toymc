# toyMC_cosmic — full build plan

## Context

The repo currently contains only `docs/desiderata.md`. Nothing else exists — this is a from-scratch build of the entire library, CLI runner, and GUI described there, plus the newly-added GUI/event-display requirements. Decisions already locked in with the user: GUI library = **PyVista**; event display = **interactive step-through** (one event at a time, via slider + arrow keys); flux is normalized over the simulated cone `[0, theta_max]` only (see §2.3).

Environment: Python 3.12.3. Installed: `numpy 1.26.4`, `PyYAML 6.0.1`. Not installed: `pytest`, `pyvista` (and its VTK dependency). No `matplotlib`/`scipy` needed — the design below avoids them to keep the dependency footprint small.

---

## 1. Package layout

```
toyMC_cosmic/
├── docs/desiderata.md              (exists)
├── docs/plan.md                    (this file)
├── pyproject.toml                  # setuptools, src layout, package "toymc_cosmic"
├── configs/
│   └── example.yaml                # 3-detector demo config
├── scripts/
│   └── run_toymc.py                # thin entry point -> cli.main()
├── src/toymc_cosmic/
│   ├── __init__.py
│   ├── geometry.py                 # Detector, AABB ray intersection, bounding box/margin
│   ├── angular.py                  # pluggable angular model(s)
│   ├── tracks.py                   # track/event generation
│   ├── response.py                 # Bernoulli detector firing
│   ├── logic.py                    # safe ast-based boolean expression evaluator
│   ├── rates.py                    # rate & uncertainty estimators
│   ├── config.py                   # YAML loading -> dataclasses, validation
│   ├── simulation.py                # orchestrates geometry+tracks+response -> SimulationResult
│   ├── cli.py                       # argparse runner, prints results table
│   └── gui/
│       ├── __init__.py
│       ├── scene.py                 # static PyVista scene (detectors, colors, rotation is free)
│       └── viewer.py                # interactive event step-through (slider + keys)
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

`pyproject.toml` dependencies: `numpy`, `pyyaml` (core); `pyvista` as an optional extra (`project.optional-dependencies.gui`) so the core library + tests never require VTK/a display; `pytest` as a dev extra.

---

## 2. Physics design (the part that needs to be right)

### 2.1 Ray / AABB intersection with strict non-zero path length

Track origin `o=(x0,y0,z_ref)`, direction `d=(sin θ cos φ, sin θ sin φ, −cos θ)` (unit vector, downward since θ is measured from vertical-downward).

Slab method per detector, per axis `i ∈ {x,y,z}` with bounds `[lo_i, hi_i]`:
- if `d_i ≠ 0`: `t1=(lo_i−o_i)/d_i`, `t2=(hi_i−o_i)/d_i`; `tmin_i=min(t1,t2)`, `tmax_i=max(t1,t2)`
- if `d_i = 0`: no constraint from this axis unless `o_i` is already outside `[lo_i,hi_i]` (then never crosses)

`t_enter = max_i(tmin_i)`, `t_exit = min_i(tmax_i)`.

**Crossing iff `t_enter < t_exit` (strict) and `t_exit > 0`.** The strict `<` is exactly what excludes a tangent/edge/corner-only touch (that case gives `t_enter == t_exit` mathematically). No epsilon is needed: with continuous random `x0,y0,θ,φ`, landing exactly on a boundary has probability zero, so float equality edge cases don't need special-casing — they're correctly excluded by the strict comparison as-is.

Fully vectorizable: broadcast `(n_events, 1, 3)` track arrays against `(1, n_detectors, 3)` detector bound arrays → `(n_events, n_detectors)` boolean crossing matrix in a handful of numpy ops, no Python loops.

Reference plane: `z_ref = max over detectors of (z_center + dz/2)` (top of the highest detector). All valid crossings then have `t ≥ 0` automatically. No artificial epsilon buffer needed above it.

### 2.2 Generation region (bias-free, per desiderata)

- Horizontal bounding box of all detectors: `[xmin,xmax] × [ymin,ymax]`.
- Total vertical extent `H = max(z_center+dz/2) − min(z_center−dz/2)` over all detectors.
- Margin `= H · tan(θ_max)` (the max horizontal distance a maximally-inclined track can travel while crossing the full vertical extent).
- Generation rectangle: `[xmin−margin, xmax+margin] × [ymin−margin, ymax+margin]`, area `A_gen` (cm²).
- `x0, y0 ~ Uniform` over that rectangle; independent of any logic expression — satisfies the no-bias requirement directly.

### 2.3 Flux normalization — the key derivation

Input `Φ` [Hz/cm²] is defined as the *total* downward flux through a horizontal surface. Design decision (confirmed with the user): **`Φ` is taken to be integrated over exactly the simulated angular domain `θ∈[0,θ_max]`, not the full 0–90° hemisphere.** This is consistent with `θ_max` being chosen "large enough to guarantee statistical coverage" — angles beyond it are defined to be outside the problem, not a missing tail.

Standard cosmic-ray geometry: intensity `I(θ) = I0·g(θ)` (g(θ)=cos²θ for v1), and the rate crossing a horizontal area `dA` from solid angle `dΩ=sinθ dθ dφ` is `dR = I(θ)·cosθ·dA·dΩ` (the extra `cosθ` is the projection of the horizontal area toward the incoming direction). So the physical *shape* of the rate density in θ is:

```
h(θ) = g(θ) · cosθ · sinθ            (for cos² model: h(θ) = cos³θ·sinθ)
```

**Key trick:** sample θ directly from the normalized shape `f(θ) = h(θ) / ∫₀^θmax h(θ') dθ'`. Because the sampling density already matches the physical rate-density shape, each generated track carries *equal* physical weight — no importance-sampling weights needed anywhere downstream. This makes every rate estimator a plain unweighted binomial fraction:

```
R_O = Φ · A_gen · (N_O / N_gen)
σ(R_O) = Φ · A_gen · sqrt(p·(1−p) / N_gen),   p = N_O/N_gen
```

for any observable `O` (single-detector geometric crossing, single-detector fired, or a logic expression evaluated in geometric or fired mode). `N_theta` (the normalization integral of `h`) never needs to be computed — it cancels out entirely because we only ever need *fractions* of generated events, and generation itself already encodes the physical shape.

Closed-form inverse-CDF for the cos² model (so sampling is exact, vectorized, no rejection sampling):

```
CDF: F(θ) = (1 − cos⁴θ) / (1 − cos⁴θmax)
Invert:  θ = arccos( [1 − U·(1 − cos⁴θmax)]^(1/4) ),   U ~ Uniform[0,1)
```

`φ ~ Uniform[0, 2π)` independently.

Conditional probabilities (e.g. `P(D1 fires | T1 and T2 fire)`) are plain binomial fractions with **no Φ·A_gen factor** (they're dimensionless probabilities, not rates):

```
p_hat = N_joint / N_cond,   σ = sqrt(p_hat·(1−p_hat) / N_cond)
```

(If `N_cond == 0`, return `nan` and log a warning rather than dividing by zero.)

### 2.4 Pluggable angular model

```python
class AngularModel(ABC):
    @abstractmethod
    def sample_theta(self, n: int, theta_max: float, rng: np.random.Generator) -> np.ndarray:
        """theta samples ~ g(theta)*cos(theta)*sin(theta), truncated to [0, theta_max]."""
```

- `Cos2AngularModel` (default): closed-form inverse-CDF above.
- A small generic fallback, `TabulatedAngularModel(g_theta_func)`, built from a fine grid + `np.cumsum` (trapezoidal) + `np.interp` for inverse-CDF lookup — gives future angular models a drop-in path without needing scipy. Include it since it's ~15 lines and directly satisfies "structured so the angular distribution can be replaced easily later," but don't build more than this — no plugin registry, no config-driven arbitrary functions (out of scope).

---

## 3. Module-by-module design

**`geometry.py`**
```python
@dataclass(frozen=True)
class Detector:
    name: str
    center: np.ndarray   # (3,)
    size: np.ndarray     # (3,) dx,dy,dz
    efficiency: float
    color: str = "grey"

    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]: ...  # (lo, hi)

def bounding_box(detectors: list[Detector]) -> tuple[float,float,float,float]: ...  # xmin,xmax,ymin,ymax
def vertical_extent(detectors: list[Detector]) -> float: ...  # H
def generation_region(detectors, theta_max) -> tuple[float,float,float,float,float]: ...  # x0,x1,y0,y1,area
def reference_z(detectors: list[Detector]) -> float: ...
def intersect(origins: np.ndarray, directions: np.ndarray, detectors: list[Detector]) -> np.ndarray:
    """origins,directions: (n,3). Returns bool (n, n_detectors) crossed matrix, vectorized slab method."""
```

**`angular.py`**: `AngularModel` ABC, `Cos2AngularModel`, `TabulatedAngularModel` as above.

**`tracks.py`**
```python
@dataclass
class Tracks:
    origins: np.ndarray     # (n,3)
    directions: np.ndarray  # (n,3) unit vectors

def generate_tracks(n, detectors, theta_max, angular_model, rng) -> Tracks: ...
```
Uses `geometry.generation_region`/`reference_z` for x0,y0,z_ref and `angular_model.sample_theta` for θ; builds direction vectors from θ,φ.

**`response.py`**
```python
def apply_response(crossed: np.ndarray, efficiencies: np.ndarray, rng) -> np.ndarray:
    """crossed, efficiencies broadcast to (n, n_detectors); returns fired bool matrix."""
```
`fired = crossed & (rng.uniform(size=crossed.shape) < efficiencies)`.

**`logic.py`**
```python
def evaluate(expr: str, context: dict[str, np.ndarray]) -> np.ndarray:
    """Parses expr via ast.parse(expr, mode='eval'); only Name/BoolOp(And/Or)/UnaryOp(Not) allowed.
    Unknown names or disallowed node types raise ValueError with a clear message."""
```
Recursive walk: `Name→context[id]`, `UnaryOp(Not)→~value`, `BoolOp(And)→np.logical_and.reduce`, `BoolOp(Or)→np.logical_or.reduce`. Anything else (Compare, Call, BinOp, Constant, …) raises. This one function is reused for both geometric and fired evaluation — callers just pass a different `context` dict (`crossed` vs `fired`); the geometric/fired separation lives in `rates.py`, not here.

**`rates.py`**
```python
@dataclass
class Rate:      value: float; error: float; n_pass: int; n_total: int
@dataclass
class Probability: value: float; error: float; n_joint: int; n_cond: int

def binomial_rate(n_pass, n_total, flux, area) -> Rate: ...
def binomial_probability(n_joint, n_cond) -> Probability: ...  # nan if n_cond==0

def detector_rates(sim: SimulationResult) -> dict[str, dict[str, Rate]]:
    """{name: {"geometric": Rate, "fired": Rate}}"""
def logic_rates(expr: str, sim: SimulationResult) -> dict[str, Rate]:
    """{"geometric": Rate, "fired": Rate} — evaluates `expr` against sim.crossed and sim.fired separately."""
def conditional_probability(numerator_expr, given_expr, sim, mode="fired") -> Probability:
    """mode selects whether both expr are evaluated against sim.crossed or sim.fired."""
```

**`config.py`**: dataclasses `DetectorConfig, AngularModelConfig, MonteCarloConfig, ConditionalConfig, LogicConfig, GuiConfig, Config`; `load_config(path) -> Config` via `yaml.safe_load` + validation (`ConfigError` on: efficiency∉[0,1], size≤0, duplicate detector names, `0 < theta_max_deg < 90`, `n_events>0`, unknown detector names referenced in logic/conditional expressions). Seed resolution happens here or in `simulation.py`: `seed = config.seed if config.seed is not None else int(time.time()*1000)`; the resolved seed is always printed by the CLI for traceability.

**`simulation.py`**
```python
@dataclass
class SimulationResult:
    tracks: Tracks
    crossed: dict[str, np.ndarray]   # per-detector (n,) bool
    fired: dict[str, np.ndarray]     # per-detector (n,) bool
    detectors: list[Detector]
    area_gen: float
    flux: float
    theta_max: float
    seed: int
    n_events: int

def run_simulation(config: Config) -> SimulationResult:
    """Wires geometry -> tracks -> response into one call. GUI and CLI both consume
    only this object — no physics is ever recomputed in the GUI layer."""
```

**`cli.py`** (+ `scripts/run_toymc.py` thin wrapper): argparse with positional `config` path and flags `--gui` (static rotatable scene) and `--event-display` (interactive step-through viewer; implies/includes the static scene). Default behavior with no flags: run the MC and print the results table. Output is plain aligned f-strings — no new formatting dependency (e.g. `rich`) since it isn't needed.

Example printed output:
```
Seed: 1720440000123
Generated events: 100000  (A_gen = 45000.0 cm^2)

Geometric crossing rates:
  T1: 12.345 +/- 0.056 Hz
  T2: 10.234 +/- 0.051 Hz

Fired rates:
  T1: 12.10 +/- 0.055 Hz
  T2:  9.72 +/- 0.050 Hz

Logic expressions:
  T1 and T2 and D1        geometric: 6.789 +/- 0.041 Hz   fired: 5.432 +/- 0.037 Hz

Conditional probabilities:
  P(D1 fires | T1 and T2 fire) = 0.7891 +/- 0.0123  (n_cond=5432)
```

---

## 4. YAML config schema

```yaml
seed: null                        # null => derive from local time; int => reproducible

theta_max_deg: 80.0

angular_model:
  type: cos2                      # only 'cos2' implemented initially

flux_hz_per_cm2: 1.0e-2

monte_carlo:
  n_events: 100000

detectors:
  - name: T1
    center: [0.0, 0.0, 100.0]
    size: [20.0, 20.0, 1.0]
    efficiency: 0.98
    color: grey                   # optional, GUI only
  - name: T2
    center: [0.0, 0.0, 50.0]
    size: [20.0, 20.0, 1.0]
    efficiency: 0.95
  - name: D1
    center: [0.0, 0.0, 0.0]
    size: [20.0, 20.0, 1.0]
    efficiency: 0.90

logic:
  expressions:                    # each auto-reported as both geometric & fired rate
    - "T1 and T2 and D1"
    - "T1 and T2 and not D1"
  conditional:
    - name: "P(D1 fires | T1 and T2 fire)"
      numerator: "D1"
      given: "T1 and T2"
      mode: fired                 # fired | geometric

gui:
  background_color: black
  default_detector_color: grey
```

---

## 5. GUI design (PyVista)

Hard architectural rule: **GUI modules only ever read a `SimulationResult`/`Config`/`Detector` — they never recompute crossing/firing logic themselves.** This guarantees the visualization can't silently drift from the printed numbers.

**`gui/scene.py`**
```python
def build_plotter(config: Config, detectors: list[Detector]) -> pv.Plotter:
    plotter = pv.Plotter()
    plotter.set_background(config.gui.background_color)      # default 'black'
    for det in detectors:
        box = pv.Cube(center=det.center, x_length=det.size[0], y_length=det.size[1], z_length=det.size[2])
        plotter.add_mesh(box, color=det.color or config.gui.default_detector_color, name=f"detector_{det.name}")
    return plotter
```
Rotation/zoom/pan come for free from PyVista's default trackball-camera interactor — no custom interaction code needed. `plotter.show()` for the static `--gui` mode.

**`gui/viewer.py`** — interactive step-through:
- Reuses `build_plotter`, keeps the `plotter` reference, does not call blocking `show()` yet.
- `show_event(plotter, sim, i)`: builds a `pv.Line(p_start, p_end)` from the track's origin along its direction spanning the full stand height, adds it via `plotter.add_mesh(line, color="white", line_width=3, name="current_track")` (the `name=` kwarg makes PyVista replace the previous actor in place — this is the mechanism used for all per-event updates, no manual actor bookkeeping needed). For each detector: color = `"green"` if `fired[name][i]`, `"red"` if `crossed[name][i] and not fired[name][i]`, else its default/base color; re-`add_mesh` with `name=f"detector_{name}"` to swap the color. Updates an on-screen `plotter.add_text(f"Event {i+1}/{n}", name="event_label")`.
- Interaction: a `plotter.add_slider_widget(callback=lambda v: show_event(plotter, sim, int(v)), rng=[0, n-1], title="Event", fmt="%.0f")` as the primary control (drag to jump to any event), plus `plotter.add_key_event("Right", ...)` / `("Left", ...)` for keyboard stepping (clamped at bounds, not wrapped).
- `show_event(plotter, sim, 0)` then `plotter.show()` (blocking; VTK interactor handles the widget/key callbacks while running).

---

## 6. Implementation order (each step independently testable, GUI deferred to the end)

1. Repo scaffolding: `pyproject.toml`, package skeleton, `configs/example.yaml`.
2. `geometry.py` + tests (hit/miss/tangent-edge cases, vectorized batch correctness).
3. `angular.py` + tests (empirical sampled θ distribution matches the closed-form CDF within tolerance).
4. `config.py` + tests (valid load, each validation error path, seed default-from-time behavior).
5. `tracks.py` + tests (generated points within bounds, unit-length directions, correct sign convention).
6. `response.py` + tests (efficiency=0 → never fires, efficiency=1 → always fires when crossed, efficiency=0.5 → statistical check).
7. `logic.py` + tests (valid expressions evaluate correctly; disallowed syntax like `T1 == T2`, `T1()`, `T1 + 1` raises).
8. `rates.py` + tests (hand-computed small cases vs function output, error formula check, `n_cond=0` → nan).
9. `simulation.py` + integration test (small 2–3 detector config; sanity checks: `fired ≤ geometric` per detector, `rate(A and B) ≤ rate(A)`, conditional probability in [0,1]).
10. `cli.py` + `scripts/run_toymc.py`; manual smoke test against `configs/example.yaml`.
11. Full `pytest` run — this is the checkpoint before any GUI/VTK dependency enters the picture.
12. `gui/scene.py`; manual smoke test: launch, confirm background/detector default colors, mouse-drag rotation.
13. `gui/viewer.py`; manual smoke test: step through events via slider and arrow keys, visually confirm green/red matches the underlying `crossed`/`fired` arrays for a few events.
14. Wire `--gui` / `--event-display` into `cli.py`; final end-to-end pass.

---

## 7. Verification plan

- `pip install -e .[gui,dev]` (dev extra = pytest) once `pyproject.toml` exists.
- `pytest` from repo root → all green, no display/VTK needed for steps 1–11.
- `python scripts/run_toymc.py configs/example.yaml` → printed table; sanity-check fired≤geometric, monotonic AND-logic rates, conditional probability in [0,1].
- `python scripts/run_toymc.py configs/example.yaml --gui` → black background, grey detectors, mouse-rotate works; edit `gui.background_color`/detector `color` in the YAML and rerun to confirm they take effect.
- `python scripts/run_toymc.py configs/example.yaml --event-display` → slider/arrow-key stepping changes the highlighted track and detector colors event-by-event, consistent with the printed rates (same underlying arrays, not recomputed).
