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


def test_dz_mismatch_raises():
    by = {
        "15_20": make_layer("15_20", 15, 25, area=100.0, ohca=[1.0], ohu=[1.0]),  # bounds dz=10, cfg=5
        "15_300": make_layer("15_300", 15, 300, area=80.0, ohca=[1.0], ohu=[1.0]),
    }
    with pytest.raises(SystemExit):
        aggregate.combine_level(L0_300, by)
