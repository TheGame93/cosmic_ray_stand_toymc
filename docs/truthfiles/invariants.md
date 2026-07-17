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
  - `cosmic` → `CosmicSourceConfig`: `model` only accepts `"cos2"`;
    `flux_hz_per_cm2` must be `> 0` and means the real total downward
    plane flux through a horizontal area, integrated over the full sky
    hemisphere.
  - `beam` → `BeamSourceConfig`: `profile` must be `"uniform"` or
    `"gaussian"` (`"divergence"` is rejected with `ConfigError` — not yet
    implemented, see `docs/truthfiles/goal.md`); `center` is a 2-element
    `(xc, yc)` list; `size` length must match the profile (`uniform`: 1,
    `gaussian`: 2) with all components `> 0`; `flux_hz_per_cm2` must be
    `> 0`.
  - `object` → `ObjectSourceConfig`: `center` is a 3-element
    `(xc, yc, zc)` list; `diameter` must be `> 0`; `normal` is a 3-element
    vector and must not be the zero vector; `angular_model` accepts
    `"uniform"` or `"cosine-weighted"` and hard-rejects
    `"material-dependent"` as not yet implemented; at least one of
    `activity_bq` or `surface_emission_rate_hz` must be present; if
    `yield_per_decay` is provided without `activity_bq`, config loading
    raises `ConfigError`. If `surface_emission_rate_hz` is present, it is
    treated as the authoritative front-side emission rate and overrides the
    derived `0.5 * activity_bq * yield_per_decay`.
- `monte_carlo.n_events` must be a positive int (`bool` values are explicitly
  rejected, since `bool` is a subclass of `int` in Python).
- `detectors` must be a non-empty list; each needs a non-empty, unique
  `name`; construction delegates to `Detector` (see Geometry below) and
  wraps any `ValueError` into `ConfigError`.
  - `center` accepts either a legacy 3-element list or a structured mapping.
    Structured `center` must use exactly one of:
    - `value` + `sigma`
    - `value` + `common_group` + optional `extra_sigma`
    `center.sigma` is mutually exclusive with `common_group` /
    `extra_sigma`; `extra_sigma` without `common_group` raises
    `ConfigError`; unknown keys in structured `center` raise `ConfigError`.
  - `size` accepts either a legacy 3-element list or a structured mapping.
    Structured `size` uses `value` + optional `sigma` only; unknown keys
    raise `ConfigError`.
- `logic.expressions` and `logic.conditional` entries are validated by
  parsing through `logic.extract_names` and rejecting references to unknown
  detector names, at load time (before any simulation runs).
- Conditional entries must **not** define `mode` — both `fired` and
  `geometric` are always reported for every conditional; `mode` is only a
  runtime parameter inside `rates.conditional_probability`, never a config
  field.
- `seed`: optional int or `null`. `null` means "resolve from local time at
  runtime" — the actual resolution happens in `simulation.py`, not here.
- `systematics.geometry`: optional mapping for detector-geometry replicas.
  - `n_replicas` must be a positive int.
  - `seed` is an optional int or `null`.
  - `common_groups` is an optional mapping of named shared center shifts.
    Each group currently supports `center.sigma` only, which must be a
    3-element numeric vector with component-wise non-negative entries.
  - If any detector declares geometry-uncertainty fields but
    `systematics.geometry` is absent, config loading raises `ConfigError`.
  - If `systematics.geometry` is present, `monte_carlo.n_events` must be at
    least `1 + n_replicas`.
  - If `systematics.geometry` is present but there is no effective nonzero
    geometry uncertainty anywhere, config loading raises `ConfigError`.
  - A detector is geometry-variable iff it has a nonzero `center.sigma`,
    nonzero `center.extra_sigma`, nonzero `size.sigma`, or references a
    `common_group` whose shared `center.sigma` has any nonzero component.
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
- `bounding_box_3d` returns the full detector-stack axis-aligned bounds.
- `enclosing_sphere` returns the center of that 3D box together with the
  half-diagonal radius multiplied by a caller-provided padding factor
  (`> 1.0` required). `CosmicSourceModel` uses this to build its finite
  auxiliary generation surface.
- `reference_z` is the highest detector's top z bound; `min_reference_z` is
  the lowest detector's bottom z bound. `BeamSourceModel` uses
  `min_reference_z` as its upstream origin plane, and GUI display bounds
  use both z references for the detector stack extent.

## Angular (`angular.py`)

- `sample_theta` always returns radians over the downward hemisphere
  `[0, pi/2]`, and `count` must be strictly positive.
- `Cos2AngularModel` implements the closed-form inverse-CDF for the
  incoming-direction marginal `p(theta) = 3 cos^2(theta) sin(theta)`,
  corresponding to a sky intensity `I(theta) ∝ cos^2(theta)` seen through
  a horizontal plane. It's the only model reachable from config today,
  wired up through `CosmicSourceModel`.
