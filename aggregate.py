"""Read ohc_derive OHCA/OHU outputs and combine mapped layers into combined-layer series.

Input is one `ohc_derive` NetCDF per mapped layer, built with
`--transforms integral,integral_anom,integral_tendency,area` (add
`--keep-members integral,integral_tendency` for error bars). Each provides:

    ohc_integral_anom      (time,)  OHCA value, TJ  (integral minus its all-time mean)
    ohc_integral_tendency  (time,)  OHU value,  TJ  (month-to-month change, NaN at t0)
    area_total             ()       m^2

For error bars, the `_ens` (member, time) siblings: `ohc_integral_ens` (the ABSOLUTE integral, for
the OHCA spread — see read_layer) and `ohc_integral_tendency_ens` (for OHU). Note the OHCA spread
comes from `ohc_integral_ens`, not `ohc_integral_anom_ens`.

Combination is the *same* shallowest-first n_fac weighting as the GCOS emitter. It's linear, so it
applies identically to OHCA and OHU:  total_L(t) = sum_i n_fac_i * q_i(t). Because OHCA is already
referenced to each layer's whole-record mean and the mean is linear, the combined OHCA is correctly
the anomaly of the combined integral — no re-referencing needed here.

**Uncertainty (optional).** Per layer, the ensemble std of the *yearly* value — yearly-mean per
member, then std across members (ddof=1) — combined by the same weights as a worst-case linear sum
(fully-correlated). All-or-nothing: a level gets an SD only if every contributor carries the
ensemble.

**Trend.** Per layer, an OLS linear slope of the annual (calendar-year mean) series — central from
the mean field, and its uncertainty the std (ddof=1) across members of the per-member slopes. Both
combine by the same linear n_fac weighting (matching the original's create_eval_string_trend[_uq]).
The per-second and per-area scaling to W/m² (ohca) and W/m²/s (ohu) is applied in the emitter.
"""
import numpy as np
import xarray as xr


def _annual(da, skipna):
    return da.groupby("time.year").mean("time", skipna=skipna)


def _yearly_member_std(ens, skipna=True):
    """Ensemble std of the yearly mean: yearly-mean per member, then std across members (ddof=1).

    `skipna=False` fills any year with a missing month (used for OHU, whose t0 tendency is NaN), so
    the first year's SD matches its filled value rather than being an 11-month spread.
    """
    return _annual(ens, skipna).std("member", ddof=1)   # (year,)


def _ols_slope(y):
    """OLS slope of y vs its integer index (per year-step), dropping NaN then re-indexing 1..M.

    Matches WMO2024_lsf_trend 'yearly' (G=[ones, x], unweighted, x = 1:length(non-NaN)); slope = m(2).
    """
    y = np.asarray(y, dtype="float64")
    y = y[np.isfinite(y)]
    if y.size < 2:
        return float("nan")
    x = np.arange(y.size, dtype="float64")
    xc = x - x.mean()
    return float((xc * (y - y.mean())).sum() / (xc * xc).sum())


def _layer_trend(central, ens, skipna):
    """Per-layer OLS trend of the annual (mean) series, per year-step, in the input's (integral) units.

    Returns (central_slope, slope_uq): central_slope from the mean-field series; slope_uq the std
    (ddof=1) across ensemble members of their per-member slopes, or None without an ensemble.
    """
    central_slope = _ols_slope(_annual(central, skipna).values)
    if ens is None:
        return central_slope, None
    ann = _annual(ens, skipna)                                            # (member, year)
    slopes = np.array([_ols_slope(ann.isel(member=k).values)
                       for k in range(ann.sizes["member"])], dtype="float64")
    return central_slope, float(np.nanstd(slopes, ddof=1))


def read_layer(nc):
    """Read one mapped layer's OHCA/OHU derive output into a dict.

    Returns tag, ohca(time) [TJ], ohu(time) [TJ], area [m^2], top/bottom [m], cp0, rho0, period, and
    `ohca_sd_yearly`/`ohu_sd_yearly` (year,) [TJ] if the `_ens` siblings are present, else None.
    """
    ds = xr.open_dataset(nc, decode_times=True)
    a = ds.attrs
    for v in ("ohc_integral_anom", "ohc_integral_tendency", "area_total"):
        if v not in ds.data_vars:
            raise SystemExit("%s missing %s — build it with `derive.py ... "
                             "--transforms integral,integral_anom,integral_tendency,area`" % (nc, v))
    tag = a.get("mapped_layer") or a.get("layer_m")
    if not tag or "_" not in str(tag):
        raise SystemExit("%s has no usable mapped_layer/layer_m attr (got %r)" % (nc, tag))
    top, bottom = (int(x) for x in str(tag).split("_"))

    ohca_da = ds["ohc_integral_anom"].astype("float64")      # reported value = mean-field anomaly
    ohu_da = ds["ohc_integral_tendency"].astype("float64")

    # OHCA spread comes from the ABSOLUTE integral members (ohc_integral_ens), matching the original's
    # data_yearly_std (std of the raw yearly integral). The anomaly members can't be used:
    # integral_anom demeans each member by its own time-mean, removing the between-member level spread.
    ohca_sd_yearly = ohu_sd_yearly = None
    has_ens = ("ohc_integral_ens" in ds.data_vars
               and "ohc_integral_tendency_ens" in ds.data_vars)
    ohca_ens = ds["ohc_integral_ens"].astype("float64") if has_ens else None
    ohu_ens = ds["ohc_integral_tendency_ens"].astype("float64") if has_ens else None
    if has_ens:
        ohca_sd_yearly = _yearly_member_std(ohca_ens)
        ohu_sd_yearly = _yearly_member_std(ohu_ens, skipna=False)     # first year (t0 NaN) -> fill

    # OLS trend: central slope from the reported value (anomaly); its spread from the absolute members
    # (a slope is offset-invariant, so the two are consistent). ohu drops its NaN t0 year.
    ohca_trend, ohca_trend_uq = _layer_trend(ohca_da, ohca_ens, skipna=True)
    ohu_trend, ohu_trend_uq = _layer_trend(ohu_da, ohu_ens, skipna=False)

    return {
        "tag": str(tag),
        "ohca": ohca_da,                                         # (time,) TJ
        "ohu": ohu_da,                                           # (time,) TJ
        "area": float(ds["area_total"]),                         # m^2
        "top": top,
        "bottom": bottom,
        "cp0": float(a["cp0"]),
        "rho0": float(a["rho0"]),
        "period": a.get("period", ""),
        "ohca_sd_yearly": ohca_sd_yearly,                        # (year,) TJ or None
        "ohu_sd_yearly": ohu_sd_yearly,                          # (year,) TJ or None
        "ohca_trend": ohca_trend,                               # slope/year-step, integral TJ
        "ohu_trend": ohu_trend,
        "ohca_trend_uq": ohca_trend_uq,                         # member-std of slopes, or None
        "ohu_trend_uq": ohu_trend_uq,
    }


