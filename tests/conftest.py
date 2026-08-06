import os
import sys

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def months(n, start="2004-01"):
    """A monthly datetime64 axis of length n."""
    return pd.date_range(start, periods=n, freq="MS").values


def _year_da(d):
    yrs = np.array(sorted(d), dtype="int64")
    return xr.DataArray(np.array([d[y] for y in yrs], dtype="float64"),
                        dims=("year",), coords={"year": yrs})


def make_layer(tag, top, bottom, area, ohca, ohu,
               ohca_sd_yearly=None, ohu_sd_yearly=None, cp0=3989.244, rho0=1030.0):
    """A read_layer()-shaped dict for combine tests (no file IO).

    `ohca`/`ohu` are monthly value lists; `*_sd_yearly`, if given, are {year: sd} dicts →
    the layer's yearly ensemble SD (year,) [TJ].
    """
    t = months(len(ohca))

    def _series(vals):
        return xr.DataArray(np.asarray(vals, dtype="float64"), dims=("time",), coords={"time": t})

    return {
        "tag": tag,
        "ohca": _series(ohca),
        "ohu": _series(ohu),
        "area": float(area),
        "top": top, "bottom": bottom,
        "cp0": cp0, "rho0": rho0, "period": "2004_2004",
        "ohca_sd_yearly": None if ohca_sd_yearly is None else _year_da(ohca_sd_yearly),
        "ohu_sd_yearly": None if ohu_sd_yearly is None else _year_da(ohu_sd_yearly),
    }
