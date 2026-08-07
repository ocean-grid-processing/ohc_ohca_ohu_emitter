"""OHCA/OHU annual export: yearly mean of the combined series + ensemble SDs, one file per level.

No baseline windowing. OHCA arrives already referenced to its whole-record mean (ohc_derive's
`integral_anom`), so annualizing it is the whole job — unlike the GCOS emitter, there is no
2005-2024 window to subtract here. OHU is the annual mean of the monthly tendency (the NaN at t0
drops out of the first year's mean by skipna). Each value gets a `*_sd` companion when the derive
inputs carried the ensemble.

Output is per-area densities to match the target (Zenodo 14720478 v4.0.0): `ohca` J/m², `ohu` W/m².
The combine works in basin-integrated TJ, so the export divides by the reference area (and scales
TJ->J, and OHU / seconds-per-month with a round 30-day month to match the target). Still to reconcile:
the exact variable names / file layout, and the t0 / partial-year handling for OHU.
"""
import numpy as np
import pandas as pd
import xarray as xr

EPOCH = "2004-06-01"     # time_ohca reference; each year anchored at its 1-June
TERA = 1e12              # TJ -> J
# OHU per-month -> per-second factor: a round 30-day month (= 360-day year), matching the target
# (their OHU is 30.4375/30 = 1.0146x a 365.25/12 month, constant across years). This is a
# target-matching convention and is deliberately NOT derive's 365.25/12 trend-axis month.
SEC_PER_MONTH = 30.0 * 86400.0
# Trend time axis: 365-day year, converting the OLS slope (per year-step) to per-second. Matches the
# original's yearly trend (bfr_vars_num_sec_in_tstep = 365*24*60*60) — note 365, not 365.25.
SEC_PER_YEAR = 365.0 * 86400.0


def _yearly(series, skipna=True):
    """Monthly (time,) series -> calendar-year mean (year,), float64.

    `skipna=False` makes any year with a missing month collapse to NaN — used for OHU so the first
    year (whose t0 tendency is NaN, no prior month) is filled rather than averaged over 11 months.
    """
    return series.astype("float64").groupby("time.year").mean("time", skipna=skipna)


def _time_ohca(years):
    """Annual timestamps as days since EPOCH (each year anchored at its 1-June)."""
    ref = pd.Timestamp(EPOCH)
    days = np.array([(pd.Timestamp("%d-06-01" % y) - ref).days for y in years], dtype="float64")
    return xr.DataArray(days, dims=("time_ohca",),
                        attrs={"units": "days since %s 00:00:00" % EPOCH,
                               "calendar": "proleptic_gregorian", "long_name": "time"})


def build_level_dataset(cl, tag, collaborators):
    """One combined level's result -> an xr.Dataset over `time_ohca` with ohca, ohu (+ optional `_sd`).

    Emits per-area densities to match the target (Zenodo 14720478 v4.0.0): `ohca` in J/m², `ohu` in
    W/m². The combine gives basin-integrated TJ / TJ-per-month, so each is divided by the reference
    area and scaled TJ->J (`× TERA`); `ohu` additionally / seconds-per-month, using a round 30-day
    month (= 360-day year) to match the target — see SEC_PER_MONTH. No baseline window — `ohca` is
    the whole-record anomaly from derive's `integral_anom`. SDs carry the same per-area/units
    conversion as their values.
    """
    area = cl["area"]
    ohca_yr = _yearly(cl["ohca"])
    ohu_yr = _yearly(cl["ohu"], skipna=False)        # first year (t0 NaN) -> fill, not an 11-mo mean
    years = ohca_yr["year"].values.astype("int64")

    def to_jm2(tj):                       # TJ -> J/m^2
        return tj / area * TERA

    def to_wm2(tj_per_month):             # TJ/month -> W/m^2
        return tj_per_month / area * TERA / SEC_PER_MONTH

    time = _time_ohca(years)
    dv = {
        "ohca": xr.DataArray(to_jm2(ohca_yr.values), dims=("time_ohca",),
                             attrs={"units": "J/m2", "area_m2": area,
                                    "long_name": "annual OHC anomaly (all-time mean removed)"}),
        "ohu": xr.DataArray(to_wm2(ohu_yr.values), dims=("time_ohca",),
                            attrs={"units": "W/m2", "area_m2": area,
                                   "long_name": "annual mean ocean heat uptake"}),
    }
    if cl["ohca_sd_yearly"] is not None:
        note = "worst-case ensemble 1-sigma: linear n_fac-weighted sum of per-layer yearly SDs"
        dv["ohca_std"] = xr.DataArray(to_jm2(cl["ohca_sd_yearly"].sel(year=years).values),
                                      dims=("time_ohca",), attrs={"units": "J/m2", "comment": note})
        dv["ohu_std"] = xr.DataArray(to_wm2(cl["ohu_sd_yearly"].sel(year=years).values),
                                     dims=("time_ohca",), attrs={"units": "W/m2", "comment": note})

    # Linear trends as attrs: OLS slope of the annual series expressed per second. to_jm2/to_wm2 carry
    # the same per-area (and per-month) conversion as the values; / SEC_PER_YEAR is the year-step ->
    # per-second factor. ohca_trend in W/m², ohu_trend in W/m²/s (+ *_trend_uq when the ensemble is on).
    dv["ohca"].attrs.update({"trend": to_jm2(cl["ohca_trend"]) / SEC_PER_YEAR, "trend_units": "W/m2"})
    dv["ohu"].attrs.update({"trend": to_wm2(cl["ohu_trend"]) / SEC_PER_YEAR, "trend_units": "W/m2/s"})
    if cl["ohca_trend_uq"] is not None:
        dv["ohca"].attrs["trend_std"] = to_jm2(cl["ohca_trend_uq"]) / SEC_PER_YEAR
        dv["ohu"].attrs["trend_std"] = to_wm2(cl["ohu_trend_uq"]) / SEC_PER_YEAR

    out = xr.Dataset(dv, coords={"time_ohca": time})
    out.attrs["level"] = cl["name"]
    out.attrs["description"] = "%s, %s" % (tag, collaborators)
    return out


def filename(cl, tag):
    """Target-style per-level name: ohca_ohu_<lo>_<hi>_dbar_<tag>.nc"""
    return "ohca_ohu_%d_%d_dbar_%s.nc" % (cl["low"], cl["high"], tag.lower().replace(" ", ""))
