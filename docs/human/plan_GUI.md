# toyMC_cosmic - GUI implementation plan

## Summary

This plan builds on the current headless engine implementation described in
[plan_engine.md](/home/matteo/programmi/toyMC_cosmic/docs/plan_engine.md).
The GUI is an optional visualization layer built on top of that engine. It
must not reimplement or fork any physics, geometry, crossing, response, logic,
or rate calculation.

Locked architectural rule:

- GUI code depends on engine APIs.
- Engine code does not depend on GUI code.
- Headless CLI usage must continue to work when GUI dependencies are absent.

Current engine APIs that the GUI plan must match:

- `toymc_cosmic.load_config(path) -> Config`
- `toymc_cosmic.run_simulation(config, progress_callback=None) -> SimulationResult`
- `toymc_cosmic.Detector`
- `toymc_cosmic.Tracks`
- `toymc_cosmic.SimulationResult`
- current repo-local runner `python3 scripts/run_toymc.py ...`

The current repository still contains packaging metadata, but the GUI phase
should treat this project primarily as a local runnable folder rather than as a
distributable package. The preferred user-facing launcher for the GUI phase
will be a root-level shell script that prepares a local virtual environment and
then launches the application.

## Implementation style

This phase must follow the same readability-first rule as the engine plan.
The GUI code should be understandable to a non-expert Python reader.

- Prefer readability and explicitness over compact, clever, or heavily
  abstract Python.
- Prefer simple control flow over dense one-liners.
- Prefer explicit variable names over terse names.
- Prefer small understandable steps over compressed callback or actor-update
  logic when both are viable.
- Every function, including internal helpers, must have a docstring describing
  purpose, inputs, outputs, and important assumptions.
- Every class must have a docstring describing its responsibility and the
  meaning of its main fields.
- Inline comments are required generously in non-obvious code paths. Comments
  must explain why a step exists and what is being computed, not trivial syntax.
- Short examples in docstrings or comments are encouraged when they remove
  ambiguity for a beginner reader.

## Dependency and runtime model

The GUI should live in separate modules under the existing local Python
codebase, for
example:

```text
src/toymc_cosmic/gui/
├── __init__.py
├── config.py
├── scene.py
├── layout.py
├── event_state.py
├── track_bounds.py
├── buttons.py
├── legend.py
└── viewer.py
```

The event-display GUI was later split by logic across `layout.py`,
`event_state.py`, `track_bounds.py`, `buttons.py`, and `legend.py` once
`viewer.py` grew past 800 lines; see the "Module responsibilities" section
below for what each one owns. `viewer.py` remains the PyVista-facing
orchestrator (`show_event_display` and `EventDisplayController`) and the
only new-module boundary that still imports PyVista.

GUI dependency policy:

- keep GUI dependencies local to the project virtual environment
- install GUI dependencies from the root launcher script when the environment
  is first created
- keep the engine importable without `pyvista`
- lazy-import GUI modules only when the user explicitly requests GUI behavior

Runtime model for this phase:

- create a project-local virtual environment in the repository root
- add a root-level `.sh` launcher that:
  - creates the venv if missing
  - installs the required dependencies into that venv
  - launches the local application from the repository checkout
- update the README to document this venv-based workflow

Package-style installation is not part of the intended GUI workflow.

If GUI is requested without GUI dependencies installed, the application must
fail gracefully with a clear install message and must not break headless usage.

## GUI inputs and configuration ownership

The GUI must consume:

- engine `Config`
- engine `SimulationResult`
- engine `Detector` definitions

It must not:

- resample tracks
- recompute detector crossings
- recompute detector firing
- implement its own detector-logic parser or evaluator

More concretely, the current engine data model provides:

- `Config.gui`, preserved by the engine as `dict[str, Any] | None`
- `SimulationResult.detectors`, an ordered `list[Detector]`
- `SimulationResult.crossed` and `SimulationResult.fired`, each a
  `dict[str, np.ndarray]` keyed by detector name
- `SimulationResult.tracks.origins` and `SimulationResult.tracks.directions`,
  each with shape `(n_events, 3)`

The GUI should treat `Config.gui` as its raw input mapping and normalize it in
GUI-owned code. The engine must continue to preserve that section opaquely.

### Configuration ownership

The single YAML format from the engine phase remains in use. GUI-specific
settings live under the optional top-level `gui:` section.

Planned GUI-owned settings:

- `background_color`
- `default_detector_color`
- detector-color overrides by detector name
- `default_track_color`
- track color for events that are geometrically relevant for the current
  conditional but do not satisfy the conditional `given` expression in fired
  mode
- track color for events that satisfy the conditional `given` expression in
  fired mode but not the `numerator`
- track color for events that satisfy both `given` and `numerator` in fired
  mode
- `line_width`

