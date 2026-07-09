# toyMC_cosmic

Toy Monte Carlo for simulating the geometric acceptance and detector-response
rates of a cosmic ray stand.

The current implementation is the headless engine only. It reads a YAML
configuration file, generates straight cosmic-ray tracks, computes geometric
crossings, applies detector efficiencies, and prints rates and conditional
probabilities to the terminal.

## Requirements

- Python 3.12
- a local `venv` created inside the repository folder

The launcher script installs the Python dependencies automatically into
`.venv/` using [requirements.txt](/home/matteo/programmi/toyMC_cosmic/requirements.txt).

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

output:
  detector_rate_decimals: 3
  logic_rate_decimals: 3
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
- `output`: optional CLI formatting settings.
- `output.detector_rate_decimals`: digits after the decimal point for the
  detector-rate table
- `output.logic_rate_decimals`: digits after the decimal point for logic
  expression rates
- `gui`: optional section used by the GUI layer and ignored by the headless
  engine.

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

Example:

```yaml
logic:
  conditional:
    - name: "P(D1 fires | T1 and T2 fire)"
      numerator: "D1"
      given: "T1 and T2"
```

The engine automatically reports both:

- `fired`: evaluate the conditional on detector firing booleans
- `geometric`: evaluate the conditional on pure geometric crossing booleans

`numerator` and `given` use the same expression syntax as `logic.expressions`.

### GUI configuration

The optional `gui:` section controls colors and line width for visualization.

Supported fields:

- `background_color`
- `default_detector_color`
- `detector_colors`
- `default_track_color`
- `track_color_geometric_only`
- `track_color_fired_given_only`
- `track_color_fired_joint`
- `line_width`

Color values can be written as:

- named colors such as `black`, `lightgray`, `orange`, `lime`
- hex strings such as `"#ff8800"`
- RGB triples such as `[0.2, 0.6, 1.0]`

## Running the engine

The main entry point is the root launcher script:

```bash
./run_toymc.sh configs/example.yaml
```

On the first run, `run_toymc.sh` will:

- create `.venv/` in the repository root if it does not exist
- install the dependencies from `requirements.txt`
- launch the local CLI from this checkout

Later runs reuse the same virtual environment unless `requirements.txt`
changes.

If you want to inspect or use the environment manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For local development, the Python wrapper script still exists:

```bash
python3 scripts/run_toymc.py configs/example.yaml
```

That wrapper is mainly useful if you already manage the Python environment
yourself.

### Headless mode

Run the standard terminal-only simulation:

```bash
./run_toymc.sh configs/example.yaml
```

The output prints:

- resolved random seed
- generated event count
- generation area
- detector rate table with geometric and fired columns
- logic-expression rates
- conditional probabilities

### Geometry-only GUI

Open a rotatable detector-only 3D scene without running the Monte Carlo:

```bash
./run_toymc.sh configs/example.yaml --gui --geometry-only
```

### Event-display GUI

Run the simulation once, then step through events in the GUI:

```bash
./run_toymc.sh configs/example.yaml --gui --event-display
```

Current event-display behavior:

- left/right arrow keys step backward or forward
- `q` or `Escape` closes the viewer
- detector colors show:
  - green when crossed and fired
  - red when crossed and not fired
  - base color otherwise
- the track color depends on the currently shown conditional state
- if multiple conditionals are geometrically relevant for one event, the GUI
  cycles through them before advancing to the next event

## Running the tests

The current test suite uses the standard library `unittest` runner:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

## Notes

- The current engine is intentionally geometric and simple.
- It does not simulate energy loss, material interactions, multiple scattering,
  timing, or secondaries.
- The GUI is optional and uses `PyVista` through lazy imports.
- Headless CLI usage still works without importing GUI modules at runtime.
