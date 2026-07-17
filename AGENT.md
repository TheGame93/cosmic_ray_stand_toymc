# AGENT.md

AI-facing entry point for this repo. Read this instead of `README.md`
(which is the human/GitHub-facing doc). You should not need to open
`README.md` to work on this codebase.

## What this repo is

`toymc_cosmic` is a geometric toy Monte Carlo for cosmic-ray detector
stands: given a YAML geometry + boolean trigger logic, it estimates
detector rates, logic-expression rates, and conditional probabilities, both
geometrically and with detector efficiencies applied. It is intentionally
simple — no energy loss, scattering, secondaries, pileup, or timing. Not
GEANT4. Full scope/non-goals: `docs/truthfiles/goal.md`.

## Running things

```bash
./run_toymc.sh configs/example_cosmic.yaml                       # headless
./run_toymc.sh configs/example_cosmic.yaml --gui --geometry-only  # 3D geometry view
./run_toymc.sh configs/example_cosmic.yaml --gui --event-display  # track-by-track view
```

First run creates `.venv/` and installs `requirements.txt`; later runs
reuse it. Manual setup: `python3 -m venv .venv && source .venv/bin/activate
&& pip install -r requirements.txt`.

Tests:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

## Ground truth: `docs/truthfiles/`

Read these before making non-trivial changes:

- **`goal.md`** — project purpose, scope boundary, operating modes.
- **`structure.md`** — module-by-module map and dependency graph for
  `src/toymc_cosmic/` (core engine) and `src/toymc_cosmic/gui/`.
- **`invariants.md`** — hard rules the code currently enforces (config
  validation, geometry/logic/rates semantics, GUI contracts). This is the
  file to check before assuming how something behaves.
- **`functions.md`** — generated index of every function/class and the
  first line of its docstring, grouped by file.

**On load**: regenerate `functions.md` before relying on it:

```bash
.venv/bin/python scripts/gen_function_truthfile.py
```

If it's not up to date and you can't safely run it yourself, tell the user
to run it rather than guessing at its content.

## `docs/human/` — not for you

`docs/human/` is the user's human-facing scratch space: unorganized drafts,
half-formed ideas, old planning docs, personal notes. It is never
authoritative, never a truthfile, and not required reading. Don't consult
it unless the user specifically asks for historical context.

## Documentation contract

This repo maintains `docs/truthfiles/` deliberately so an agent never has
to be told these rules from scratch. Follow them without being reminded:

1. **Docstring first line template**: imperative verb phrase + explicit
   return hint, one line, period-terminated. Example:
   `"Compute crossing points for a straight-line track; returns list[CrossingPoint]."`
   Applies to new/changed functions going forward — existing docstrings are
   not yet retrofitted, don't assume every current first line already
   matches this.
2. Any plan or task breakdown for a change touching `src/` must include an
   explicit step to update the relevant truthfile(s) — listed up front, not
   discovered as an afterthought once code is done.
3. Module responsibility or data-flow changes → update `structure.md`.
   New, changed, or removed hard constraints → update `invariants.md`.
4. Don't hand-edit `functions.md` — regenerate it with the script instead.
