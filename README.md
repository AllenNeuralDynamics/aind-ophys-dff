# aind-ophys-dff

This capsule calculates $\Delta F/F$ from neuropil-corrected fluorescence traces. Two algorithms
are available, selected via `--method` (default: `triexp`):

### `triexp` (default)

A parametric 3-pass triexponential baseline fit, delegated to `aind-ophys-dff-library`'s
`triexp_dff`. Configured via:
- `sigma_anneal_steps`: IRLS sigma-annealing steps for the nonlinear fit. `1` (default) or `2`
  disable annealing (single-jump); `3` enables one intermediate step; `4` uses two; higher
  graduates further but exceeds the internal `maxiter=5`.
- `triexp_config_overrides`: a JSON object overriding `set_dff_config`'s keyword arguments
  (other than `sigma_anneal_steps`, which has its own field above); any key omitted falls back
  to that function's default.

If triexp's main fit fails to converge for a given ROI, it falls back to
`aind_ophys_utils.dff.dff()` (the same function backing `percentile` mode below) for that ROI
only -- using its own `fallback_long_window` setting from `set_dff_config`/
`triexp_config_overrides`, not this capsule's `--long_window`/`--short_window`/etc. flags, which
only apply when `method='percentile'`.

### `percentile`

Uses the `dff` function from `aind-ophys-utils`, which executes the following steps:
- Estimate the noise standard deviation $\sigma$ and initial baseline $b$
- Mask active frames, i.e. outliers where $F > b + 3\sigma$
- Obtain $F_0$ by median-filtering the trace using only inactive frames and interpolation
- Calculate $\Delta F/F = (F - F_0) / F_0$

Configured via:
- `long_window`: percentile baseline window, in seconds (default `60.0`)
- `short_window`: short detrending window, in seconds (default `3.333`)
- `inactive_percentile`: inactive percentile used to estimate $F_0$ (default `10`)
- `noise_method`: noise estimator, one of `mad`, `fft`, `welch` (default `mad`)

## Input

All parameters are passed to `dff.py` using `python dff.py [parameters]`, parsed via
`pydantic-settings` (see `DFFSettings` in `dff.py` for the full list and defaults). The most
important one is `input_dir`, which should point to a directory containing an HDF5 file
`extraction.h5` with the dataset `traces/corrected`, a 2D array of neuropil-corrected traces for
each ROI.

## Output

The main output is the `dff.h5` file.
It contains 4 datasets:

`data`: Baseline-corrected fluorescence traces $\Delta F/F$  
`baseline`: Estimated baselines $F_0$  
`noise`:  Estimated standard deviation of the noise in the input traces  
`skewness`:  The skewness of the $\Delta F/F$ traces
