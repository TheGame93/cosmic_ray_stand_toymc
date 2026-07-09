# toyMC_cosmic - GUI implementation plan

## Summary

This plan starts only after
[plan_engine.md](/home/matteo/programmi/toyMC_cosmic/docs/plan_engine.md) is
complete. The GUI is an optional visualization layer built on top of the
headless engine. It must not reimplement or fork any physics, geometry,
crossing, response, logic, or rate calculation.

Locked architectural rule:

- GUI code depends on engine APIs.
- Engine code does not depend on GUI code.
- Headless CLI usage must continue to work when GUI dependencies are absent.

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

## Dependency and packaging model

The GUI lives in separate modules, for example:

```text
src/toymc_cosmic/gui/
├── __init__.py
├── scene.py
└── viewer.py
```

GUI dependency policy:

- add `pyvista` only as an optional install extra
- keep the engine importable without `pyvista`
- lazy-import GUI modules only when the user explicitly requests GUI behavior

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
- evaluate detector logic independently from the engine helper layer

### Configuration ownership

The single YAML format from the engine phase remains in use. GUI-specific
settings live under the optional top-level `gui:` section.

Planned GUI-owned settings:

- `background_color`
- `default_detector_color`
- detector-color overrides by detector name

These settings are visualization-only. Their meaning and validation belong to
the GUI layer, not to detector physics objects.

## Visualization behavior

### Static 3D scene

Provide a 3D detector view with:

- rotatable camera
- visible detector boxes from engine geometry
- configurable detector colors
- configurable background color

`scene.py` should build the static PyVista plotter and detector meshes from the
engine data model only.

Scene construction should be written in a step-by-step style with comments
explaining how engine geometry maps to displayed meshes and colors.

### Event display

Provide an event-by-event viewer with:

- one event shown at a time
- slider-based event selection
- left/right key stepping
- current track drawn in the scene
- detector recoloring per event:
  - green when crossed and fired
  - red when crossed and not fired
  - base color otherwise

The event display must read directly from the engine `SimulationResult`
booleans and track arrays. It must not infer event state by recomputing
geometry.

Event navigation callbacks, actor replacement logic, and the mapping from
engine booleans to detector colors must be explicitly written and commented,
since these are the parts most likely to be opaque to a non-expert reader.

## Integration shape

The GUI can be activated in one of two acceptable ways:

- lazy-imported `--gui` and `--event-display` flags added to the existing CLI
- a thin dedicated GUI entry point that wraps the engine runner

Whichever path is chosen, these rules are mandatory:

- default CLI behavior remains terminal-only
- headless execution remains unchanged when GUI extras are not installed
- GUI launch paths run the engine once, then visualize the returned
  `SimulationResult`

## Module responsibilities

### `gui/scene.py`

- build the PyVista plotter
- create detector meshes from engine detector geometry
- apply background and base detector colors
- expose a reusable scene-construction function for both static and event views

### `gui/viewer.py`

- manage the event-display state
- update the current track actor
- update detector colors based on engine crossing/firing booleans
- wire slider and keyboard stepping callbacks
- keep all per-event rendering logic in one place

No engine physics logic belongs in either module.

Lazy imports and missing-dependency error handling must also be commented
clearly so the boundary between engine and GUI remains easy to follow.

## Implementation order

1. Add the optional GUI dependency to packaging as an extra only.
2. Create `toymc_cosmic.gui` modules with lazy import boundaries.
3. Implement the static scene builder from engine detector data.
4. Implement the event viewer using engine tracks and per-detector boolean
   arrays.
5. Add GUI activation through CLI flags or a thin GUI-specific entry point.
6. Add graceful dependency-error handling when GUI is requested without the GUI
   extra installed.
7. Perform a readability review pass: add or refine docstrings, explanatory
   inline comments, and any overly compressed GUI code paths before
   considering the GUI phase complete.
8. Run headless and GUI smoke tests to confirm the engine/GUI separation holds.

## Test plan

This phase should focus on GUI-specific validation only. Engine behavior must
already be covered by the engine plan.

Small non-render unit tests:

- GUI config parsing/normalization for defaults and detector-color overrides
- lazy-import behavior and friendly dependency errors
- event-selection helpers, if extracted from the viewer

Manual smoke tests:

- `python scripts/run_toymc.py configs/example.yaml --gui`
  - detector geometry appears in 3D
  - mouse rotation works
  - background and base colors follow config
- `python scripts/run_toymc.py configs/example.yaml --event-display`
  - slider changes the current event
  - left/right keys step between events
  - track display updates correctly
  - detector colors match engine booleans for the selected event

Regression checks:

- running the headless CLI without GUI flags still works when `pyvista` is not
  installed
- GUI launch does not change printed engine results or rerun physics in a
  separate code path
- implementation review checks:
  - every function and class has a docstring
  - non-obvious GUI code paths contain explanatory inline comments
  - unnecessarily clever or compressed constructs are rewritten when a clearer
    version is practical

Completion criterion for this plan:

- GUI features work as an optional layer on top of the engine
- missing GUI dependencies fail clearly
- the engine remains independently usable without any visual stack
- the GUI code is readable by a non-expert Python reader, with docstrings and
  comments present across the non-obvious parts of the implementation

## Assumptions and defaults

- `pyvista` is the chosen GUI library.
- The GUI reads engine `Config` plus `SimulationResult` only.
- Event display is interactive and step-based, not an autonomous animation.
- Detector visual properties are owned by the optional `gui:` config section,
  not by the engine `Detector` type.
