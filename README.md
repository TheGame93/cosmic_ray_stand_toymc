# Toy MC Particle Detector Stand: Acceptance, Rates and Efficiencies

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-blue.svg" alt="Python 3.12">
  <img src="https://img.shields.io/badge/workflow-local%20script%20%2B%20venv-success" alt="Local script and venv workflow">
  <img src="https://img.shields.io/badge/gui-pyvista%20optional-orange" alt="Optional PyVista GUI">
  <img src="https://img.shields.io/badge/status-active-brightgreen" alt="Active status">
</p>

<table align="center">
  <tr>
    <td align="center">
      <strong>Toy Monte Carlo for cosmic-ray stands</strong><br>
      A geometric Monte Carlo for estimating cosmic ray stand acceptance, trigger rates, and detector efficiencies.
    </td>
  </tr>
</table>


<p align="center">
  <img src="docs/images/track_good.png" width="600" alt="Cosmic-ray track crossing the detector stand">
  <br>
  <em>A cosmic-ray track crossing two 10×10 cm² trigger scintillators (T1, T2)<br>and firing the
  6×5 cm² D1 detector. The central 6×5 cm² T3 scintillator (grey, transparent)<br>sits in the geometry but is
  not used by this particular logic configuration.</em>
</p>

<table align="center" width="600">
  <tr>
    <td align="center" width="33%"><img src="docs/images/example_beam.png" width="100%" alt="Given true, numerator false"></td>
    <td align="center" width="33%"><img src="docs/images/example_object.png" width="100%" alt="Given false, numerator true"></td>
  </tr>
  <tr>
    <td align="center"><strong>Particle Beam</strong><br> setups</td>
    <td align="center"><strong>Radioactive Sources</strong><br></td>
  </tr>
</table>


> [!IMPORTANT]
> The current engine is intentionally geometric and simple.
> It does not simulate energy loss, material interactions, multiple scattering, secondaries, pileup or timing requirements. It's not GEANT4.

> [!NOTE]
> **AI disclaimer**
> This is a personal project I built mainly to learn how to code with AI assistance.
> I used AI heavily throughout the development process, especially because I had no prior Python experience.
> For me, AI was a tool that made this project possible.

## Quick Start

Clone or copy the repository, then run one of these:

```bash
./run_toymc.sh configs/example_cosmic.yaml                       # only terminal output
./run_toymc.sh configs/example_cosmic.yaml --gui --geometry-only # view detector geometry
./run_toymc.sh configs/example_cosmic.yaml --gui --event-display # view particle tracks
```

You can also change source type:
```bash
configs/example_beam.yaml   # horizontal particle beam
configs/example_object.yaml # radioactive source
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
./run_toymc.sh configs/example_cosmic.yaml
```

On the first run, the script will:

- create `.venv/` in the repository root
- install dependencies from `requirements.txt`
- run the local CLI from this checkout

Later runs reuse the same environment unless `requirements.txt` changes.

<details>
<summary><strong>Expected headless output</strong></summary>

```text
$ ./run_toymc.sh configs/example_cosmic.yaml
Progress: 2000000 / 2000000 (100.00%)
Seed: 123456
Generated events: 2000000  (cosmic flux = 0.01 Hz/cm2)

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
./run_toymc.sh configs/example_cosmic.yaml --gui --geometry-only
```

This opens a rotatable 3D view of the detector geometry without running the
Monte Carlo.

### Event Display