def uncertainty_available(needed, by_tag):
    """True if *every* needed tag carries an ensemble SD, False if none do; raise on a partial mix."""
    have = [t for t in needed if by_tag[t].get("ohca_sd_yearly") is not None]
    if not have:
        return False
    if len(have) != len(needed):
        missing = [t for t in needed if by_tag[t].get("ohca_sd_yearly") is None]
        raise SystemExit(
            "uncertainty: ensemble present for %s but missing for %s — re-run derive on the missing "
            "layer(s) with --keep-members integral_anom,integral_tendency, or none get error bars."
            % (have, missing))
    return True


def combine_level(level, by_tag, reference="shallowest"):
    """Combine one Level's contributors from `by_tag` (tag -> read_layer dict).

    Returns {name, low, high, ohca(time), ohu(time), area, ohca_sd_yearly, ohu_sd_yearly}. The two
    `*_sd_yearly` are the n_fac-weighted linear sums of the contributors' yearly SDs (year,) if
    *every* contributor carries one, else None.
    """
    if reference != "shallowest":
        raise NotImplementedError(
            "reference_area=%r needs gridded per-layer masks; only 'shallowest' is implemented "
            "for the series-level combine." % reference)

    missing = [c.tag for c in level.contributors if c.tag not in by_tag]
    if missing:
        raise SystemExit("level %s: missing contributor derive input(s) %s" % (level.name, missing))

    ohca = ohu = None
    ohca_sd = ohu_sd = None
    ohca_trend = ohu_trend = 0.0                                  # central trend: always (mean field)
    ohca_trend_uq = ohu_trend_uq = None
    have_all_sd = all(by_tag[c.tag].get("ohca_sd_yearly") is not None for c in level.contributors)
    have_all_tuq = all(by_tag[c.tag].get("ohca_trend_uq") is not None for c in level.contributors)
    for c in level.contributors:
        layer = by_tag[c.tag]
        bounds_dz = layer["bottom"] - layer["top"]
        if abs(c.dz - bounds_dz) > 1e-9:
            raise SystemExit(
                "dz mismatch for %s in level %s: config dz=%g but layer bounds give %g"
                % (c.tag, level.name, c.dz, bounds_dz))
        ohca = c.n_fac * layer["ohca"] if ohca is None else ohca + c.n_fac * layer["ohca"]
        ohu = c.n_fac * layer["ohu"] if ohu is None else ohu + c.n_fac * layer["ohu"]
        ohca_trend += c.n_fac * layer["ohca_trend"]              # linear n_fac sum (matches original)
        ohu_trend += c.n_fac * layer["ohu_trend"]
        if have_all_sd:                                          # worst-case linear SD sum
            a_term = c.n_fac * layer["ohca_sd_yearly"]
            u_term = c.n_fac * layer["ohu_sd_yearly"]
            ohca_sd = a_term if ohca_sd is None else ohca_sd + a_term
            ohu_sd = u_term if ohu_sd is None else ohu_sd + u_term
        if have_all_tuq:                                         # worst-case linear trend-uq sum
            at = c.n_fac * layer["ohca_trend_uq"]
            ut = c.n_fac * layer["ohu_trend_uq"]
            ohca_trend_uq = at if ohca_trend_uq is None else ohca_trend_uq + at
            ohu_trend_uq = ut if ohu_trend_uq is None else ohu_trend_uq + ut

    area = by_tag[level.contributors[0].tag]["area"]             # reference = shallowest contributor
    return {
        "name": level.name,
        "low": level.low,
        "high": level.high,
        "ohca": ohca,
        "ohu": ohu,
        "area": area,
        "ohca_sd_yearly": ohca_sd,                              # (year,) TJ or None
        "ohu_sd_yearly": ohu_sd,
        "ohca_trend": ohca_trend,                              # slope/year-step, integral TJ
        "ohu_trend": ohu_trend,
        "ohca_trend_uq": ohca_trend_uq,                        # or None
        "ohu_trend_uq": ohu_trend_uq,
    }