- `TabulatedAngularModel` (`grid_size >= 3`, non-negative weights, positive
  normalization) exists but is not wired to config — see
  `docs/truthfiles/goal.md`. Its physical hemisphere density is built as
  `weight_function(theta) * sin(theta)`.

## Tracks (`tracks.py`)

- `Tracks` is a pure container: `origins`/`directions` must both be 2D
  arrays with shape `(n_events, 3)` and matching event counts. No
  generation logic lives here — see Source below.

## Source (`source.py`)

- `SourceModel.generate` requires `count > 0`. `CosmicSourceModel` and
  `BeamSourceModel` cache detector-derived geometry on first use
  (enclosing sphere for cosmic, `min_reference_z` for beam) — safe because
  `detectors` never changes across chunks within one `run_simulation`
  call, but means a `SourceModel` instance must not be reused across two
  different detector lists.
- **`CosmicSourceModel`**: `model` must be `"cos2"` (validated again at
  construction time, not just in `config.py`) and is what selects
  `Cos2AngularModel`. Each sampled direction points **downward**
  (`direction_z = -cos(theta)`), with `phi` uniform over `[0, 2*pi)` and
  `theta` from the configured angular model. Origins are sampled on a
  padded enclosing sphere: the code chooses a uniform impact point on the
  disk perpendicular to the direction and back-propagates to the sphere
  entry point. `total_rate_hz = (4/3) * pi * R^2 * flux_hz_per_cm2`, where
  `R` is the padded enclosing-sphere radius.
- **`BeamSourceModel`**: origin `z` fixed at `min_reference_z` (upstream
  face); direction is exactly `(0, 0, +1)` for every event (no angular
  spread) — the beam travels `-z -> +z`, opposite the cosmic source's
  downward convention. `profile` must be `"uniform"` or `"gaussian"`
  (validated again at construction time). Transverse `(x, y)`:
  - `uniform`: sampled uniformly inside the disk of diameter `size[0]`
    centered at `center`; `total_rate_hz = flux_hz_per_cm2 * pi *
    (size[0]/2)**2`.
  - `gaussian`: `x`/`y` sampled from a 2D gaussian with
    `sigma = size/_FWHM_TO_SIGMA` (`_FWHM_TO_SIGMA = 2*sqrt(2*ln 2)`),
    **truncated** via vectorized rejection sampling to the ellipse of
    semi-axes `_GAUSSIAN_TRUNCATION_SIGMA_MULTIPLE * sigma`
    (`_GAUSSIAN_TRUNCATION_SIGMA_MULTIPLE = 5`) — guarantees every sampled
    origin lies within `spatial_bounds`, at a truncated-mass cost of
    `~3.7e-6`, negligible for this engine. `total_rate_hz = 2 *
    flux_hz_per_cm2 * pi * (size[0]/2) * (size[1]/2)`: the FWHM ellipse
    (`_footprint_area`) is exactly `pi * (size[0]/2) * (size[1]/2)`, and
    contains exactly half of an independent 2D gaussian's mass (the
    semi-axis `FWHM/2 = 1.1774*sigma` is the 2D-Rayleigh median radius in
    standardized units), so the total rate over the full population is
    twice `flux_hz_per_cm2` times that ellipse area.
- **`ObjectSourceModel`**: models a one-sided mounted disk only. The
  configured `normal` is normalized internally; origins are sampled
  uniformly on the disk surface with `r = R*sqrt(u)` in a local orthonormal
  basis perpendicular to that normal. Directions are sampled only into the
  forward hemisphere (`direction dot normal > 0`):
  - `uniform`: hemisphere-uniform, `cos(theta) ~ U(0, 1)`.
  - `cosine-weighted`: Lambert-like, `cos(theta) = sqrt(u)`.
  `total_rate_hz` equals the configured front-side emission rate, either
  supplied directly as `surface_emission_rate_hz` or derived from
  `0.5 * activity_bq * yield_per_decay`.
- `build_source_model` dispatches on the config dataclass's Python type
  (`CosmicSourceConfig` / `BeamSourceConfig` / `ObjectSourceConfig`) via
  `isinstance`.
- `SourceModel.spatial_bounds` returns each source's own axis-aligned
  footprint, independent of the detector stack. For every source type this
  is a **true hard bound** on what `generate()` can produce (exact for
  cosmic/uniform-beam/object; truncation-guaranteed for gaussian beam). It
  exists for the GUI's display-box sizing and object-source mesh bounds
  (see GUI cross-cutting below) and is not used by `simulation.py`.

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
- `RateEstimate` and `ProbabilityEstimate` keep `error` as the main public
  uncertainty field, and now also carry `stat_error`, optional
  `syst_error`, and optional `quality_warning`. When no systematic summary is
  attached, `stat_error == error` and `syst_error is None`.