```bash
./run_toymc.sh configs/example_cosmic.yaml --gui --event-display
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

<table align="center" width="600">
  <tr>
    <td align="center" width="33%"><img src="docs/images/track_good.png" width="100%" alt="Given and numerator both true"></td>
    <td align="center" width="33%"><img src="docs/images/track_bad.png" width="100%" alt="Given true, numerator false"></td>
    <td align="center" width="33%"><img src="docs/images/track_valid.png" width="100%" alt="Given false, numerator true"></td>
  </tr>
  <tr>
    <td align="center"><strong>Given YES / Numerator YES</strong><br>T1 and T2 both fire (given), and D1 also fires (numerator): a fully confirmed coincidence.</td>
    <td align="center"><strong>Given YES / Numerator NO</strong><br>T1 and T2 fire the trigger, but D1 misses: an inefficiency in the small detector.</td>
    <td align="center"><strong>Given NO / Numerator YES</strong><br>T2 fails to fire so the trigger condition is false, yet D1 still fires: an edge case where the numerator is true even though its given condition is not.</td>
  </tr>
</table>

## Configuration

The engine is configured through YAML.

<details>
<summary><strong>Minimal field overview</strong></summary>

- `seed`: fixed integer seed, or `null` to derive it from local time
- `source_model`: particle source; one of `cosmic`, `beam`, or `object` (see
  below)
- `monte_carlo.n_events`: number of generated events
- `detectors`: list of detector volumes
- `logic.expressions`: boolean detector expressions to evaluate as rates
- `logic.conditional`: conditional probabilities to report
- `output`: CLI formatting settings
- `gui`: optional GUI-only settings

</details>

<details>
<summary><strong>Detector fields</strong></summary>

Each detector entry must contain:

- `name`: unique detector name used in logic expressions
- `center`: `[x, y, z]`
- `size`: `[dx, dy, dz]`
- `efficiency`: number between `0` and `1`

</details>

<details open>
<summary><strong>Source models</strong></summary>

`source_model.type` selects one of three particle sources. Only one source
is active per run.

### `cosmic`
Downward cosmic-ray-like flux, sampled from a `cos^2(theta)`
sky intensity law. The configured `flux_hz_per_cm2` is the real total
downward plane flux through a horizontal area, so enlarging the auxiliary
simulation sphere does not change the physical detector rate by itself:

```yaml
source_model:
  type: cosmic
  model: cos2           # only supported model today
  flux_hz_per_cm2: 0.01 # real downward plane flux through a horizontal area
```

<details>
<summary><strong>math detail</strong></summary>

The user provides the physical plane flux \(F\) in `Hz/cm^2`, integrated
over the full downward hemisphere.

For the built-in `cos2` model, the sky intensity is
\(I(\theta) \propto \cos^2\theta\), but tracks crossing a horizontal area
must also be weighted by the projected-area factor \(\cos\theta\) and by
the solid-angle Jacobian \(\sin\theta\). The sampled zenith distribution is
therefore:

\[
p(\theta) = 3 \cos^2\theta \sin\theta, \qquad 0 \le \theta \le \frac{\pi}{2}.
\]

Sampling uses an enclosing sphere around the detector stack. For each
direction, the code chooses a point uniformly on the disk perpendicular to
that direction and tangent to the sphere, then back-propagates to the entry
point on the sphere surface. This reproduces the same crossing statistics as
the real sky flux while keeping the generation volume finite.

If the enclosing sphere radius is \(R\), the generated entry rate is:

\[
R_\mathrm{gen} = \frac{4}{3}\pi R^2 F.
\]

</details>

### `beam`
A directed beam traveling in `+z` (`z` increases going
downstream, entering from the detector stack's lowest-`z` face), with a
transverse spatial profile:

```yaml
source_model:
  type: beam
  profile: uniform      # uniform | gaussian (divergence is rejected: not yet implemented)
  center: [0.0, 0.0]    # xc, yc
  size: [8.0]           # uniform: [diameter]; gaussian: [FWHM_x, FWHM_y]
  flux_hz_per_cm2: 50.0 # uniform: the flux; gaussian: average over the FWHM ellipse