The YAML should also contain a comment block listing acceptable color formats
or examples, so the user can discover valid values directly in the config file.

Because the current engine preserves `gui:` without interpretation, the GUI
layer should introduce its own small normalization step for these settings
rather than moving validation into `toymc_cosmic.config`.

These settings are visualization-only. Their meaning and validation belong to
the GUI layer, not to detector physics objects.

## Visualization behavior

### Static 3D scene

Provide a 3D detector view with:

- rotatable camera
- visible detector boxes from engine geometry
- configurable detector colors
- configurable background color
- no simulation run in this mode

`scene.py` should build the static PyVista plotter and detector meshes from the
engine data model only. In the current codebase, detector geometry is available
from `Detector.center`, `Detector.size`, and the derived bound properties.

Scene construction should be written in a step-by-step style with comments
explaining how engine geometry maps to displayed meshes and colors.

### Event display

Provide an event-by-event viewer with:

- one event shown at a time
- keyboard-driven stepping
- current track drawn in the scene
- detector recoloring per event:
  - green when crossed and fired
  - red when crossed and not fired
  - base color otherwise
- conditional-by-conditional stepping inside the same event

Event display flow:

- `--gui --event-display` runs the simulation
- the viewer advances only when the user explicitly asks to move forward or
  backward
- the default navigation order is:
  - `(event 17, conditional 1)`
  - `(event 17, conditional 2)`
  - `(event 17, conditional 3)`
  - `(event 18, conditional 1)`
- only geometrically relevant events are included in navigation
- if an event has no geometrically relevant conditional, it is skipped

The event display must read directly from the engine `SimulationResult`
booleans and track arrays. It must not infer event state by recomputing
geometry.

For the current engine, this means:

- use `tracks.origins[event_index]` and `tracks.directions[event_index]` as the
  source event track
- use `crossed[detector_name][event_index]` to decide whether the detector was
  geometrically crossed
- use `fired[detector_name][event_index]` to decide whether the crossed
  detector fired

The viewer may derive a display line segment from the stored origin and
direction for rendering purposes, but that display geometry must not become a
second source of truth for detector state.

### Conditional relevance and track-color states

A conditional is relevant for an event only if its `given` expression is true
in geometric mode for that event.

For a geometrically relevant conditional, the track color should encode the
fired-mode conditional state with three user-configurable colors:

- geometric-only state:
  - the event is relevant because the conditional `given` is true in geometric
    mode
  - but the same `given` expression is false in fired mode
- fired-given-only state:
  - the conditional `given` is true in fired mode
  - the conditional `numerator` is false in fired mode
- fired-joint state:
  - both `given` and `numerator` are true in fired mode

If no conditional is geometrically relevant for any event in the simulation,
event-display mode should fail clearly instead of opening an empty viewer.

### Event track segment bounds

The displayed track should be a finite segment, not an infinite line.

The display bounds are:

- `z_max_display = 1.1 * max(z_detector_top)`
- `z_min_display = 0.9 * min(z_detector_bottom)`
- `x` and `y` limits should match the generation-region boundaries already
  computed from detector geometry and `theta_max`

Event navigation callbacks, actor replacement logic, and the mapping from
engine booleans to detector colors must be explicitly written and commented,
since these are the parts most likely to be opaque to a non-expert reader.

## Integration shape

The GUI should be activated through CLI flags added to the existing CLI flow.

Required behavior:

- `--gui --geometry-only` loads the config and shows detector geometry only
- `--gui --event-display` runs the simulation once, then opens the step-by-step
  event viewer
- default CLI behavior remains terminal-only
- the repo-local shell launcher becomes the primary way to start the program
- existing local Python entry points may remain for development, but they are
  no longer the primary documented UX

The implementation should reuse the current `load_config(...)` and
`run_simulation(...)` flow rather than introducing a second engine-launch path.

## Module responsibilities

### `gui/config.py`

- normalize `Config.gui` into GUI-specific settings with defaults
- validate color settings and detector-color overrides
- normalize track-state colors and line width
- keep GUI-only interpretation out of `toymc_cosmic.config`
- provide a single place where accepted color examples are documented for YAML
  comments and README examples

### `gui/scene.py`

- build the PyVista plotter
- create detector meshes from engine detector geometry
- apply background and base detector colors
- expose a reusable scene-construction function for both static and event views

### `gui/layout.py`

- single source of truth for on-screen position/size constants: button
  sizing, the top-left legend box, and the bottom-left stack of
  `[axes triad]` above `[button row]` above `[key-hint text]`
- constants only, no functions and no PyVista, so it stays cheap to load
  on its own
- the bottom-stack constants are deliberately coupled to each other (kept
  in one place rather than split across files) so they cannot silently
  drift out of sync and reintroduce overlap

### `gui/event_state.py`

