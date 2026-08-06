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
import xarray as xr


def _yearly(series):
    """Monthly (time,) series -> calendar-year mean (year,), float64."""
    return series.astype("float64").groupby("time.year").mean("time")


def build_level_dataset(cl, tag, collaborators):
    """One combined level's result -> an xr.Dataset over `years` with OHCA, OHU (+ optional `_sd`)."""
    ohca_yr = _yearly(cl["ohca"])
    ohu_yr = _yearly(cl["ohu"])
    years = ohca_yr["year"].values.astype("int64")

    dv = {
        "OHCA": xr.DataArray(ohca_yr.values, dims=("years",),
                             attrs={"units": "TJ", "long_name": "annual OHC anomaly (all-time mean removed)",
                                    "area_m2": cl["area"]}),
        "OHU": xr.DataArray(ohu_yr.values, dims=("years",),
                            attrs={"units": "TJ per month", "long_name": "annual mean ocean heat uptake",
                                   "area_m2": cl["area"]}),
    }
    if cl["ohca_sd_yearly"] is not None:
        note = "worst-case ensemble 1-sigma: linear n_fac-weighted sum of per-layer yearly SDs"
        dv["OHCA_sd"] = xr.DataArray(cl["ohca_sd_yearly"].sel(year=years).values, dims=("years",),
                                     attrs={"units": "TJ", "comment": note})
        dv["OHU_sd"] = xr.DataArray(cl["ohu_sd_yearly"].sel(year=years).values, dims=("years",),
                                    attrs={"units": "TJ per month", "comment": note})

    out = xr.Dataset(dv, coords={"years": ("years", years.astype("float64"))})
    out.attrs["level"] = cl["name"]
    out.attrs["description"] = "%s, %s" % (tag, collaborators)
    return out


def filename(cl, tag):
    """Target-style per-level name: ohca_ohu_<lo>_<hi>_dbar_<tag>.nc"""
    return "ohca_ohu_%d_%d_dbar_%s.nc" % (cl["low"], cl["high"], tag.lower().replace(" ", ""))
