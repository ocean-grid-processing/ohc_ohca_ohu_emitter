"""Read ohc_derive OHCA/OHU outputs and combine mapped layers into combined-layer series.

Input is one `ohc_derive` NetCDF per mapped layer, built with
`--transforms integral_anom,integral_tendency,area` (add
`--keep-members integral_anom,integral_tendency` for error bars). Each provides:

    ohc_integral_anom      (time,)  OHCA, TJ  (integral minus its all-time mean)
    ohc_integral_tendency  (time,)  OHU,  TJ  (month-to-month change, NaN at t0)
    area_total             ()       m^2

and, with the ensemble, the `_ens` (member, time) siblings.

Combination is the *same* shallowest-first n_fac weighting as the GCOS emitter. It's linear, so it
applies identically to OHCA and OHU:  total_L(t) = sum_i n_fac_i * q_i(t). Because OHCA is already
referenced to each layer's whole-record mean and the mean is linear, the combined OHCA is correctly
the anomaly of the combined integral — no re-referencing needed here.

**Uncertainty (optional).** Per layer, the ensemble std of the *yearly* value — yearly-mean per
member, then std across members (ddof=1) — combined by the same weights as a worst-case linear sum
(fully-correlated). All-or-nothing: a level gets an SD only if every contributor carries the
ensemble.
"""
import xarray as xr


def _yearly_member_std(ens):
    """Ensemble std of the yearly mean: yearly-mean per member, then std across members (ddof=1)."""
    return ens.groupby("time.year").mean("time").std("member", ddof=1)      # (year,)


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
                             "--transforms integral_anom,integral_tendency,area`" % (nc, v))
    tag = a.get("mapped_layer") or a.get("layer_m")
    if not tag or "_" not in str(tag):
        raise SystemExit("%s has no usable mapped_layer/layer_m attr (got %r)" % (nc, tag))
    top, bottom = (int(x) for x in str(tag).split("_"))

    ohca_sd_yearly = ohu_sd_yearly = None
    has_ens = ("ohc_integral_anom_ens" in ds.data_vars
               and "ohc_integral_tendency_ens" in ds.data_vars)
    if has_ens:
        ohca_sd_yearly = _yearly_member_std(ds["ohc_integral_anom_ens"].astype("float64"))
        ohu_sd_yearly = _yearly_member_std(ds["ohc_integral_tendency_ens"].astype("float64"))

    return {
        "tag": str(tag),
        "ohca": ds["ohc_integral_anom"].astype("float64"),       # (time,) TJ
        "ohu": ds["ohc_integral_tendency"].astype("float64"),    # (time,) TJ
        "area": float(ds["area_total"]),                         # m^2
        "top": top,
        "bottom": bottom,
        "cp0": float(a["cp0"]),
        "rho0": float(a["rho0"]),
        "period": a.get("period", ""),
        "ohca_sd_yearly": ohca_sd_yearly,                        # (year,) TJ or None
        "ohu_sd_yearly": ohu_sd_yearly,                          # (year,) TJ or None
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
    have_all_sd = all(by_tag[c.tag].get("ohca_sd_yearly") is not None for c in level.contributors)
    for c in level.contributors:
        layer = by_tag[c.tag]
        bounds_dz = layer["bottom"] - layer["top"]
        if abs(c.dz - bounds_dz) > 1e-9:
            raise SystemExit(
                "dz mismatch for %s in level %s: config dz=%g but layer bounds give %g"
                % (c.tag, level.name, c.dz, bounds_dz))
        ohca = c.n_fac * layer["ohca"] if ohca is None else ohca + c.n_fac * layer["ohca"]
        ohu = c.n_fac * layer["ohu"] if ohu is None else ohu + c.n_fac * layer["ohu"]
        if have_all_sd:                                          # worst-case linear SD sum
            a_term = c.n_fac * layer["ohca_sd_yearly"]
            u_term = c.n_fac * layer["ohu_sd_yearly"]
            ohca_sd = a_term if ohca_sd is None else ohca_sd + a_term
            ohu_sd = u_term if ohu_sd is None else ohu_sd + u_term

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
    }