```

Selecting `beam` also changes the GUI's default startup view: the `yz`
plane becomes the horizontal ground plane (beam entering from the side)
with `x` pointing up, instead of the usual `z`-up view.

<details>
<summary><strong>math detail</strong></summary>

For `profile: uniform`, origins are sampled uniformly over a disk of
diameter `size[0]`, so the total beam rate is:

\[
R_\mathrm{gen} = \Phi \, \pi \left(\frac{d}{2}\right)^2
\]

with \(\Phi =\) `flux_hz_per_cm2`.

For `profile: gaussian`, `size` means `[FWHM_x, FWHM_y]` and the code uses
\(\sigma = \mathrm{FWHM} / (2\sqrt{2\ln 2})\). The user-provided
`flux_hz_per_cm2` is interpreted as the average flux over the FWHM ellipse:

\[
A_\mathrm{FWHM} = \pi \frac{\mathrm{FWHM}_x}{2}\frac{\mathrm{FWHM}_y}{2}.
\]

An independent 2D Gaussian has exactly half of its total population inside
that ellipse, so the total rate is:

\[
R_\mathrm{gen} = 2 \, \Phi \, A_\mathrm{FWHM}.
\]

Sampling is truncated at \(5\sigma\) in the transverse plane: the code keeps
drawing from the Gaussian until the sampled point lies inside the
\(5\sigma\) ellipse. The discarded tail is about \(e^{-25/2} \approx
3.7\times 10^{-6}\) of the total population, so this cutoff is negligible
for this toy Monte Carlo while giving a hard finite bound for the GUI.

</details>

### `object`
A mounted one-sided radioactive disk source. Emission points
are sampled on the disk surface and directions are sampled only into the
forward hemisphere defined by `normal`:

```yaml
source_model:
  type: object
  center: [0.0, 0.0, 20.0]    # xc, yc, zc
  diameter: 2.0               # emitting disk diameter
  normal: [0.0, 0.0, -1.0]    # emitting side; normalized internally if needed
  angular_model: uniform      # uniform | cosine-weighted | material-dependent (not yet implemented)
  activity_bq: 100000.0       # intrinsic source activity from the datasheet/certificate
  yield_per_decay: 1.0        # optional; defaults to 1.0
  # surface_emission_rate_hz: 50000.0  # optional authoritative override
```

`object` sources are rendered in the GUI using `gui.source_color` /
`gui.source_opacity` (defaults: `orange`, `0.25`).

`activity_bq` means intrinsic source activity, not necessarily the actual
front-side particle emission rate. Datasheets sometimes report both, and
they are not always equal. If only `activity_bq` is provided, the engine
derives the front emission rate with the simple toy-MC assumption:

- one relevant particle per decay
- isotropic microscopic emission
- perfect backing

That gives `front emission = 0.5 * activity_bq * yield_per_decay`.
If `surface_emission_rate_hz` is present, it overrides the derived value.

<details>
<summary><strong>math detail</strong></summary>

Let \(\hat{n}\) be the normalized `normal` vector. The source position is
sampled uniformly on the disk surface:

\[
r = R\sqrt{u}, \qquad \phi \sim U(0, 2\pi),
\]

with \(R = \) `diameter / 2`.

Directions are always emitted into the forward hemisphere,
\(\hat{d}\cdot\hat{n} > 0\).

For `angular_model: uniform`, the hemisphere is sampled uniformly:

\[
\cos\theta \sim U(0, 1).
\]

For `angular_model: cosine-weighted`, the emission is Lambert-like:

\[
p(\theta) = 2\cos\theta\sin\theta, \qquad \cos\theta = \sqrt{u}.
\]

If `surface_emission_rate_hz` is not provided, the toy model derives the
front emission rate as:

\[
R_\mathrm{front} = 0.5 \times \texttt{activity\_bq} \times \texttt{yield\_per\_decay}.
\]

</details>

</details>


## Logic and Conditionals

<details>
<summary><strong>How to setup the trigger and detector logic </strong></summary>

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

<details>
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
python3 scripts/run_toymc.py configs/example_cosmic.yaml
```

</details>

## Tests

<details>
<summary><strong>Run the test suite</strong></summary>

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

</details>
