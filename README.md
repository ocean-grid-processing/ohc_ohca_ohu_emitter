# ohc_ohca_ohu_emitter

`ohc_ohca_ohu_emitter` combines mapped-layer `ohc_derive` outputs into **combined depth layers** and
exports the annual **OHCA** (ocean heat content anomaly) and **OHU** (ocean heat uptake) deliverable
— one NetCDF per level: `ohca_ohu_<lo>_<hi>_dbar_<tag>.nc`.

```
ohc_ingest ─▶ publish ─▶ ohc_derive (integral_anom,integral_tendency,area) ─▶ ohc_ohca_ohu_emitter ─▶ per-level .nc
```

It's the sibling of `ohc_gcos_emitter`: same synthetic layers, same shallowest-first `n_fac`
combination, same yearly-member-spread SD. The differences are the quantities (`ohca`/`ohu` vs
GCOS's J/m²/ZJ/temp), the per-level file layout, a `time_ohca` axis (days since 2004-06-01) rather
than `years`, and no baseline window (the anomaly is referenced upstream in derive).

> **Units:** output matches the target (Zenodo 14720478 v4.0.0) — **`ohca` in J/m²**, **`ohu` in
> W/m²** (per-area *densities*; the W/m² and W/m²/s in the file are the *trend* attributes). The
> combine works in basin-integrated TJ, so the export divides by the reference area and scales
> (`ohca = ohca[TJ]/area × 1e12`; `ohu = ohu[TJ/mo]/area × 1e12 / sec_per_month`, idealized
> `365.25/12` month). Confirm the OHU seconds-per-month convention against the target if `ohu` is
> slightly off.

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
`ohca`/`ohu` (+ optional `_sd`) per level on a `time_ohca` axis. No baseline window — `ohca` is
already referenced to its whole-record mean upstream (`integral_anom`).

**Error bars.** If the derive inputs carried the ensemble (`--keep-members
integral_anom,integral_tendency`), each value gets a `*_sd`: per layer, the ensemble std of the
**yearly** value (yearly-mean per member, then std across members, ddof=1), combined by the same
`n_fac` weights as a worst-case linear sum. All-or-nothing — a missing contributor ensemble errors
loudly rather than dropping a term.

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
python combine.py DERIVE_*.nc --tag "OHCA-OHU 2026 <run>" [--levels ...] [--out DIR]
```

#### combine.py options

| option | default | effect |
|---|---|---|
| `DERIVE_*.nc` (positional, 1+) | *(required)* | the `ohc_derive` outputs, one per mapped layer, built with `--transforms integral_anom,integral_tendency,area` (add `--keep-members integral_anom,integral_tendency` for `*_sd`). |
| `--tag` | *(required)* | run tag; lowercased/space-stripped into the filenames and the `description`. |
| `--levels` | all in `layers.py` | comma list of combined levels to emit. |
| `--collaborators` | `LocalGP by Giglio, Sukianto, Kuusela, Mills` | `description` suffix. |
| `--reference` | `shallowest` | combined-layer reference area; only `shallowest` is implemented. |
| `--out` | `.` | output directory (created if absent). |

## Opinionated choices

- **No baseline window.** `ohca` is referenced to its whole-record mean upstream (`integral_anom`);
  this emitter doesn't subtract a window. (We briefly guessed a GCOS-style window to explain the
  target being smaller, but the real gap is units — see below — so the window was dropped.)
- **Error bars are a worst-case linear sum**, `n_fac`-weighted across contributors and treated as
  fully correlated — matching the GCOS convention. All-or-nothing.
- **Reference area = shallowest contributor**, same `reference=shallowest` policy as GCOS; the
  bottom-must-be-wet alternative needs gridded masks and is a deliberate `NotImplementedError`.

## Open (reproduction-time) details

Reconcile against the target (Zenodo 14720478 v4.0.0):

- **OHU seconds-per-month** convention: the export uses the idealized `365.25/12` month (same as
  derive's trend axis). If `ohu` is slightly off against the target, this is the first knob — the
  target may use each month's actual length instead. (`ohca` is unaffected.)
- **t0 / partial-year** handling for OHU (NaN at t0 vs a dropped first year), and the exact
  **anomaly baseline** convention if it turns out the target isn't a plain whole-record anomaly.

The combine-and-annualize core is agnostic to all of this; it's output formatting.