- `detector_rates` and `logic_rates` always compute **both** `"geometric"`
  (from `simulation_result.crossed`) and `"fired"` (from
  `simulation_result.fired`) — this pair is the concrete geometric/fired
  duality reported throughout the CLI and GUI.
- `conditional_probability`'s `mode` parameter (`"fired"` or `"geometric"`,
  default `"fired"`) is the one place mode is a runtime choice — `cli.py`
  calls it twice, once per mode, to report both. All three public helpers can
  optionally attach geometry-systematics summaries, combining
  `stat_error` and `syst_error` in quadrature.

## Simulation (`simulation.py`)

- `resolve_seed(config.seed)` implements the engine's seed rule:
  `config.seed` when explicit, otherwise `int(time.time()*1000)`. A
  `null`/omitted seed makes the run non-deterministic; an explicit int makes
  it fully reproducible via `np.random.default_rng(seed)`. The *resolved*
  seed is always a concrete int on `SimulationResult.seed`.
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

## Geometry systematics (`geometry_systematics.py`)

- `geometry_systematics.py` is an orchestration layer around the fixed-geometry
  engine; it does not change `Detector` or the semantics of
  `run_simulation(config, ...)`.
- `monte_carlo.n_events` is the *global* event budget when geometry
  systematics are enabled:
  - `total_runs = 1 + n_replicas`
  - `replica_events = floor(n_events / total_runs)`
  - `nominal_events = n_events - n_replicas * replica_events`
  The remainder stays on the nominal run.
- Two seed roles are kept separate:
  - Monte Carlo seeds come from the resolved MC seed (`resolve_seed`) and
    deterministic `+ replica_index` offsets for the replicas.
  - Geometry perturbation draws come from `systematics.geometry.seed` when
    explicit, otherwise from a deterministic value derived from the resolved
    MC seed; replica geometry RNGs use deterministic `+ replica_index`
    offsets from that geometry seed.
- Replica detector perturbations are gaussian only.
  - Shared center shifts are sampled once per common group per replica.
  - Local `center.sigma` and `center.extra_sigma` are sampled independently.
  - `size.sigma` samples are resampled until every perturbed size component is
    strictly positive.
- Central values always come from the nominal-geometry run. `syst_error` is
  the replica RMS spread around that nominal value:
  `sqrt(mean((q_k - q_0)^2))`.
- Geometry-systematics summaries are attached only to observables that depend
  on at least one geometry-variable detector:
  - detector rates: only that detector
  - logic rates: any referenced detector in the expression
  - conditional probabilities: any referenced detector in `numerator` or
    `given`
- Sparse-replica warnings appear only when the minimum relevant replica count
  is below `20`:
  - rates / logic rates: `replica_min_n_pass=...`
  - conditional probabilities: `replica_min_n_cond=...`

## CLI (`cli.py`)

- `--geometry-only` and `--event-display` are mutually exclusive and both
  require `--gui`; `--gui` alone (no submode) is also rejected. Enforced via
  `argparse.error` (nonzero exit), not an exception.
- The headless summary always prints, even in `--event-display` GUI mode —
  only `--geometry-only` skips running the simulation entirely.
- When geometry systematics are enabled, `cli.py` runs the nominal result plus
  replicas through `geometry_systematics.py`, prints:
  - the resolved MC seed
  - the resolved geometry seed
  - the configured total event count
  - the nominal event count
  - the replica layout as `N x M events`
  and still sends only the nominal `SimulationResult` to the GUI
  `--event-display` path.
- The second headless-summary line always prints source-specific physical
  normalization text, not a generic source rate:
  - `cosmic` → `cosmic flux = ... Hz/cm2`
  - `beam` → `beam flux = ... Hz/cm2`
  - `object` → `source activity = ... Bq, front emission = ... Hz`
    (or `source activity = n/a` if only `surface_emission_rate_hz` was
    configured)
- Rate formatting uses `config.output.detector_rate_decimals` /
  `logic_rate_decimals`; probability formatting is hard-coded to 3 decimals
  and prints the literal text `"nan"` when the value is `NaN`.
  - Unaffected observables keep the short nominal-only format.
  - Affected observables print total uncertainty plus the split
    `(stat ... syst ...)`.
  - Sparse-replica warnings are appended as `[replica_min_n_pass=...]` or
    `[replica_min_n_cond=...]` only when present.

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
  (a `pyvista.Disc` matching `center`, `diameter`, and `normal`) for
  `source_model.type: object`, colored by `gui.source_color` (default
  `orange`) and `gui.source_opacity` (default `0.25`, must be in `[0, 1]`);
  a no-op for `cosmic`/`beam`. Drawn once in `build_plotter`, not redrawn
  per event.
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
