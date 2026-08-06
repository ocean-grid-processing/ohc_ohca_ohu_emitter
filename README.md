# ohc_ohca_ohu_emitter

`ohc_ohca_ohu_emitter` combines mapped-layer `ohc_derive` outputs into **combined depth layers** and
exports the annual **OHCA** (ocean heat content anomaly) and **OHU** (ocean heat uptake) deliverable
— one NetCDF per level: `ohca_ohu_<lo>_<hi>_dbar_<tag>.nc`.

```
ohc_ingest ─▶ publish ─▶ ohc_derive (integral_anom,integral_tendency,area) ─▶ ohc_ohca_ohu_emitter ─▶ per-level .nc
```

It's the sibling of `ohc_gcos_emitter`: same synthetic layers, same shallowest-first `n_fac`
combination, same yearly-member-spread SD. The differences are the quantities (OHCA/OHU vs GCOS's
J/m²/ZJ/temp) and, crucially, **no baseline window** — OHCA is already referenced to its whole-record
mean upstream, so this emitter just annualizes.

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

Both combinations are linear, so `n_fac` weighting applies identically to OHCA and OHU. Because OHCA
is already a whole-record anomaly per layer and the mean is linear, the combined OHCA is the correct
anomaly of the combined integral — no re-referencing. The **export** then takes the annual mean of
each combined series and writes it per level.

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

- **No baseline window.** OHCA is anomaly-referenced upstream (`integral_anom`, whole-record mean);
  this emitter never subtracts a window. That's the deliberate difference from the GCOS emitter.
- **Error bars are a worst-case linear sum**, `n_fac`-weighted across contributors and treated as
  fully correlated — matching the GCOS convention. All-or-nothing.
- **Reference area = shallowest contributor**, same `reference=shallowest` policy as GCOS; the
  bottom-must-be-wet alternative needs gridded masks and is a deliberate `NotImplementedError`.

## Open (reproduction-time) details

Deliberately not pinned in this backbone — reconcile against the target (Zenodo 14720478 v4.0.0):
the reported **units** (OHCA as TJ / J·m⁻² / ZJ; OHU as per-month TJ vs a per-second W·m⁻² flux),
the exact **variable names** and file layout, the **anomaly baseline convention** (monthly all-time
mean, as `integral_anom` gives, vs a mean over the annual series), and the **t0 / partial-year**
handling for OHU. The combine-and-annualize core is agnostic to these; they're output formatting.
