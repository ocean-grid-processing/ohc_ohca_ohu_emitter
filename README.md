# ohc_ohca_ohu_emitter

`ohc_ohca_ohu_emitter` packages one `ohc_derive` blob into the annual **OHCA** (ocean heat content
anomaly) and **OHU** (ocean heat uptake) deliverable — one NetCDF per level,
`ohca_ohu_<lo>_<hi>_dbar_<tag>.nc`.

```
ohc_ingest ─▶ publish ─▶ ohc_derive (--quantities ohca,ohu,ohca_trend,ohu_trend) ─▶ ohc_ohca_ohu_emitter ─▶ per-level .nc
```

The analysis is all upstream now. `ohc_derive` does the `n_fac` cross-layer combine, the annual means,
the OHCA baseline window, the OLS trends, and the ensemble → SD collapse. Its blob hands over
`ohca`/`ohu` (with their `_sd` and trends) as **basin-integrated extensive** quantities (TJ, and TJ per
month), plus `area_m2`, the `level`, and the `time_window` it was built with. This emitter is only the
packaging: divide by the area, carry the units to the target's per-area densities, relabel, and write.

> **Units:** output matches the target (Zenodo 14720478 v4.0.0) — **`ohca` in J/m²**, **`ohu` in
> W/m²** (per-area densities; the W/m² and W/m²/s on the `trend` attrs are the trends). Conversions:
> `ohca = ohca[TJ]/area × 1e12`; `ohu = ohu[TJ/mo]/area × 1e12 / sec_per_month`, using a **round
> 30-day month** (= 360-day year) to match the target (their OHU is 1.0146× a `365.25/12` month);
> trends divide by a 365-day year to reach per-second.

## What it computes

Per blob (one synthetic level):

```
ohca(t) = blob.ohca / area_m2 × 1e12                    # J/m²
ohu(t)  = blob.ohu  / area_m2 × 1e12 / sec_per_month    # W/m²
*_std   = the matching blob.*_sd, same conversion       # present when the ensemble was on
```

The values ride a `time_ohca` axis — days since 2004-06-01, each year anchored at its 1-June — built
from the blob's `year` coord. The `low`/`high` in the filename come from the blob's `level` attr; the
OHCA baseline label comes from its `time_window`.

**Trends.** `ohca_trend`/`ohu_trend` (and their `_sd`) are hung on the `ohca`/`ohu` variables as
`trend` / `trend_units` / `trend_std` attrs, converted per-second: `trend` on `ohca` is W/m², on `ohu`
is W/m²/s.

**OHU first year.** OHU's first year is an 11-month partial (its t0 tendency has no prior month). The
factory averaged it and fit the trend including it; this emitter blanks that first year to NaN for
presentation only — the trend is unchanged.

## Building the input

`ohc_ohca_ohu_emitter` consumes one `ohc_derive` blob per synthetic level. To match the Zenodo target,
build them with the whole-record baseline — i.e. **no `--time-window`** (the 2005:2024 window is
GCOS-only) — and the ensemble on:

```bash
python ../ohc_derive/run.py OHC_<constituents>.nc \
    --level 0_2000 --bathy etopo60.nc --quantities ohca,ohu,ohca_trend,ohu_trend \
    --tag <tag> --out <dir>
```

Each blob **must** carry:

- data vars **`ohca`** and **`ohu`** (annual, extensive); **`ohca_trend`** / **`ohu_trend`** (each with
  a `per` attr) for the trend attributes; and the `_sd` companions when the derive run kept the
  ensemble. The emitter errors if `ohca`/`ohu` are absent, and skips the trend/`_sd` outputs that
  aren't present.
- attrs **`area_m2`**, **`level`**, and **`time_window`** (which becomes the OHCA baseline label).

`cp0`/`rho0` are not used here (they're a GCOS thing), so they need not be present.

## Usage

### Test
```bash
docker image build -t ohc_ohca_ohu_emitter:test .
docker container run -v $(pwd):/app ohc_ohca_ohu_emitter:test pytest
```

### Run
```bash
python emit.py derive_<tag>_<window>_<level>.nc [more levels …] --tag <tag> --code-version URL \
    [--provenance-link URL] [--out DIR]
```

One blob in, one deliverable out, per level. Run `ohc_derive` first with at least `--quantities
ohca,ohu` (add `ohca_trend,ohu_trend` for the trend attrs; run without `--no-ensemble` for the `_std`
companions).

**Provenance chain.** Since each deliverable is built from one derive blob, this step is a 1-in-1-out
courier: it rolls that blob's whole provenance chain forward untouched — every `*_run_config` /
`*_run_facts` / `*_code_version` (the grouped `localgp_ingest_*` / `localgp_publish_*` and the
`ohc_derive_*` blocks) as opaque JSON strings — and adds its own `ohc_ohca_ohu_emitter_run_config`
(resolved args), `ohc_ohca_ohu_emitter_run_facts` (level, window, area, quantities, source blob), and
`ohc_ohca_ohu_emitter_code_version`. The global `provenance_tag` / `provenance_link` are this step's own.

#### emit.py options

| option | default | effect |
|---|---|---|
| `derive_*.nc` (positional, 1+) | *(required)* | `ohc_derive` blobs, one per synthetic level (`derive_<tag>_<window>_<level>.nc`). Each must carry `ohca` and `ohu`. Point at the whole-record window (no `--time-window`), not gcos's 2005-2024. |
| `--tag` | *(required)* | run token in the filename (`ohca_ohu_<lo>_<hi>_dbar_<tag>.nc`) and the `provenance_tag` attr. Used verbatim; should match the tag the blob was derived under. |
| `--provenance-link` | *(none)* | URL/path to the provenance record; written to the `provenance_link` attr. |
| `--code-version` | *(required)* | URL to the exact ohc_ohca_ohu_emitter code (commit/release); written to the `ohc_ohca_ohu_emitter_code_version` attr. |
| `--out` | `.` | output directory (created if absent). |

## Notes

- The **30-day-month** OHU conversion is the one target-matching magic number (their OHU is a constant
  1.0146× a `365.25/12` month); `ohca` is unaffected.
- **Trends are attributes**, not variables, mirroring the target's per-variable `trend` attr.
- **Fill value `-999`** (the target's) on every data variable on write, so the blanked OHU first year
  lands as `-999` on disk (and decodes back to NaN on read).
- **Annual means are calendar-year** upstream (`ohc_derive` groups by `time.year`), and are stamped
  here at 1-June. Whether the target's annual value is a calendar year or a June-centered year is not
  yet confirmed against the target file — `parity.py` is the place to check the `time_ohca` offset.
- `python parity.py OURS.nc THEIRS.nc` compares one level against the target (Zenodo 14720478 v4.0.0)
  on the shared `time_ohca`, bridging the `area`/`area_m2` and string-vs-numeric trend differences.
