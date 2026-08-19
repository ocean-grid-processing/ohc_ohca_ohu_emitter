#!/usr/bin/env python3
"""OHCA/OHU packaging: one ohc_derive blob -> the target per-area deliverable.

The factory has already done the analysis — the n_fac cross-layer combine, the annual means, the OHCA
baseline window, and the OLS trends. Its blob carries `ohca`/`ohu` (with their `_sd` and trends) as
basin-integrated extensive quantities (TJ, and TJ per month), plus `area_m2`, the `level`, and the
`time_window` it was built with. This step is only the packaging: divide by the area, carry the units
to the target's per-area densities, relabel, and write one file per level.

Target (Zenodo 14720478 v4.0.0): `ohca` in J/m2 and `ohu` in W/m2 on a `time_ohca` axis (days since
2004-06-01, each year anchored at its 1-June), with the linear trends as attrs on each variable.

OHU's first year arrives NaN from the factory (its leading tendency step is undefined, so that year is
voided upstream and excluded from the trend); it carries through here and lands as -999 on write.
"""
import argparse
import os

import numpy as np
import pandas as pd
import xarray as xr

EPOCH = "2004-06-01"        # time_ohca reference; each year anchored at its 1-June
TERA = 1e12                 # TJ -> J
# OHU per-month -> per-second: a round 30-day month (a 360-day year), matching the target's convention.
SEC_PER_MONTH = 30.0 * 86400.0
# Trend per year-step -> per-second: a 365-day year, matching the target's trend axis.
SEC_PER_YEAR = 365.0 * 86400.0
SEC_PER = {"year": SEC_PER_YEAR, "month": SEC_PER_MONTH}


def _trend_seconds(trend_var):
    """Seconds in one step of a trend's cadence, read from its `per` attr (default year)."""
    return SEC_PER[trend_var.attrs.get("per", "year")]


def to_jm2(tj, area):
    """Basin-integrated TJ -> per-area J/m2."""
    return tj / area * TERA


def to_wm2(tj_per_month, area):
    """Basin-integrated TJ per month -> per-area W/m2."""
    return tj_per_month / area * TERA / SEC_PER_MONTH


def _time_ohca(years):
    """Integer years -> days since EPOCH, each year anchored at its 1-June."""
    ref = pd.Timestamp(EPOCH)
    days = np.array([(pd.Timestamp("%d-06-01" % y) - ref).days for y in years], dtype="float64")
    return xr.DataArray(days, dims=("time_ohca",),
                        attrs={"units": "days since %s 00:00:00" % EPOCH,
                               "calendar": "proleptic_gregorian", "long_name": "time"})


def build_dataset(blob, tag, provenance_link):
    """A derive blob -> the OHCA/OHU deliverable Dataset over `time_ohca`."""
    area = float(blob.attrs["area_m2"])
    window = blob.attrs.get("time_window", "all")
    baseline = "all-time mean" if window == "all" else "%s mean" % window

    time = _time_ohca(blob["ohca"]["year"].values.astype("int64"))
    dv = {
        "ohca": xr.DataArray(to_jm2(blob["ohca"].values, area), dims=("time_ohca",),
                             attrs={"units": "J/m2", "area_m2": area,
                                    "long_name": "annual OHC anomaly (%s removed)" % baseline}),
        "ohu": xr.DataArray(to_wm2(blob["ohu"].values, area), dims=("time_ohca",),
                            attrs={"units": "W/m2", "area_m2": area,
                                   "long_name": "annual mean ocean heat uptake"}),
    }
    if "ohca_sd" in blob:
        note = "worst-case ensemble 1-sigma: n_fac-weighted sum of the per-constituent SDs"
        dv["ohca_std"] = xr.DataArray(to_jm2(blob["ohca_sd"].values, area), dims=("time_ohca",),
                                      attrs={"units": "J/m2", "comment": note})
        dv["ohu_std"] = xr.DataArray(to_wm2(blob["ohu_sd"].values, area), dims=("time_ohca",),
                                     attrs={"units": "W/m2", "comment": note})

    # Linear trends as attrs, per second: the trend's `per` attr picks the seconds in one step.
    if "ohca_trend" in blob:
        sec = _trend_seconds(blob["ohca_trend"])
        dv["ohca"].attrs.update({"trend": to_jm2(float(blob["ohca_trend"]), area) / sec, "trend_units": "W/m2"})
        if "ohca_trend_sd" in blob:
            dv["ohca"].attrs["trend_std"] = to_jm2(float(blob["ohca_trend_sd"]), area) / sec
    if "ohu_trend" in blob:
        sec = _trend_seconds(blob["ohu_trend"])
        dv["ohu"].attrs.update({"trend": to_wm2(float(blob["ohu_trend"]), area) / sec, "trend_units": "W/m2/s"})
        if "ohu_trend_sd" in blob:
            dv["ohu"].attrs["trend_std"] = to_wm2(float(blob["ohu_trend_sd"]), area) / sec

    out = xr.Dataset(dv, coords={"time_ohca": time})
    out.attrs["level"] = blob.attrs["level"]
    out.attrs["time_window"] = window
    out.attrs["provenance_tag"] = tag
    if provenance_link is not None:
        out.attrs["provenance_link"] = provenance_link
    return out


def filename(level, tag):
    """Target-style per-level name: ohca_ohu_<lo>_<hi>_dbar_<tag>.nc (low/high from the level)."""
    low, high = level.split("_")
    return "ohca_ohu_%s_%s_dbar_%s.nc" % (low, high, tag)


def main():
    ap = argparse.ArgumentParser(description="OHCA/OHU packaging: ohc_derive blob -> target deliverable")
    ap.add_argument("blobs", nargs="+", help="ohc_derive output NetCDFs (derive_<tag>_<level>.nc)")
    ap.add_argument("--tag", required=True, help="provenance tag: filename token + provenance_tag attr")
    ap.add_argument("--provenance-link", default=None, help="URL/path to the provenance record")
    ap.add_argument("--out", default=".")
    cfg = ap.parse_args()
    os.makedirs(cfg.out, exist_ok=True)
    for path in cfg.blobs:
        blob = xr.open_dataset(path)
        if "ohca" not in blob or "ohu" not in blob:
            raise SystemExit("%s carries no ohca/ohu; run ohc_derive with --quantities ohca,ohu (+ trends)"
                             % path)
        dest = os.path.join(cfg.out, filename(blob.attrs["level"], cfg.tag))
        out = build_dataset(blob, cfg.tag, cfg.provenance_link)
        enc = {v: {"_FillValue": -999.0} for v in out.data_vars}   # target fill (NaN -> -999)
        out.to_netcdf(dest, engine="netcdf4", encoding=enc)
        print("wrote", dest)


if __name__ == "__main__":
    main()
