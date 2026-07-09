# toyMC_cosmic - implementation plan index

This repo now uses a two-step implementation plan derived from
[desiderata.md](/home/matteo/programmi/toyMC_cosmic/docs/desiderata.md):

1. [plan_engine.md](/home/matteo/programmi/toyMC_cosmic/docs/plan_engine.md)
   Build the standalone Monte Carlo engine, reusable Python API, YAML loader,
   and terminal CLI.
2. [plan_GUI.md](/home/matteo/programmi/toyMC_cosmic/docs/plan_GUI.md)
   Build the optional visualization layer on top of the completed engine.

## Dependency direction

- The GUI depends on the engine.
- The engine does not depend on the GUI.
- The engine must be fully usable and testable without `pyvista`, viewer code,
  or any visual output.

## Configuration rule

The project keeps a single YAML format. GUI settings, when present, live in an
optional top-level `gui:` section. The engine must not require that section for
validation or execution.

## Implementation style

This project prioritizes code that is easy to read and learn from:

- prefer readability and explicitness over compact, clever, or highly abstract
  Python
- prefer simple control flow and clear intermediate variables over dense
  one-liners
- require docstrings on all functions and classes
- require generous inline comments in non-obvious code paths, especially to
  explain why a step exists and what is being computed
- welcome short examples in comments or docstrings when they help a non-expert
  Python reader

## Source of requirements

Product requirements remain in
[desiderata.md](/home/matteo/programmi/toyMC_cosmic/docs/desiderata.md).
The two plan files below turn those requirements into an implementation order:

- [plan_engine.md](/home/matteo/programmi/toyMC_cosmic/docs/plan_engine.md)
- [plan_GUI.md](/home/matteo/programmi/toyMC_cosmic/docs/plan_GUI.md)