- manage the event-display state (`EventDisplayState`, `PreparedConditional`)
- manage the nested `(event_index, conditional_index_within_event)`
  navigation (`EventNavigator`)
- precompute per-event/conditional boolean arrays and relevant-event
  selection
- pure Python/NumPy bookkeeping -- no PyVista

### `gui/track_bounds.py`

- compute the finite display box from detector geometry
- clip an event's infinite track line into a finite segment for rendering
- pure geometry math -- no PyVista

### `gui/buttons.py`

- build the Home/Previous/Next button layout, icon textures, and the raw
  VTK button widgets
- generic and self-contained: takes `pv`/`plotter` objects as parameters
  rather than importing PyVista itself

### `gui/legend.py`

- build the legend's plain-text lines and the dynamic
  "Given .../ Numerator ..." sentence from one `EventDisplayState`
- pure string building -- no PyVista

### `gui/viewer.py`

- orchestrate the pieces above into `show_event_display` and
  `EventDisplayController`
- update the current track actor
- update the track color for the current conditional state
- update detector colors based on engine crossing/firing booleans
- wire keyboard stepping callbacks
- own the PyVista scene and keep all per-event *rendering* calls
  (`add_mesh`/`add_text`/button widgets) in one place, even though the
  logic that decides *what* to render now lives in the sibling modules
  above

No engine physics logic belongs in any of these modules.

Lazy imports and missing-dependency error handling must also be commented
clearly so the boundary between engine and GUI remains easy to follow.

## Implementation order

1. Add project-local GUI environment setup through a root shell launcher and
   virtual environment creation.
2. Update the README to document the venv workflow and launcher usage.
3. Create `toymc_cosmic.gui` modules with lazy import boundaries.
4. Add a GUI-owned config normalization layer that reads the existing
   `Config.gui` mapping.
5. Implement the static geometry-only scene builder from engine detector data.
6. Implement the event viewer using engine tracks and per-detector boolean
   arrays.
7. Add nested event/conditional navigation and track-color state handling.
8. Add GUI activation through `--gui --geometry-only` and
   `--gui --event-display`.
9. Add graceful dependency-error handling when GUI is requested without the GUI
   environment being ready.
10. Perform a readability review pass: add or refine docstrings, explanatory
   inline comments, and any overly compressed GUI code paths before
   considering the GUI phase complete.
11. Run headless and GUI smoke tests to confirm the engine/GUI separation
    holds.

## Test plan

This phase should focus on GUI-specific validation only. Engine behavior must
already be covered by the engine plan.

Small non-render unit tests:

- GUI config parsing/normalization from raw `Config.gui` for defaults and
  detector-color overrides
- GUI parsing/normalization for default track color, conditional-state track
  colors, and line width
- lazy-import behavior and friendly dependency errors
- event-selection helpers, if extracted from the viewer
- conditional-relevance selection and nested event/conditional ordering helpers

Manual smoke tests:

- `./run_toymc.sh configs/example.yaml --gui --geometry-only`
  - detector geometry appears in 3D
  - mouse rotation works
  - background and base colors follow config
- `./run_toymc.sh configs/example.yaml --gui --event-display`
  - left/right keys step between events
  - per-event stepping pauses until the user advances
  - events with multiple relevant conditionals cycle conditional-by-conditional
  - track display updates correctly
  - track color matches the current conditional state
  - detector colors match engine booleans for the selected event
- `./run_toymc.sh configs/example.yaml`
  - headless terminal output remains unchanged when no GUI flags are passed

Regression checks:

- running the headless CLI without GUI flags still works when `pyvista` is not
  installed
- GUI launch does not change printed engine results or rerun physics in a
  separate code path
- engine config loading still accepts and preserves `gui:` without requiring or
  validating GUI-specific fields
- the root launcher creates the venv and installs dependencies only when
  needed, then reuses the existing environment on later runs
- the README examples match the actual launcher behavior
- implementation review checks:
  - every function and class has a docstring
  - non-obvious GUI code paths contain explanatory inline comments
  - unnecessarily clever or compressed constructs are rewritten when a clearer
    version is practical

Completion criterion for this plan:

- GUI features work as an optional layer on top of the engine
- missing GUI dependencies fail clearly
- the engine remains independently usable without any visual stack
- the root launcher and venv workflow are documented and usable locally
- the GUI code is readable by a non-expert Python reader, with docstrings and
  comments present across the non-obvious parts of the implementation

## Assumptions and defaults

- `pyvista` is the chosen GUI library.
- The GUI reads the current engine `Config`, `SimulationResult`, and
  `Detector`/`Tracks` data exposed through those objects.
- Event display is interactive and step-based, not an autonomous animation.
- Detector visual properties are owned by the optional `gui:` config section,
  not by the engine `Detector` type.
- Geometry-only mode does not run the Monte Carlo.
- Keyboard navigation is the first supported interaction mode for event
  stepping.
