# ohc_ohca_ohu_emitter

`ohc_ohca_ohu_emitter` combines mapped-layer `ohc_derive` outputs into **combined depth layers** and
exports the annual **OHCA** (ocean heat content anomaly) and **OHU** (ocean heat uptake) deliverable
— one NetCDF per level: `ohca_ohu_<lo>_<hi>_dbar_<tag>.nc`.

```
ohc_ingest ─▶ publish ─▶ ohc_derive (integral,integral_anom,integral_tendency,area) ─▶ ohc_ohca_ohu_emitter ─▶ per-level .nc
```

It's the sibling of `ohc_gcos_emitter`: same synthetic layers, same shallowest-first `n_fac`
combination, same yearly-member-spread SD. The differences are the quantities (`ohca`/`ohu` vs
GCOS's J/m²/ZJ/temp), the per-level file layout, a `time_ohca` axis (days since 2004-06-01) rather
than `years`, and the baseline: by default the anomaly is the whole-record mean referenced upstream
in derive, with `--time-window` as an optional GCOS-style baseline/trend window (off by default).

> **Units:** output matches the target (Zenodo 14720478 v4.0.0) — **`ohca` in J/m²**, **`ohu` in
> W/m²** (per-area *densities*; the W/m² and W/m²/s in the file are the *trend* attributes). The
> combine works in basin-integrated TJ, so the export divides by the reference area and scales
> (`ohca = ohca[TJ]/area × 1e12`; `ohu = ohu[TJ/mo]/area × 1e12 / sec_per_month`, using a **round
> 30-day month** = 360-day year to match the target — their OHU is 1.0146× a `365.25/12` month).

## What it computes

Combination happens on the already-integrated 1-D series, never on grids. Each mapped layer's
`ohc_derive` output hands over `ohc_integral_anom(time)` (OHCA, TJ) and `ohc_integral_tendency(time)`
(OHU, TJ; month-to-month change, NaN at t0), plus the scalar `area_total`. For a combined layer whose
contributors are listed shallowest-first (in `layers.py`):

```
OHCA_L(t) = Σᵢ n_facᵢ · OHCAᵢ(t)          # TJ
OHU_L(t)  = Σᵢ n_facᵢ · OHUᵢ(t)           # TJ
area_L    = area_total of the shallowest contributor
```

Both combinations are linear, so `n_fac` weighting applies identically to OHCA and OHU. The
**export** annual-means each combined series, converts to per-area densities (`ohca` J/m², `ohu`
W/m² — divide by the reference area, scale TJ→J, and for `ohu` also / seconds-per-month), and writes
`ohca`/`ohu` (+ optional `_std`) per level on a `time_ohca` axis. By default `ohca` keeps its
whole-record mean referencing from upstream (`integral_anom`); `--time-window YEAR0:YEAR1`
re-references it to that period's mean and fits the OHCA/OHU trends over those years (the full
series is still reported — see below).

**Error bars.** If the derive inputs carried the ensemble (`--keep-members integral,integral_tendency`),
each value gets a `*_std`: per layer, the ensemble std of the **yearly** value (yearly-mean per
member, then std across members, ddof=1), combined by the same `n_fac` weights as a worst-case linear
sum. All-or-nothing — a missing contributor ensemble errors loudly rather than dropping a term. Note
the OHCA spread is taken from the **absolute** integral members (`ohc_integral_ens`), not the anomaly
members — see the opinionated choice below.

