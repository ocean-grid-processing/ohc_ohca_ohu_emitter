"""combine_level arithmetic: n_fac-weighted OHCA/OHU, shallowest area, SD propagation, guards."""
import numpy as np
import pytest

import aggregate
from layers import Contributor, Level
from conftest import make_layer

L0_300 = Level("0_300", (Contributor("15_20", 3, 5), Contributor("15_300", 1, 285)))


def test_ohca_ohu_nfac_linear():
    by = {
        "15_20": make_layer("15_20", 15, 20, area=100.0, ohca=[1.0, 2.0], ohu=[0.5, 0.5]),
        "15_300": make_layer("15_300", 15, 300, area=80.0, ohca=[10.0, 20.0], ohu=[1.0, 1.0]),
    }
    out = aggregate.combine_level(L0_300, by)
    assert np.allclose(out["ohca"].values, [3 * 1 + 10, 3 * 2 + 20])   # [13, 26]
    assert np.allclose(out["ohu"].values, [3 * 0.5 + 1, 3 * 0.5 + 1])  # [2.5, 2.5]
    assert out["area"] == 100.0                                        # shallowest (15_20)
    assert out["ohca_sd_yearly"] is None and out["ohu_sd_yearly"] is None


def test_sd_is_nfac_linear_sum():
    by = {
        "15_20": make_layer("15_20", 15, 20, area=100.0, ohca=[1.0], ohu=[1.0],
                            ohca_sd_yearly={2004: 2.0}, ohu_sd_yearly={2004: 0.1}),
        "15_300": make_layer("15_300", 15, 300, area=80.0, ohca=[1.0], ohu=[1.0],
                             ohca_sd_yearly={2004: 5.0}, ohu_sd_yearly={2004: 0.3}),
    }
    out = aggregate.combine_level(L0_300, by)
    assert np.allclose(out["ohca_sd_yearly"].values, [3 * 2.0 + 5.0])  # 11
    assert np.allclose(out["ohu_sd_yearly"].values, [3 * 0.1 + 0.3])   # 0.6


def test_partial_ensemble_gives_no_sd():
    by = {
        "15_20": make_layer("15_20", 15, 20, area=100.0, ohca=[1.0], ohu=[1.0],
                            ohca_sd_yearly={2004: 2.0}, ohu_sd_yearly={2004: 0.1}),
        "15_300": make_layer("15_300", 15, 300, area=80.0, ohca=[1.0], ohu=[1.0]),  # no ensemble
    }
    out = aggregate.combine_level(L0_300, by)
    assert out["ohca_sd_yearly"] is None and out["ohu_sd_yearly"] is None


def test_uncertainty_available_raises_on_partial():
    by = {
        "15_20": make_layer("15_20", 15, 20, area=100.0, ohca=[1.0], ohu=[1.0],
                            ohca_sd_yearly={2004: 2.0}, ohu_sd_yearly={2004: 0.1}),
        "15_300": make_layer("15_300", 15, 300, area=80.0, ohca=[1.0], ohu=[1.0]),
    }
    assert aggregate.uncertainty_available(["15_20"], {"15_20": by["15_20"]}) is True
    with pytest.raises(SystemExit):
        aggregate.uncertainty_available(["15_20", "15_300"], by)


def test_ols_slope_recovers_line():
    import numpy as np
    y = 3.0 + 2.5 * np.arange(5)                      # slope 2.5 per step
    assert abs(aggregate._ols_slope(y) - 2.5) < 1e-12
    y2 = np.array([np.nan, 10.0, 12.0, 14.0])         # NaN dropped, re-indexed -> slope 2.0
    assert abs(aggregate._ols_slope(y2) - 2.0) < 1e-12


def test_layer_trend_window_restricts_fit():
    # Monthly series whose annual mean is (year-2000)^2 -> the OLS slope over 0..9 is 9.0, but over
    # the 2000-2004 window (annual values 0,1,4,9,16) it is 4.0. Proves --time-window slices the fit.
    import numpy as np
    import pandas as pd
    import xarray as xr
    time = pd.date_range("2000-01-01", "2009-12-01", freq="MS")
    y = ((time.year.values - 2000) ** 2).astype("float64")
    da = xr.DataArray(y, dims=("time",), coords={"time": time})
    assert np.isclose(aggregate._layer_trend(da, None, skipna=True, window=None)[0], 9.0)
    assert np.isclose(aggregate._layer_trend(da, None, skipna=True, window=(2000, 2004))[0], 4.0)


def test_combine_trend_and_uq_linear():
    by = {
        "15_20": make_layer("15_20", 15, 20, area=100.0, ohca=[1.0], ohu=[1.0],
                            ohca_trend=2.0, ohu_trend=0.4, ohca_trend_uq=0.5, ohu_trend_uq=0.05),
        "15_300": make_layer("15_300", 15, 300, area=80.0, ohca=[1.0], ohu=[1.0],
                             ohca_trend=7.0, ohu_trend=1.0, ohca_trend_uq=2.0, ohu_trend_uq=0.2),
    }
    out = aggregate.combine_level(L0_300, by)
    assert np.isclose(out["ohca_trend"], 3 * 2.0 + 7.0)          # 13
    assert np.isclose(out["ohu_trend"], 3 * 0.4 + 1.0)           # 2.2
    assert np.isclose(out["ohca_trend_uq"], 3 * 0.5 + 2.0)       # 3.5 (worst-case linear sum)
    assert np.isclose(out["ohu_trend_uq"], 3 * 0.05 + 0.2)       # 0.35


def test_combine_trend_uq_all_or_nothing():
    by = {
        "15_20": make_layer("15_20", 15, 20, area=100.0, ohca=[1.0], ohu=[1.0],
                            ohca_trend=2.0, ohu_trend=0.4, ohca_trend_uq=0.5, ohu_trend_uq=0.05),
        "15_300": make_layer("15_300", 15, 300, area=80.0, ohca=[1.0], ohu=[1.0],
                             ohca_trend=7.0, ohu_trend=1.0),      # no ensemble -> no trend_uq
    }
    out = aggregate.combine_level(L0_300, by)
    assert np.isclose(out["ohca_trend"], 13.0)                   # central trend still combines
    assert out["ohca_trend_uq"] is None and out["ohu_trend_uq"] is None


def test_dz_mismatch_raises():
    by = {
        "15_20": make_layer("15_20", 15, 25, area=100.0, ohca=[1.0], ohu=[1.0]),  # bounds dz=10, cfg=5
        "15_300": make_layer("15_300", 15, 300, area=80.0, ohca=[1.0], ohu=[1.0]),
    }
    with pytest.raises(SystemExit):
        aggregate.combine_level(L0_300, by)
