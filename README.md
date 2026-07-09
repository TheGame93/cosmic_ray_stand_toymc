# Toy MC Cosmic Ray Stand: Acceptance, Rates and Efficiencies

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-blue.svg" alt="Python 3.12">
  <img src="https://img.shields.io/badge/workflow-local%20script%20%2B%20venv-success" alt="Local script and venv workflow">
  <img src="https://img.shields.io/badge/gui-pyvista%20optional-orange" alt="Optional PyVista GUI">
  <img src="https://img.shields.io/badge/status-active-brightgreen" alt="Active status">
</p>

<table>
  <tr>
    <td>
      <strong>Toy Monte Carlo for cosmic-ray stands</strong><br>
      A geometric Monte Carlo for estimating cosmic ray stand acceptance, trigger rates, and detector efficiencies.
    </td>
  </tr>
</table>


> [!IMPORTANT]
> The current engine is intentionally geometric and simple.
> It does not simulate energy loss, material interactions, multiple scattering, timing, or secondaries.

> [!NOTE]
> This repo is meant to be run locally from the checkout with `./run_toymc.sh`.
> The launcher creates `.venv/`, installs dependencies from `requirements.txt`,
> and starts the CLI from this repository.

> [!NOTE] AI disclaimer
> This is a personal project I built mainly to learn how to code with AI assistance.
> I used AI heavily throughout the development process, especially because I had no prior Python experience.
> For me, AI was a tool that made this project possible.

## Quick Start

Clone or copy the repository, then run one of these:

```bash
./run_toymc.sh configs/example.yaml                       # headless rates and probabilities
./run_toymc.sh configs/example.yaml --gui --geometry-only # detector geometry only
./run_toymc.sh configs/example.yaml --gui --event-display # relevant tracks only
```

## Table of Contents

