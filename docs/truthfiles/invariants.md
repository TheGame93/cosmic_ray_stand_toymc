# Invariants

> Maintained per the documentation contract in AGENT.md — update this file
> when the change you're making alters what's described here.

Hard rules the codebase currently enforces, organized by module. This
describes current state only — no aspirational content. If a rule listed
here stops being true, either the code has a bug or this file is stale;
figure out which before proceeding.

## Config (`config.py`)

- `source_model.type` is a required, discriminated union: `"cosmic"`,
  `"beam"`, or `"object"`; anything else raises `ConfigError`. Exactly one
  source is active per run — there is no multi-source config shape.
  - `cosmic` → `CosmicSourceConfig`: `theta_max_deg` must satisfy
    `0 < theta_max_deg < 90` (strict both ends), converted to radians
    (`theta_max`) at load time; `model` only accepts `"cos2"`;
    `flux_hz_per_cm2` must be `> 0`.
  - `beam` → `BeamSourceConfig`: `profile` must be `"uniform"`,
    `"gaussian"`, or `"divergence"`; `center` is a 2-element `(xc, yc)`
    list; `size` length must match the profile (`uniform`: 1,
    `gaussian`: 2) with all components `> 0` — **except** `divergence`,
    whose `size` is accepted unvalidated (format is not yet defined; see
    Source below for where this actually fails); `flux_hz_per_cm2` must be
    `> 0`.
  - `object` → `ObjectSourceConfig`: `shape` must be `"sphere"`, `"disk"`,
    or `"box"`; `center` is a 3-element `(xc, yc, zc)` list; `size` length
    must match the shape (`sphere`: 1, `disk`: 2, `box`: 3) with all
    components `> 0`; `activity_hz` must be `> 0`.
- `monte_carlo.n_events` must be a positive int (`bool` values are explicitly
  rejected, since `bool` is a subclass of `int` in Python).
- `detectors` must be a non-empty list; each needs a non-empty, unique
  `name`; construction delegates to `Detector` (see Geometry below) and
  wraps any `ValueError` into `ConfigError`.
- `logic.expressions` and `logic.conditional` entries are validated by
  parsing through `logic.extract_names` and rejecting references to unknown
  detector names, at load time (before any simulation runs).
- Conditional entries must **not** define `mode` — both `fired` and
  `geometric` are always reported for every conditional; `mode` is only a
  runtime parameter inside `rates.conditional_probability`, never a config
  field.
- `seed`: optional int or `null`. `null` means "resolve from local time at
  runtime" — the actual resolution happens in `simulation.py`, not here.
- `output.detector_rate_decimals` / `output.logic_rate_decimals` default to
  `1`, must be non-negative ints.
- The `gui:` section is preserved as an opaque `dict[str, Any] | None` — no
  validation happens in `config.py`; that's deferred to `gui/config.py`.

## Geometry (`geometry.py`)

- Detectors are axis-aligned boxes: `center` ± `size/2`, Cartesian `(x, y, z)`.
- `size` components must be strictly positive; `efficiency` must be in
  `[0, 1]` inclusive; `name` must be non-empty. Inputs are coerced to
  `np.float64` arrays.
- Crossing (`intersect`) is a **strictly interior** slab-method ray/AABB
  test: surface-only, edge-only, and corner-only touches are explicitly
  excluded, not counted as a crossing.
- `generation_region` enlarges the detector bounding box by
  `margin = vertical_extent * tan(theta_max)` on all four x/y sides,
  independent of any logic expression. Only used by `CosmicSourceModel`.
