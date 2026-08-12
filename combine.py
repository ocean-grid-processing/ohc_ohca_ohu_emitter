#!/usr/bin/env python3
"""Combine mapped-layer ohc_derive OHCA/OHU outputs into the annual OHCA/OHU deliverable.

    python combine.py DERIVE_*.nc --tag "OHCA-OHU-2026-OP20260127b" \
        [--levels 0_300,0_700,700_2000,0_2000] [--time-window 2005:2024] \
        [--collaborators STR] [--out DIR]

Each DERIVE_*.nc is one mapped layer's ohc_derive output, built with
`derive.py ... --transforms integral,integral_anom,integral_tendency,area`
(add `--keep-members integral,integral_tendency` for error bars). The combined layers and
their n_fac/dz weights live in layers.py (same table as the GCOS emitter). One .nc is written per
combined level. By default OHCA is the whole-record anomaly (referenced upstream); `--time-window`
re-references the OHCA baseline to a year range and fits the OHCA/OHU trends over it — the full
annual series is still reported either way.

Requires: numpy, xarray>=2024.10, netCDF4.
"""
import argparse
import os

import layers as layers_mod
import aggregate
import emit


def _sanitize_tag(tag):
    """Strip all whitespace from a provenance tag; never lowercase or otherwise munge it — it must
    match the provenance record char-for-char."""
    return "".join(tag.split())


def _add_provenance(ds, args):
    """Stamp provenance attrs: provenance_tag is the required --tag (also the filename run token)."""
    ds.attrs["provenance_tag"] = args.tag
    if args.provenance_link is not None:
        ds.attrs["provenance_link"] = args.provenance_link


def parse_window(s):
    """YEAR0:YEAR1 (or YEAR0-YEAR1) -> (int, int); None/empty -> None (all years)."""
    if not s:
        return None
    a, b = (int(x) for x in s.replace("-", ":").split(":"))
    return (a, b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("derive", nargs="+", help="ohc_derive .nc files, one per mapped layer")
    ap.add_argument("--tag", required=True, help='run tag, e.g. "OHCA-OHU-2026-OP20260127b"')
    ap.add_argument("--levels", default=None,
                    help="comma list of combined levels to emit (default: all in layers.py)")
    ap.add_argument("--time-window", default=None,
                    help="YEAR0:YEAR1 inclusive window for the OHCA anomaly baseline AND the OHCA/OHU "
                         "trend fits. The full annual series is still reported — the window only sets "
                         "the reference level and the trend-fit years. Default: all years.")
    ap.add_argument("--collaborators", default="LocalGP by Giglio, Sukianto, Kuusela, Mills")
    ap.add_argument("--reference", default="shallowest",
                    help="combined-layer reference area (only 'shallowest' implemented)")
    ap.add_argument("--provenance-link", default=None,
                    help="URL/path to the provenance record; written to the provenance_link header attr")
    ap.add_argument("--out", default=".")
    args = ap.parse_args()
    args.tag = _sanitize_tag(args.tag)
    window = parse_window(args.time_window)

    names = None if not args.levels else [s.strip() for s in args.levels.split(",")]
    levels = layers_mod.select_levels(names)

    by_tag = {}
    for nc in args.derive:
        layer = aggregate.read_layer(nc, window=window)
        by_tag[layer["tag"]] = layer

    need = layers_mod.required_tags(levels)
    absent = [t for t in need if t not in by_tag]
    if absent:
        raise SystemExit("missing derive inputs for contributor layer(s): %s (needed by %s)"
                         % (absent, [lv.name for lv in levels]))

    # Uncertainty is all-or-nothing across the needed contributors (raises on a partial mix).
    uncertainty = aggregate.uncertainty_available(need, by_tag)

    os.makedirs(args.out, exist_ok=True)
    written = []
    for lv in levels:
        cl = aggregate.combine_level(lv, by_tag, reference=args.reference)
        ds = emit.build_level_dataset(cl, args.tag, args.collaborators, window=window)
        _add_provenance(ds, args)
        path = os.path.join(args.out, emit.filename(cl, args.tag))
        enc = {v: {"_FillValue": -999.0} for v in ds.data_vars}   # target's fill value (NaN -> -999)
        ds.to_netcdf(path, engine="netcdf4", encoding=enc)
        written.append(path)

    print("wrote %d file(s):" % len(written))
    for p in written:
        print("  ", p)
    print("uncertainty:", "on — _sd written" if uncertainty else "off (mean-only inputs)")


if __name__ == "__main__":
    main()
