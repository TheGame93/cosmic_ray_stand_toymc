# toyMC_cosmic

Toy Monte Carlo for simulating the geometric acceptance and detector-response
rates of a cosmic ray stand.

The current implementation is the headless engine only. It reads a YAML
configuration file, generates straight cosmic-ray tracks, computes geometric
crossings, applies detector efficiencies, and prints rates and conditional
probabilities to the terminal.

## Requirements

- Python 3.12
- `numpy`
- `PyYAML`

## Configuration

The engine is configured through YAML.

Example:

```yaml
seed: 123456
theta_max_deg: 80.0

angular_model:
  type: cos2

flux_hz_per_cm2: 0.01

monte_carlo:
  n_events: 2000000

detectors:
  - name: T1
    center: [0.0, 0.0, 100.0]
    size: [20.0, 20.0, 1.0]
    efficiency: 0.98
  - name: T2
    center: [0.0, 0.0, 50.0]
    size: [20.0, 20.0, 1.0]
    efficiency: 0.95
  - name: D1
    center: [0.0, 0.0, 0.0]
    size: [20.0, 20.0, 1.0]
    efficiency: 0.90

logic:
  expressions:
    - "T1 and T2 and D1"
    - "T1 and T2 and not D1"
  conditional:
    - name: "P(D1 fires | T1 and T2 fire)"
      numerator: "D1"
      given: "T1 and T2"
      mode: fired
```

### Main configuration fields

- `seed`: integer seed for reproducible runs. Use `null` to derive it from the
  local time.
- `theta_max_deg`: maximum zenith angle in degrees. Must be between `0` and
  `90`.
- `angular_model.type`: currently only `cos2` is supported.
- `flux_hz_per_cm2`: total downward flux over the simulated angular cone.
- `monte_carlo.n_events`: number of generated events.
- `detectors`: list of detector volumes.
- `logic.expressions`: detector logic expressions to evaluate as rates.
- `logic.conditional`: conditional probabilities to report.
- `gui`: optional section preserved for the future GUI layer. It is ignored by
  the headless engine.

### Detector fields

Each detector entry must contain:

- `name`: unique detector name used in logic expressions
- `center`: `[x, y, z]`
- `size`: `[dx, dy, dz]`
- `efficiency`: number between `0` and `1`

### Writing logic expressions

`logic.expressions` is a YAML list of strings. Each string is a boolean
expression built from detector names.

Allowed syntax:

- detector names such as `T1`, `T2`, `D1`
- `and`
- `or`
- `not`
- parentheses

Examples:

```yaml
logic:
  expressions:
    - "T1"
    - "T1 and T2"
    - "T1 and T2 and D1"
    - "T1 and T2 and not D1"
    - "T1 and (T2 or D1)"
```

Important rules:

- detector names must match exactly the names defined in `detectors`
- expressions must be quoted strings in YAML
- only boolean logic is allowed

Not allowed:

- comparisons such as `"T1 == T2"`
- arithmetic such as `"T1 + T2"`
- function calls such as `"T1()"`

The engine validates expressions before running the simulation.

### Writing conditional probabilities

`logic.conditional` is a YAML list. Each entry asks the engine to compute a
conditional probability of the form:

```text
P(numerator | given)
```

Each entry must contain:

- `name`: label printed in the output
- `numerator`: expression for the event in the numerator
- `given`: expression for the conditioning event
- `mode`: which boolean dataset to use

Example:

```yaml
logic:
  conditional:
    - name: "P(D1 fires | T1 and T2 fire)"
      numerator: "D1"
      given: "T1 and T2"
      mode: fired
```

Another valid example:

```yaml
logic:
  conditional:
    - name: "P(D1 crossed | T1 and T2 crossed)"
      numerator: "D1"
      given: "T1 and T2"
      mode: geometric
```

Allowed `mode` values:

- `fired`: use detector firing booleans
- `geometric`: use pure geometric crossing booleans

`numerator` and `given` use the same expression syntax as `logic.expressions`.

## Running the engine

Run the example configuration with the script:

```bash
python3 scripts/run_toymc.py configs/example.yaml
```

The output prints:

- resolved random seed
- generated event count
- generation area
- geometric crossing rates
- fired rates
- logic-expression rates
- conditional probabilities

## Running the tests

The current test suite uses the standard library `unittest` runner:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Notes

- The current engine is intentionally geometric and simple.
- It does not simulate energy loss, material interactions, multiple scattering,
  timing, or secondaries.
- The GUI is planned separately and is not part of the current runtime.