- [What It Does](#what-it-does)
- [How To Run](#how-to-run)
- [GUI Modes](#gui-modes)
- [Configuration](#configuration)
- [Logic and Conditionals](#logic-and-conditionals)
- [GUI Colors and Track States](#gui-colors-and-track-states)
- [Manual Venv Setup](#manual-venv-setup)
- [Tests](#tests)
- [Notes](#notes)

## What It Does

The current implementation is a geometric toy Monte Carlo engine with an
optional GUI layer. It:

- reads a YAML configuration file
- generates straight cosmic-ray tracks
- computes detector crossings
- applies detector efficiencies
- prints detector rates, logic rates, and conditional probabilities
- optionally opens a 3D detector viewer or a relevant-track event display

## How To Run

The main entry point is:

```bash
./run_toymc.sh configs/example.yaml
```

On the first run, the script will:

- create `.venv/` in the repository root
- install dependencies from `requirements.txt`
- run the local CLI from this checkout

Later runs reuse the same environment unless `requirements.txt` changes.

<details>
<summary><strong>Expected headless output</strong></summary>

```text
$ ./run_toymc.sh configs/example.yaml
Progress: 2000000 / 2000000 (100.00%)
Seed: 123456
Generated events: 2000000  (A_gen = 61600.180 cm^2)

Detector rates:
  det  geometric           fired
  T1   1.121 +/- 0.019 Hz  0.902 +/- 0.017 Hz
  T3   0.349 +/- 0.010 Hz  0.288 +/- 0.009 Hz
  D1   0.318 +/- 0.010 Hz  0.318 +/- 0.010 Hz
  T2   1.142 +/- 0.019 Hz  0.921 +/- 0.017 Hz

Logic expressions:
  T1 and T2
    geometric: 0.152 +/- 0.007 Hz
    fired:     0.099 +/- 0.006 Hz
  T1 and T2 and T3
    geometric: 0.087 +/- 0.005 Hz
    fired:     0.048 +/- 0.004 Hz

Conditional probabilities:
  D1|T1*T2
    fired:     0.570 +/- 0.028 (n_cond=321)
    geometric: 0.564 +/- 0.022 (n_cond=495)
  D1|T1*T2*T3
    fired:     0.949 +/- 0.018 (n_cond=156)
    geometric: 0.950 +/- 0.013 (n_cond=281)
```

</details>

## GUI Modes

### Geometry Only

```bash
./run_toymc.sh configs/example.yaml --gui --geometry-only
```

This opens a rotatable 3D view of the detector geometry without running the
Monte Carlo.

### Event Display

```bash
./run_toymc.sh configs/example.yaml --gui --event-display
```

This runs the simulation once and then shows only relevant tracks.

- left/right arrow keys step backward or forward
- `q` or `Escape` closes the viewer
- a track is relevant when at least one conditional `given` expression is true
  in geometric mode for that event
- if one track is relevant for more than one conditional, the GUI cycles
  through those conditionals before moving to the next relevant track
- detector colors mean:
  - green: crossed and fired
  - red: crossed and not fired
  - base color: not crossed
- if `logic.conditional` is empty, event-display mode exits with a clear
  message
- if no relevant tracks are found, event-display mode exits with a clear
  message

## Configuration

The engine is configured through YAML.

<details open>
<summary><strong>Minimal field overview</strong></summary>

- `seed`: fixed integer seed, or `null` to derive it from local time
- `theta_max_deg`: maximum zenith angle in degrees
- `angular_model.type`: currently only `cos2`
- `flux_hz_per_cm2`: total downward flux over the simulated cone
- `monte_carlo.n_events`: number of generated events
- `detectors`: list of detector volumes
- `logic.expressions`: boolean detector expressions to evaluate as rates
- `logic.conditional`: conditional probabilities to report
- `output`: CLI formatting settings
- `gui`: optional GUI-only settings

</details>

<details>
<summary><strong>Full example YAML</strong></summary>

```yaml
seed: 123456
theta_max_deg: 80

angular_model:
  type: cos2

flux_hz_per_cm2: 0.01

monte_carlo:
  n_events: 2000000

detectors:
  - name: T1
    center: [0.0, 0.0, 20.0]
    size: [10.0, 10.0, 1.0]
    efficiency: 0.8
  - name: T3
    center: [0.0, 0.0, 11.0]
    size: [6.0, 5.0, 1.0]
    efficiency: 0.8
  - name: D1
    center: [0.0, 0.0, 9.0]
    size: [6.0, 5.0, 0.3]
    efficiency: 1
  - name: T2
    center: [0.0, 0.0, 0.0]
    size: [10.0, 10.0, 1.0]
    efficiency: 0.8

logic:
  expressions:
    - "T1 and T2"
    - "T1 and T2 and T3"
  conditional:
    - name: "D1|T1*T2"
      numerator: "D1"
      given: "T1 and T2"
    - name: "D1|T1*T2*T3"
      numerator: "D1"
      given: "T1 and T2 and T3"

output:
  detector_rate_decimals: 3
  logic_rate_decimals: 3

gui:
  # Accepted color examples:
  # - named colors such as black, lightgray, orange, lime
  # - named colors reference: Matplotlib named colors
  #   https://matplotlib.org/stable/gallery/color/named_colors.html
  # - hex strings such as "#ff8800"
  # - RGB triples such as [0.2, 0.6, 1.0]
  background_color: white
  default_detector_color: lightgray
  detector_colors:
    T1: black
    T3: black
    D1: gray
    T2: black
  default_track_color: black
  track_color_geometric_only: orange
  track_color_fired_given_only: red
  track_color_fired_joint: green
  line_width: 4.0
```

</details>

<details>
<summary><strong>Detector fields</strong></summary>

Each detector entry must contain:

- `name`: unique detector name used in logic expressions
- `center`: `[x, y, z]`
- `size`: `[dx, dy, dz]`
- `efficiency`: number between `0` and `1`

</details>

## Logic and Conditionals

<details>
<summary><strong>Trimmed logic reference</strong></summary>

Allowed expression syntax:

- detector names such as `T1`, `T2`, `D1`
- `and`
- `or`
- `not`
- parentheses

Short example:

```yaml
logic:
  expressions:
    - "T1 and T2"
    - "T1 and T2 and not D1"
```

Conditionals use the same expression syntax:

```yaml
logic:
  conditional:
    - name: "D1|T1*T2"
      numerator: "D1"
      given: "T1 and T2"
```

The engine reports each conditional in both modes:

- `geometric`: evaluated on detector crossings
- `fired`: evaluated on detector firing booleans

</details>

## GUI Colors and Track States

<details>
<summary><strong>GUI color fields</strong></summary>

Supported GUI fields:

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

</details>

<details open>
<summary><strong>What the three track-color fields mean</strong></summary>

In event-display mode, the currently shown track color is chosen from these
three fields according to the conditional state being displayed:

- `track_color_geometric_only`
  - use this when the conditional `given` is true geometrically
  - but the same `given` is false in fired mode
- `track_color_fired_given_only`
  - use this when the conditional `given` is true in fired mode
  - but the conditional `numerator` is false
- `track_color_fired_joint`
  - use this when both the conditional `given` and `numerator` are true in
    fired mode

So when the README says “the track color depends on the currently shown
conditional state”, it means the GUI picks one of these three config fields for
the specific `(track, conditional)` view currently on screen.

</details>

## Manual Venv Setup

<details>
<summary><strong>Prepare the same local environment manually</strong></summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you already activated that environment yourself, you can also run:

```bash
python3 scripts/run_toymc.py configs/example.yaml
```

</details>

## Tests

<details>
<summary><strong>Run the test suite</strong></summary>

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

</details>