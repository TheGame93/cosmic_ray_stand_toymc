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
  the enlarged generation region above the detector stack.
- **`angular.py`** — pluggable zenith-angle sampling models. `Cos2AngularModel`
  (closed-form inverse-CDF for a `cos^2(theta)` density) is the only one
  wired up today; `AngularModel` (ABC) and `TabulatedAngularModel` exist for
  future use (see `docs/truthfiles/goal.md`).
- **`response.py`** — applies per-detector Bernoulli firing efficiency on top
  of a geometric crossing (`apply_response`).
- **`logic.py`** — parses and evaluates boolean detector-coincidence
  expressions (`evaluate`, `extract_names`) via a strict `ast`-based
  whitelist.

Modules built on the leaves:

- **`tracks.py`** — generates straight downward tracks (`generate_tracks`,
  `Tracks`). Depends on `angular.py` + `geometry.py`.
- **`config.py`** — loads and validates the YAML config into a typed,
  immutable `Config`. Depends on `geometry.py` (detector construction) +
  `logic.py` (cross-checking expression names against detector names).
- **`simulation.py`** — orchestrates the full headless pipeline (seed
  resolution → chunked track generation → geometric intersection → response
  → aggregation) into one `SimulationResult`. Depends on `angular.py`,
  `config.py`, `geometry.py`, `response.py`, `tracks.py`.
- **`rates.py`** — turns raw pass/fail counts into Hz rates and conditional
  probabilities with binomial uncertainties (`detector_rates`, `logic_rates`,
  `conditional_probability`). Depends on `logic.py` (and on `simulation.py`
  only under `TYPE_CHECKING`, to avoid a runtime circular import).
- **`cli.py`** — composition root. Wires `config.py` → `simulation.py` →
  `rates.py` → formatted stdout, and is the only core module that imports
  the `gui/` package.

```
config.py      -> geometry.py, logic.py
tracks.py      -> angular.py, geometry.py
simulation.py  -> angular.py, config.py, geometry.py, response.py, tracks.py
rates.py       -> logic.py   (+ simulation.py only under TYPE_CHECKING)
cli.py         -> config.py, rates.py, simulation.py, gui/
```

`src/toymc_cosmic/__init__.py` re-exports the public engine surface:
`Config`, `ConfigError`, `ConditionalConfig`, `load_config`, `Detector`,
`ProbabilityEstimate`, `RateEstimate`, `SimulationResult`, `run_simulation`,
`Tracks`. Note `angular.py`, `logic.py`, `response.py`, and `cli.py` are
*not* re-exported at package level — they're internal to the pipeline.

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
  finite segment inside a computed display box. No PyVista.
- **`scene.py`** — static 3D scene construction, camera framing, and the
  `--geometry-only` entry point (`show_geometry_only`).
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
detectors, conditionals, `theta_max`), `geometry.py` (`Detector`,
`generation_region`), `logic.py` (`evaluate`, `extract_names`),
`simulation.py` (`SimulationResult`, produced upstream by `cli.py` and
passed in). It never imports `tracks.py`, `rates.py`, `response.py`, or
`angular.py` directly — only via the already-computed `SimulationResult`.

## Tests

`tests/` mirrors `src/toymc_cosmic/` one-to-one: `test_<module>.py` for each
core module, `test_gui_<module>.py` for each GUI module.
