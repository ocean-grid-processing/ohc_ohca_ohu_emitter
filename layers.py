"""Combined-layer configuration for ohc_ohca_ohu_emitter.

Each combined layer is a weighted sum of mapped ("contributor") layers, listed shallowest-first.
The shallowest contributor sets the reference area. `n_fac` scales a thin measured layer up to the
depth slab it stands in for (e.g. the 5 m `15_20` layer x3 covers the unmeasured `0-15 m` top; the
50 m `1800_1850` sliver x3 covers `1850-2000 m`). `dz` is the contributor's own thickness
(bottom - top); `sum(n_fac*dz)` equals the nominal layer thickness.

NOTE: this is a *verbatim duplicate* of ohc_gcos_emitter/layers.py — the two emitters share the
same synthetic layers by decision. Kept duplicated (not a shared import) until a third consumer
earns the extraction; if you edit one, edit the other.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Contributor:
    tag: str      # mapped-layer tag "top_bottom", matches ohc_ingest/publish `mapped_layer`
    n_fac: int    # multiplier (thin-layer proxy scaling)
    dz: float     # contributor thickness in m (= bottom - top); checked against the layer bounds


@dataclass(frozen=True)
class Level:
    name: str            # "0_300"
    contributors: tuple  # (Contributor, ...) shallowest first; contributors[0] sets the area

    @property
    def low(self):
        return int(self.name.split("_")[0])

    @property
    def high(self):
        return int(self.name.split("_")[1])

    @property
    def nominal_thickness(self):
        return sum(c.n_fac * c.dz for c in self.contributors)


# The config table. Shallowest contributor first (it sets the reference area).
LEVELS = [
    Level("0_300", (
        Contributor("15_20", 3, 5),
        Contributor("15_300", 1, 285),
    )),
    Level("0_700", (
        Contributor("15_20", 3, 5),
        Contributor("15_300", 1, 285),
        Contributor("300_700", 1, 400),
    )),
    Level("0_1000", (                       # net-new; needs the 700_1000 mapped layer
        Contributor("15_20", 3, 5),
        Contributor("15_300", 1, 285),
        Contributor("300_700", 1, 400),
        Contributor("700_1000", 1, 300),
    )),
    Level("700_2000", (
        Contributor("700_1850", 1, 1150),
        Contributor("1800_1850", 3, 50),
    )),
    Level("0_2000", (
        Contributor("15_20", 3, 5),
        Contributor("15_300", 1, 285),
        Contributor("300_700", 1, 400),
        Contributor("700_1850", 1, 1150),
        Contributor("1800_1850", 3, 50),
    )),
]

LEVELS_BY_NAME = {lv.name: lv for lv in LEVELS}


def select_levels(names=None):
    """Return the Levels for `names` (a list of level names), or all LEVELS if names is None."""
    if names is None:
        return list(LEVELS)
    out = []
    for n in names:
        if n not in LEVELS_BY_NAME:
            raise SystemExit("unknown level %r; known: %s" % (n, list(LEVELS_BY_NAME)))
        out.append(LEVELS_BY_NAME[n])
    return out


def required_tags(levels):
    """Distinct contributor tags needed to build `levels` (order-preserving)."""
    tags = []
    for lv in levels:
        for c in lv.contributors:
            if c.tag not in tags:
                tags.append(c.tag)
    return tags
