I want to create a toy Monte Carlo to simulate a cosmic ray stand.

This project is intentionally simple. It is a geometrical toyMC, not a full detector simulation. I do not want to model energy loss, interactions, multiple scattering, timing, or secondaries. That is why I am not using GEANT4.

# Goal
I want a reusable Python library, split into small modules, plus a small runner script.

The configuration should be stored in YAML so it is easy for a human to edit.

The first version only needs to print results to the terminal.

# Coordinate system and conventions
- `z` is the vertical axis.
- Cosmic rays come from `+z` toward `-z`.
- `phi` is uniform in `[0, 2*pi)`.
- `theta` is the zenith angle measured from the vertical downward direction.
- For the first version, use `theta_max = 80 deg`.

# Geometry
The stand is made of axis-aligned rectangular detector volumes.

Each detector is defined by:
- a unique name such as `T1`, `T2`, `D1`, ...
- center coordinates `(x, y, z)`
- sizes `(dx, dy, dz)`
- efficiency between `0` and `1`

Each detector occupies:
- `x in [x0 - dx/2, x0 + dx/2]`
- `y in [y0 - dy/2, y0 + dy/2]`
- `z in [z0 - dz/2, z0 + dz/2]`

I can add any number of detectors.

I do not care about overlapping detector volumes for now.

A detector is geometrically crossed only if the track has a non-zero path length inside the volume. A track that only touches a surface or an edge should not count as a crossing.

# Detector response
The detector response is instantaneous and binary.

After a geometric crossing, the detector fires with an independent Bernoulli extraction:
- draw a random number uniformly in `[0, 1)`
- if the number is smaller than the detector efficiency, the detector fires
- otherwise it does not fire

The response of different detectors must be independent.

# Track generation
Tracks represent cosmic rays and are straight lines.

I do not want to simulate energy or interactions. Only geometry matters.

The angular model for the first version can be based on `cos^2(theta)`, but the code should be structured so that the angular distribution can be replaced easily later.

The generation region in the `xy` plane should not depend on the logic expression being studied, because that could introduce bias.

Instead, the generation region should depend only on the detector geometry and on `theta_max`.

A good default is:
- take the global bounding box of all detectors in `x` and `y`
- enlarge it with a safety margin based on the total vertical extent of the setup and on `theta_max`

This should guarantee enough statistical coverage for all relevant intercept cases without introducing logic-dependent bias.

# Flux and rate normalization
The input cosmic flux is given in `Hz/cm^2` and should be interpreted as the total downward flux through a horizontal surface, already integrated over all downward angles.

The Monte Carlo must sample directions from a normalized angular PDF over the downward hemisphere, but the final normalization must ensure that:
- a horizontal area `A` sees a total rate `Phi * A`
- where `Phi` is the input flux in `Hz/cm^2`

In other words, the angular distribution controls how directions are populated, while the total rate normalization must remain consistent with the integrated flux definition.

# Logic and observables
I want detectors to be referenced by name.

I want Python-style logic expressions to be supported, for example:
- `T1 and T2 and T3 and not T4`

The code should support both:
- geometric logic, based on whether a detector volume was crossed
- fired logic, based on whether the detector fired after efficiency

These two concepts should remain explicitly separated in the API and in the printed results.

I want to estimate:
- geometric crossing rate for a single detector
- fired rate for a single detector
- rate of a logic expression of detectors
- conditional probabilities such as `P(D1 fires | T1 and T2 fire)`

# Statistical uncertainties
I want the Monte Carlo to report statistical uncertainties on the estimated quantities, so I can judge whether the finite sample size is sufficient.

# Randomness
The random seed can default to one based on the local PC time.

# Software structure
I want a reusable library organized into smaller modules rather than a single monolithic script.

A reasonable structure would be something like:
- geometry handling
- track generation
- detector response
- logic evaluation
- rate estimation
- YAML config loading
- a small runner script that prints the requested results

# Configuration
The YAML configuration should contain at least:
- detector definitions
- flux value
- angular model settings
- Monte Carlo settings such as number of events
- `theta_max`
- random seed options
- logic expressions to evaluate

# GUI / Visualization
I want a GUI that shows me the detectors:
- I can interact with the GUI, rotating the system (3D view).
- Detector color can be chosen (default is grey).
- Background color can be chosen (default is black).
- Optional event display, event by event: a track passing through a detector has 2 modes:
  - turn it green if the track passes and the detector is efficient (fires)
  - turn it red if the track passes and the detector is not efficient (does not fire)

# Explicit exclusions
Do not implement:
- energy loss
- material interactions
- multiple scattering
- detector timing
- secondaries
- GEANT4-like full simulation features
