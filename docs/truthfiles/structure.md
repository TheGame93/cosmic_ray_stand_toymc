# Structure

> Maintained per the documentation contract in AGENT.md — update this file
> when the change you're making alters what's described here.

Two layers: the core engine (`src/toymc_cosmic/*.py`) and the optional GUI
subpackage (`src/toymc_cosmic/gui/*.py`). The engine never imports the GUI;
the GUI is only ever reached from `cli.py`.

## Core pipeline

Reading order follows the dependency graph, leaves first.

Leaf modules (no internal dependencies):

- **`geometry.py`** — axis-aligned `Detector` volumes (`center` ± `size/2`)
  and ray/AABB crossing tests. Also computes the flat generation plane and
  the enlarged generation region used by the cosmic source, plus the
  `reference_z` / `min_reference_z` reference planes used by the cosmic and
  beam sources respectively.
- **`angular.py`** — pluggable zenith-angle sampling models used by the
  cosmic source. `Cos2AngularModel` (closed-form inverse-CDF for a
  `cos^2(theta)` density) is the only one wired up today; `AngularModel`
  (ABC) and `TabulatedAngularModel` exist for future use (see
  `docs/truthfiles/goal.md`).
- **`response.py`** — applies per-detector Bernoulli firing efficiency on top
  of a geometric crossing (`apply_response`).
- **`logic.py`** — parses and evaluates boolean detector-coincidence
  expressions (`evaluate`, `extract_names`) via a strict `ast`-based
  whitelist.
- **`tracks.py`** — the `Tracks` container (origins + directions, shape
  validation only). No generation logic lives here; see `source.py`.

Modules built on the leaves:

- **`config.py`** — loads and validates the YAML config into a typed,
  immutable `Config`. Depends on `geometry.py` (detector construction) +
  `logic.py` (cross-checking expression names against detector names). Owns
  the `source_model` discriminated union (`CosmicSourceConfig` /
  `BeamSourceConfig` / `ObjectSourceConfig`, under the `SourceModelConfig`
  marker base) alongside the other small config dataclasses.
- **`source.py`** — pluggable source models: the `SourceModel` ABC
  (`generate`, `total_rate_hz`, `spatial_bounds`) plus `CosmicSourceModel`,
  `BeamSourceModel`, `ObjectSourceModel`, and the `build_source_model`
  dispatcher that turns a `SourceModelConfig` into the matching model.
  Depends on `angular.py` + `geometry.py` (physics), `tracks.py` (return
  container), and `config.py` (the config dataclasses it dispatches on).
- **`simulation.py`** — orchestrates the full headless pipeline (seed
  resolution → chunked track generation via the configured source model →
  geometric intersection → response → aggregation) into one
  `SimulationResult`. Depends on `config.py`, `geometry.py`, `response.py`,
  `source.py`, `tracks.py`.
- **`rates.py`** — turns raw pass/fail counts into Hz rates and conditional
  probabilities with binomial uncertainties (`detector_rates`, `logic_rates`,
  `conditional_probability`). Depends on `logic.py` (and on `simulation.py`
  only under `TYPE_CHECKING`, to avoid a runtime circular import).
- **`cli.py`** — composition root. Wires `config.py` → `simulation.py` →
  `rates.py` → formatted stdout, and is the only core module that imports
  the `gui/` package.

```
config.py      -> geometry.py, logic.py
source.py      -> angular.py, config.py, geometry.py, tracks.py
simulation.py  -> config.py, geometry.py, response.py, source.py, tracks.py
rates.py       -> logic.py   (+ simulation.py only under TYPE_CHECKING)
cli.py         -> config.py, rates.py, simulation.py, gui/
```

`src/toymc_cosmic/__init__.py` re-exports the public engine surface:
`BeamSourceConfig`, `Config`, `ConfigError`, `ConditionalConfig`,
`CosmicSourceConfig`, `Detector`, `ObjectSourceConfig`,
`ProbabilityEstimate`, `RateEstimate`, `SimulationResult`,
`SourceModelConfig`, `Tracks`, `load_config`, `run_simulation`. Note
`angular.py`, `logic.py`, `response.py`, `source.py`, and `cli.py` are *not*
re-exported at package level — they're internal to the pipeline.

## GUI subpackage (`gui/`)

Only reached via `cli.py`'s `--gui` flag. Only `scene.py` and `viewer.py`
import PyVista, and both do so lazily through a duplicated `_require_pyvista()`
guard that raises a friendly `RuntimeError` if PyVista isn't installed.

- **`layout.py`** — screen-position/size constants only (button sizing,
  legend box, bottom-left stacked layout). No PyVista import, no functions.
- **`config.py`** — parses the optional `gui:` YAML block into a normalized
  `GUIConfig` (colors, line width, per-detector overrides).
- **`event_state.py`** — pure NumPy bookkeeping: which event/conditional is
  being displayed, track relevance, and the three-state
  geometric-only/fired-given-only/fired-joint color logic. No PyVista.
- **`legend.py`** — turns one `EventDisplayState` into the legend's text
  lines. No PyVista.
- **`buttons.py`** — generic VTK button-widget factory (Home/Previous/Next
  icons). Deliberately never imports PyVista itself — `pv`/`plotter` objects
  are passed in by the caller.
- **`track_bounds.py`** — clips an infinite track (origin + direction) into a
  finite segment inside a computed display box. `compute_display_bounds`
  unions the detector bounding box with the active `SourceModel`'s own
  `spatial_bounds`, then pads every axis uniformly — one box shape for all
  three source types. No PyVista.
- **`scene.py`** — static 3D scene construction, camera framing, and the
  `--geometry-only` entry point (`show_geometry_only`). `startup_view_up`
  picks the startup camera's up vector from the source type (`x`-up for
  `beam`, the usual `z`-up otherwise); `render_source_shape` draws the
  source volume (sphere/cylinder/box) once for `object`-type sources only.
- **`viewer.py`** — the `--event-display` entry point (`show_event_display`)
  and `EventDisplayController`, the PyVista-owning orchestrator that wires
  together navigation state, track clipping, buttons, and legend text.

```
cli.py
  -> gui/__init__.py  (facade: show_event_display, show_geometry_only)
        -> scene.show_geometry_only(config)                [--geometry-only]
        -> viewer.show_event_display(config, simulation_result)  [--event-display]
              -> gui/config.load_gui_config
              -> gui/event_state (relevance, navigation, per-event states)
              -> gui/track_bounds (per-frame track clip)
              -> viewer.EventDisplayController
                    -> gui/scene (plotter, camera, detector colors)
                    -> gui/buttons (nav widgets)
                    -> gui/legend (legend text)
                    -> gui/layout (screen-position constants)
```

The GUI touches these core modules directly: `config.py` (`Config`,
detectors, conditionals, `source_model`), `geometry.py` (`Detector`,
`bounding_box`), `logic.py` (`evaluate`, `extract_names`), `source.py`
(`build_source_model`, used for its `spatial_bounds` and to gate the
`object`-only source rendering), and `simulation.py` (`SimulationResult`,
produced upstream by `cli.py` and passed in). It never imports `tracks.py`,
`rates.py`, `response.py`, or `angular.py` directly — only via the
already-computed `SimulationResult` or through `source.py`.

## Tests

`tests/` mirrors `src/toymc_cosmic/` one-to-one: `test_<module>.py` for each
core module, `test_gui_<module>.py` for each GUI module.