**Trend.** Each `ohca`/`ohu` variable carries a `trend` attribute — an OLS linear slope of the
annual series (central from the mean field), per second: `trend` on `ohca` is W/m², on `ohu` is
W/m²/s (mirroring the original's per-second-up trend units). With the ensemble, a `trend_std` attr
is the std across members of the per-member slopes, combined by the same linear `n_fac` weights.
Matches the original (`WMO2024_lsf_trend` yearly OLS, 365-day year; `create_eval_string_trend[_uq]`).

## Combined layers (config)

The combined-layer table lives in [`layers.py`](layers.py) — a **verbatim duplicate** of the GCOS
emitter's, by decision (edit both until a third consumer earns extracting a shared module). Current:
`0_300`, `0_700`, `0_1000`, `700_2000`, `0_2000`. `--levels` selects a subset per run.

## Usage

### Test
```bash
docker image build -t ohc_ohca_ohu_emitter:test .
docker container run -v $(pwd):/app ohc_ohca_ohu_emitter:test pytest
```

### Run
```bash
python combine.py DERIVE_*.nc --tag OHCA-OHU-2026-<run> [--provenance-link URL] [--time-window 2005:2024] [--levels ...] [--out DIR]
```

#### combine.py options

| option | default | effect |
|---|---|---|
| `DERIVE_*.nc` (positional, 1+) | *(required)* | the `ohc_derive` outputs, one per mapped layer, built with `--transforms integral,integral_anom,integral_tendency,area` (add `--keep-members integral,integral_tendency` for `*_std`). |
| `--tag` | *(required)* | provenance tag: whitespace-stripped (case preserved, no other munging) into the filenames and the `description`, and written to the `provenance_tag` header attr (pointer to the provenance record). Must match the provenance record char-for-char. |
| `--provenance-link` | *(none)* | URL/path to the provenance record; written to the `provenance_link` header attr. |
| `--levels` | all in `layers.py` | comma list of combined levels to emit. |
| `--time-window` | *(all years)* | `YEAR0:YEAR1` inclusive window applied to **both** the OHCA anomaly baseline and the OHCA/OHU trend fits (e.g. `2005:2024`). The full annual series is still reported — the window only sets the reference level and the trend-fit years; OHU has no baseline (it's a tendency), so only its trend is affected. Recorded in the `time_window` header attr. Default (omitted) = whole record, i.e. the validated Zenodo-matching form. |
| `--collaborators` | `LocalGP by Giglio, Sukianto, Kuusela, Mills` | `description` suffix. |
| `--reference` | `shallowest` | combined-layer reference area; only `shallowest` is implemented. |
| `--out` | `.` | output directory (created if absent). |

## Opinionated choices

- **Baseline window is opt-in.** By default `ohca` keeps its whole-record mean referencing from
  upstream (`integral_anom`) — no window — which is the form validated against the Zenodo target.
  (We briefly guessed a GCOS-style window early on to explain the target being smaller, but the real
  gap was units, so the default stays whole-record.) `--time-window YEAR0:YEAR1` opts into a GCOS-style
  baseline over that period **and** fits the OHCA/OHU trends over it; the full series is still
  reported. A window is a deliberate departure from the Zenodo-matching default — the reported OHCA
  and trends will differ, by design.
- **Error bars are a worst-case linear sum**, `n_fac`-weighted across contributors and treated as
  fully correlated — matching the GCOS convention. All-or-nothing.
- **OHCA spread ← absolute integral members** (`ohc_integral_ens`), while the value is the anomaly.
  Reproduces the original's `data_yearly_std` (std of the raw yearly integral). The anomaly members
  can't be used: `integral_anom` demeans each member by its own time-mean, removing the
  between-member level spread. (OHU and the trends are unaffected — a difference and a slope are both
  offset-invariant.)
- **Reference area = shallowest contributor**, same `reference=shallowest` policy as GCOS; the
  bottom-must-be-wet alternative needs gridded masks and is a deliberate `NotImplementedError`.
- **Trends are attributes**, not variables — an OLS slope + `trend_std` per `ohca`/`ohu`, mirroring
  the target where the trend is a per-variable attr. Fit convention matches the original (yearly OLS,
  365-day year, member-slope spread).
- **Fill value `-999`** (the target's), applied on write to every data variable — so `ohu`'s NaN
  first year (no prior month) lands as `-999`.

## Open (reproduction-time) details

Reconcile against the target (Zenodo 14720478 v4.0.0):

- **OHU seconds-per-month = round 30-day month** (= 360-day year), matching the target — *not*
  derive's `365.25/12` trend-axis month. This is the one target-matching magic number; the target's
  OHU is 1.0146× a `365.25/12` month, constant across years, so a fixed 30-day month is the fit.
  (`ohca` is unaffected.)
- **t0 / partial-year** handling for OHU (NaN at t0 vs a dropped first year). The **anomaly baseline**
  is whole-record by default (matching the target); if a specific reference period is wanted, pass
  `--time-window` (which also windows the trend fits).

The combine-and-annualize core is agnostic to all of this; it's output formatting.