- `reference_z` is the highest detector's top z bound (the cosmic source's
  downward-origin plane); `min_reference_z` is the lowest detector's bottom
  z bound (the beam source's upstream-origin plane). Every cosmic/beam
  track originates from one of these two flat planes, regardless of
  individual detector heights.

## Angular (`angular.py`)

- `sample_theta` always returns radians over `[0, theta_max]`.
- `theta_max` must satisfy `0 < theta_max < pi/2` (strict both ends).
- `Cos2AngularModel` implements the closed-form inverse-CDF for density
  `cos^2(theta)`; it's the only model reachable from config today, wired up
  through `CosmicSourceModel`.
- `TabulatedAngularModel` (`grid_size >= 3`, non-negative weights, positive
  normalization) exists but is not wired to config — see
  `docs/truthfiles/goal.md`.

## Tracks (`tracks.py`)

- `Tracks` is a pure container: `origins`/`directions` must both be 2D
  arrays with shape `(n_events, 3)` and matching event counts. No
  generation logic lives here — see Source below.

## Source (`source.py`)

- `SourceModel.generate` requires `count > 0`.
- **`CosmicSourceModel`**: origin `(x, y)` uniform over `generation_region`,
  `z` fixed at `reference_z`; direction `direction_z = -cos(theta)` with
  `theta` from the configured `Cos2AngularModel` and `phi` uniform over
  `[0, 2*pi)` — tracks point **downward** (negative z), unchanged from the
  engine's original single-source behavior. `total_rate_hz = flux_hz_per_cm2
  * area_gen`.
- **`BeamSourceModel`**: origin `z` fixed at `min_reference_z` (upstream
  face); direction is exactly `(0, 0, +1)` for every event (no angular
  spread) — the beam travels `-z -> +z`, opposite the cosmic source's
  downward convention. Transverse `(x, y)`:
  - `uniform`: sampled uniformly inside the disk of diameter `size[0]`
    centered at `center`; `total_rate_hz = flux_hz_per_cm2 * pi *
    (size[0]/2)**2`.
  - `gaussian`: `x`/`y` sampled independently from
    `Normal(center, size/_FWHM_TO_SIGMA)` (`_FWHM_TO_SIGMA =
    2*sqrt(2*ln 2)`); `total_rate_hz = flux_hz_per_cm2 * pi *
    (size[0]/2) * (size[1]/2)` (the FWHM-ellipse area, matching
    `flux_hz_per_cm2`'s "average over the FWHM ellipse" definition).
  - `divergence`: constructing `BeamSourceModel` with this profile always
    raises `NotImplementedError` — `config.py` accepts the YAML key, but no
    model exists yet.
- **`ObjectSourceModel`**: origin sampled uniformly inside the configured
  volume (`sphere`: closed-form `r = R*u**(1/3)` with an isotropic unit
  vector; `disk`: uniform in a cylinder, `r = R*sqrt(u)` in-plane and
  uniform along `z`; `box`: independent uniforms per axis, no rejection
  sampling anywhere). Direction is isotropic over the full 4*pi sphere
  (`cos(theta) ~ U(-1,1)`, `phi ~ U(0, 2*pi)`), not just a downward
  hemisphere. `total_rate_hz = activity_hz` directly, independent of
  detector geometry. No collimation exists yet.
- `build_source_model` dispatches on the config dataclass's Python type
  (`CosmicSourceConfig` / `BeamSourceConfig` / `ObjectSourceConfig`) via
  `isinstance`.
- `SourceModel.spatial_bounds` returns each source's own axis-aligned
  footprint, independent of the detector stack; it exists purely for the
  GUI's display-box sizing (see GUI cross-cutting below) and is not used by
  `simulation.py`.

## Response (`response.py`)

- `fired = crossed & (uniform_draw < efficiency)` — a detector can only fire
  if it was also geometrically crossed. This is the concrete definition of
  the geometric/fired distinction used everywhere else in the codebase:
  end-to-end, `fired <= crossed` always holds per detector per event.

## Logic (`logic.py`)

- Expressions are parsed via Python's `ast` module in `eval` mode — a single
  expression only, no statements.
- Allowed AST nodes are an explicit whitelist: `ast.Name` (detector names),
  `ast.BoolOp` with `And`/`Or` only, `ast.UnaryOp` with `Not` only. Anything
  else (comparisons, arithmetic, calls, literals) raises `ValueError`.
- Every `Name` referenced must exist in the evaluation `context`, else
  `ValueError: Unknown detector name...` — `config.py` pre-checks this at
  load time so it's normally caught before simulation runs.

## Rates (`rates.py`)

- `binomial_rate`: `n_total` must be `> 0`; returned rate is
  `value = total_rate_hz * (n_pass / n_total)`, unit Hz, with a
  binomial-propagated error. `total_rate_hz` is the source's total physical
  event rate (`SimulationResult.total_rate_hz`, computed once via
  `SourceModel.total_rate_hz`) — a single number for every source type,
  replacing the old cosmic-specific `flux_hz_per_cm2 * area_cm2` split.
- `binomial_probability`: `n_cond >= 0`, `n_joint >= 0`,
  `n_joint <= n_cond`; if `n_cond == 0` it returns `nan`/`nan` rather than
  raising (explicit divide-by-zero guard).
- `detector_rates` and `logic_rates` always compute **both** `"geometric"`
  (from `simulation_result.crossed`) and `"fired"` (from
  `simulation_result.fired`) — this pair is the concrete geometric/fired
  duality reported throughout the CLI and GUI.
- `conditional_probability`'s `mode` parameter (`"fired"` or `"geometric"`,
  default `"fired"`) is the one place mode is a runtime choice — `cli.py`
  calls it twice, once per mode, to report both.

## Simulation (`simulation.py`)

- `seed = config.seed if config.seed is not None else int(time.time()*1000)`
  — a `null`/omitted seed makes the run non-deterministic; an explicit int
  seed makes it fully reproducible via `np.random.default_rng(seed)`. The
  *resolved* seed is always a concrete int on `SimulationResult.seed`.
- Events are processed in `PROGRESS_UPDATE_INTERVAL` (1,000,000) chunks so
  large `n_events` runs can report progress; chunks are concatenated back
  into full arrays at the end regardless (chunking is for progress
  reporting, not memory streaming).
- `build_source_model(config.source_model)` builds the model once per run;
  `SimulationResult.total_rate_hz` is computed once via
  `source_model.total_rate_hz(config.detectors)` after all chunks are done.
- `SimulationResult.crossed` / `.fired` are `dict[str, np.ndarray]` keyed by
  detector name — the same naming scheme used by logic expressions and the
  GUI.

## CLI (`cli.py`)

- `--geometry-only` and `--event-display` are mutually exclusive and both
  require `--gui`; `--gui` alone (no submode) is also rejected. Enforced via
  `argparse.error` (nonzero exit), not an exception.
- The headless summary always prints, even in `--event-display` GUI mode —
  only `--geometry-only` skips running the simulation entirely.
- Rate formatting uses `config.output.detector_rate_decimals` /
  `logic_rate_decimals`; probability formatting is hard-coded to 3 decimals
  and prints the literal text `"nan"` when the value is `NaN`.

## GUI cross-cutting

- **Relevance rule**: an event/track is "relevant" iff its conditional
  `given` expression is true **geometrically** (evaluated on `crossed`, not
  `fired`) for at least one configured conditional.
- `show_event_display` raises `ValueError` if `config.conditionals` is empty,
  or if no relevant tracks are found — both are explicit, user-readable
  failures, not silent no-ops.
- Navigation order is nested `(event, conditional)`: if one track is
  relevant to more than one conditional, the GUI cycles through those
  conditionals before advancing to the next relevant event.
- **Three-state color/name mapping**, evaluated in fired mode:
  - `given=False` → `"geometric-only"`, color = `track_color_geometric_only`
  - `given=True, numerator=False` → `"fired-given-only"`, color =
    `track_color_fired_given_only`
  - `given=True, numerator=True` → `"fired-joint"`, color =
    `track_color_fired_joint`
- **Keyboard contract**: `Right` = next state, `Left` = previous state,
  `q` or `Escape` = close.
- **Detector color contract** (per detector, per current event):
  `crossed and fired` → green; `crossed and not fired` → red; not crossed →
  falls through to the configured base color.
- **Detector opacity contract**: detectors referenced by the active
  conditional's `given`/`numerator` get opacity `0.35`; all others are
  dimmed to `0.05`.
- `gui.detector_colors` keys must reference real detector names, else
  `ValueError`. `gui.line_width` must be numeric (not bool) and `> 0.0`.
  Colors accepted: non-empty string (named color or hex), or a 3-element
  numeric tuple/list.
- **Startup camera up vector**: `startup_view_up` returns `(1, 0, 0)`
  (`x`-up) for `source_model.type: beam`, else the default `(0, 0, 1)`
  (`z`-up). Applies to both `--geometry-only` and `--event-display`.
- **Object source rendering**: `render_source_shape` draws exactly one mesh
  (sphere/cylinder/box matching `shape`) for `source_model.type: object`,
  colored by `gui.source_color` (default `orange`) and `gui.source_opacity`
  (default `0.25`, must be in `[0, 1]`); a no-op for `cosmic`/`beam`. Drawn
  once in `build_plotter`, not redrawn per event.
- **Display-box padding**: `compute_display_bounds` pads every axis of the
  detector-bounds ∪ source-`spatial_bounds` union by 10% of that axis's own
  span or magnitude (whichever is larger) — the same formula on all three
  axes, for every source type.

## Documented current-state discrepancies (facts, not bugs to fix here)

- `requirements.txt` installs `pyvista` unconditionally, even though the
  runtime code path treats it as optional/lazy (`_require_pyvista()` guards
  in `gui/scene.py` and `gui/viewer.py`, both raising a friendly
  `RuntimeError` if it's missing). The installed environment always has it;
  the *code* just doesn't require it to import.
- Python 3.12 is declared only via a badge in `README.md` — there's no
  `pyproject.toml`/`setup.cfg`/`python_requires` pin enforcing it mechanically.
