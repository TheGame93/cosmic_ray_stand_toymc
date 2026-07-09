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

You can install the package in editable mode with:

```bash
python3 -m pip install -e .
```

If you also want the declared development dependency for future `pytest` use:

```bash
python3 -m pip install -e .[dev]
```

## Project layout

- `configs/example.yaml`: example engine configuration
- `scripts/run_toymc.py`: direct runner script
- `src/toymc_cosmic/`: engine package
- `tests/`: headless engine test suite

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

## Running the engine

Run the example configuration with the script:

```bash
python3 scripts/run_toymc.py configs/example.yaml
```

You can also run the installed console entry point:

```bash
toymc-cosmic configs/example.yaml
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

If you installed the dev extra and want to use `pytest`, it can discover the
same tests:

```bash
PYTHONPATH=src pytest
```

## Notes

- The current engine is intentionally geometric and simple.
- It does not simulate energy loss, material interactions, multiple scattering,
  timing, or secondaries.
- The GUI is planned separately and is not part of the current runtime.
