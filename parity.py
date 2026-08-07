#!/usr/bin/env python3
"""Compare our OHCA/OHU deliverable .nc against the target (Zenodo 14720478 v4.0.0), one level per file.

    python parity.py OURS.nc THEIRS.nc [--rtol 1e-6]

Both files are one combined level. Variables `ohca`, `ohu`, `ohca_std`, `ohu_std` live on the
`time_ohca` axis; the reference area and the linear trend (+ its uncertainty) are per-variable
attributes. Reports the max absolute/relative difference per shared variable, then the `area` and
the trend, which need bridging because the target and our emitter store them differently:

  * trend — the target packs value and uncertainty into one string, `"<value> plus/minus <unc>"`,
    at ~5 significant figures; we store numeric `trend` + `trend_std`. Parsed and compared, but the
    trend can only agree to ~1e-4 (the target's string rounding), so it is reported, not gated.
  * area — the target's attr is `area`; ours is `area_m2`.

The two files are aligned on the shared `time_ohca` values (inner join), so a differing record
length (e.g. ours 22 years vs theirs 21) compares the overlap and flags the mismatch as REVIEW.

Requires: numpy, xarray, netCDF4.
"""
import argparse
import re

import numpy as np
import xarray as xr

VARS = ["ohca", "ohu", "ohca_std", "ohu_std"]


def maxdiff(a, b):
    """(max |a-b|, max |a-b| / max|b|) over finite entries."""
    a = np.asarray(a, dtype="float64")
    b = np.asarray(b, dtype="float64")
    ad = float(np.nanmax(np.abs(a - b)))
    denom = float(np.nanmax(np.abs(b))) or 1.0
    return ad, ad / denom


def parse_trend(s):
    """Target trend attr '1.1606 plus/minus 0.022107' -> (value, uncertainty) floats."""
    parts = re.split(r"\s*plus/minus\s*", str(s))
    return float(parts[0]), float(parts[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ours")
    ap.add_argument("theirs")
    ap.add_argument("--rtol", type=float, default=1e-6)
    args = ap.parse_args()

    # decode_times=False: keep time_ohca as raw day floats so both sides align on the same numbers
    # (the "days since 01-Jun-2004" units string isn't CF-parseable). missing_value/-999 still
    # decode to NaN via mask_and_scale.
    o = xr.open_dataset(args.ours, decode_times=False)
    t = xr.open_dataset(args.theirs, decode_times=False)

    no = o.sizes.get("time_ohca", 0)
    nt = t.sizes.get("time_ohca", 0)
    oa, ta = xr.align(o, t, join="inner")
    ns = oa.sizes.get("time_ohca", 0)
    print("time_ohca — ours=%d theirs=%d, shared=%d%s" % (
        no, nt, ns, "" if no == nt else "  (record lengths differ — comparing the overlap)"))

    worst = 0.0
    print("\n%-10s %11s %10s" % ("variable", "max|Δ|", "rel"))
    for v in VARS:
        if v not in oa or v not in ta:
            side = "ours-only" if v in oa else ("theirs-only" if v in ta else "in neither")
            print("[MISS] %-10s %s" % (v, side))
            continue
        ad, rd = maxdiff(oa[v].values, ta[v].values)
        worst = max(worst, rd)
        print("[%s] %-10s %11.3e %10.2e" % ("ok " if rd <= args.rtol else "OFF", v, ad, rd))

    # reference area (our attr `area_m2` vs the target's `area`)
    for v in ("ohca", "ohu"):
        oav, tav = o[v].attrs.get("area_m2"), t[v].attrs.get("area")
        if oav is not None and tav is not None:
            ra = abs(float(oav) - float(tav)) / (abs(float(tav)) or 1.0)
            print("  %-4s area: ours=%.6g theirs=%.6g (rel %.2e)" % (v, float(oav), float(tav), ra))

    # trend + spread — target string vs our numeric; ~5-fig, so reported not gated
    for v in ("ohca", "ohu"):
        if "trend" in o[v].attrs and "trend" in t[v].attrs:
            ov, ou = float(o[v].attrs["trend"]), float(o[v].attrs.get("trend_std", float("nan")))
            tv, tu = parse_trend(t[v].attrs["trend"])
            rv = abs(ov - tv) / (abs(tv) or 1.0)
            ru = abs(ou - tu) / (abs(tu) or 1.0)
            print("  %-4s trend: ours=%.5g theirs=%.5g (rel %.2e); spread ours=%.5g theirs=%.5g (rel %.2e)"
                  % (v, ov, tv, rv, ou, tu, ru))

    print("\nWORST relative difference over shared variables: %.2e  (rtol=%g)" % (worst, args.rtol))
    ok = worst <= args.rtol and no == nt
    print("RESULT:", "PASS" if ok else "REVIEW")


if __name__ == "__main__":
    main()
