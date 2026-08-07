#!/usr/bin/env python3
"""Combine mapped-layer ohc_derive OHCA/OHU outputs into the annual OHCA/OHU deliverable.

    python combine.py DERIVE_*.nc --tag "OHCA-OHU 2026 OP20260127b" \
        [--levels 0_300,0_700,700_2000,0_2000] [--collaborators STR] [--out DIR]

Each DERIVE_*.nc is one mapped layer's ohc_derive output, built with
`derive.py ... --transforms integral_anom,integral_tendency,area`
(add `--keep-members integral_anom,integral_tendency` for error bars). The combined layers and
their n_fac/dz weights live in layers.py (same table as the GCOS emitter). One .nc is written per
combined level. No baseline windowing — OHCA is already anomaly-referenced upstream.

Requires: numpy, xarray>=2024.10, netCDF4.
"""
import argparse
import os

import layers as layers_mod
import aggregate
import emit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("derive", nargs="+", help="ohc_derive .nc files, one per mapped layer")
    ap.add_argument("--tag", required=True, help='run tag, e.g. "OHCA-OHU 2026 OP20260127b"')
    ap.add_argument("--levels", default=None,
                    help="comma list of combined levels to emit (default: all in layers.py)")
    ap.add_argument("--collaborators", default="LocalGP by Giglio, Sukianto, Kuusela, Mills")
    ap.add_argument("--reference", default="shallowest",
                    help="combined-layer reference area (only 'shallowest' implemented)")
    ap.add_argument("--out", default=".")
    args = ap.parse_args()

    names = None if not args.levels else [s.strip() for s in args.levels.split(",")]
    levels = layers_mod.select_levels(names)

    by_tag = {}
    for nc in args.derive:
        layer = aggregate.read_layer(nc)
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
        ds = emit.build_level_dataset(cl, args.tag, args.collaborators)
        path = os.path.join(args.out, emit.filename(cl, args.tag))
        ds.to_netcdf(path, engine="netcdf4")
        written.append(path)

    print("wrote %d file(s):" % len(written))
    for p in written:
        print("  ", p)
    print("uncertainty:", "on — _sd written" if uncertainty else "off (mean-only inputs)")


if __name__ == "__main__":
    main()
