"""OHCA/OHU annual export: yearly mean of the combined series + ensemble SDs, one file per level.

No baseline windowing. OHCA arrives already referenced to its whole-record mean (ohc_derive's
`integral_anom`), so annualizing it is the whole job — unlike the GCOS emitter, there is no
2005-2024 window to subtract here. OHU is the annual mean of the monthly tendency (the NaN at t0
drops out of the first year's mean by skipna). Each value gets a `*_sd` companion when the derive
inputs carried the ensemble.

Open reproduction details to reconcile against the Zenodo 14720478 target (deliberately not pinned
in this backbone): the reported units (TJ vs J/m^2 vs ZJ for OHCA; per-month vs per-second W/m^2 for
OHU), the exact variable names, and whether the anomaly baseline is the monthly all-time mean (as
`integral_anom` gives) or a mean of the annual series. The combine/annualize machinery below is
agnostic to those; they are output-formatting choices layered on top.
"""
import numpy as np
import pandas as pd
import xarray as xr

EPOCH = "2004-06-01"     # time_ohca reference; each year anchored at its 1-June


def _yearly(series):
    """Monthly (time,) series -> calendar-year mean (year,), float64."""
    return series.astype("float64").groupby("time.year").mean("time")


def _time_ohca(years):
    """Annual timestamps as days since EPOCH (each year anchored at its 1-June)."""
    ref = pd.Timestamp(EPOCH)
    days = np.array([(pd.Timestamp("%d-06-01" % y) - ref).days for y in years], dtype="float64")
    return xr.DataArray(days, dims=("time_ohca",),
                        attrs={"units": "days since %s 00:00:00" % EPOCH,
                               "calendar": "proleptic_gregorian", "long_name": "time"})


def build_level_dataset(cl, tag, collaborators, baseline):
    """One combined level's result -> an xr.Dataset over `time_ohca` with ohca, ohu (+ optional `_sd`)."""
    ohca_yr = _yearly(cl["ohca"])
    ohu_yr = _yearly(cl["ohu"])
    years = ohca_yr["year"].values.astype("int64")

    # GCOS-style baseline: subtract the window mean of the annual OHCA. OHCA already had its
    # whole-record mean removed upstream (integral_anom), so that all-time mean cancels here — this
    # is exactly windowing the raw integral, matching the GCOS emitter. (A guess: the target's much
    # smaller magnitude suggests it referenced to a window; no source to confirm.) The SD is NOT
    # baseline-subtracted — a constant offset leaves the member spread unchanged — matching GCOS.
    b0, b1 = baseline
    ohca_yr = ohca_yr - ohca_yr.sel(year=slice(b0, b1)).mean("year")

    time = _time_ohca(years)
    dv = {
        "ohca": xr.DataArray(ohca_yr.values, dims=("time_ohca",),
                             attrs={"units": "TJ", "area_m2": cl["area"],
                                    "long_name": "annual OHC anomaly (%d-%d baseline)" % (b0, b1)}),
        "ohu": xr.DataArray(ohu_yr.values, dims=("time_ohca",),
                            attrs={"units": "TJ per month", "area_m2": cl["area"],
                                   "long_name": "annual mean ocean heat uptake"}),
    }
    if cl["ohca_sd_yearly"] is not None:
        note = "worst-case ensemble 1-sigma: linear n_fac-weighted sum of per-layer yearly SDs"
        dv["ohca_sd"] = xr.DataArray(cl["ohca_sd_yearly"].sel(year=years).values, dims=("time_ohca",),
                                     attrs={"units": "TJ", "comment": note})
        dv["ohu_sd"] = xr.DataArray(cl["ohu_sd_yearly"].sel(year=years).values, dims=("time_ohca",),
                                    attrs={"units": "TJ per month", "comment": note})

    out = xr.Dataset(dv, coords={"time_ohca": time})
    out.attrs["level"] = cl["name"]
    out.attrs["baseline_years"] = "%d-%d" % (b0, b1)
    out.attrs["description"] = "%s, %s" % (tag, collaborators)
    return out


def filename(cl, tag):
    """Target-style per-level name: ohca_ohu_<lo>_<hi>_dbar_<tag>.nc"""
    return "ohca_ohu_%d_%d_dbar_%s.nc" % (cl["low"], cl["high"], tag.lower().replace(" ", ""))
