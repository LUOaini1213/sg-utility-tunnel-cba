"""Placement of parallel utilities in a road reserve as a mixed-integer programme (HiGHS via SciPy).

Variables per utility i: centre x_i, zone binaries (left sidetable / carriageway / right sidetable);
per pair an ordering binary; optionally the sidetable width v and, for existing utilities, a
"diverted" binary. A utility lies wholly inside one zone (it does not straddle the kerb).

Every solution is re-packed deterministically from its zone assignment and left-to-right order and
then passed through the independent checker in corridor.py before it is reported.
"""
from __future__ import annotations

import itertools

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from . import corridor as co

ZONES = ("left", "carriageway", "right")
TIGHT = 1e-6


class Infeasible(Exception):
    pass


def _gap_matrix(cfg, ids, disabled):
    """g[i][j] = minimum centre-to-centre distance, rule[i][j] = governing clearance rule."""
    n = len(ids)
    g, rid = np.zeros((n, n)), [[None] * n for _ in range(n)]
    for i, j in itertools.combinations(range(n), 2):
        ui, uj = cfg["utilities"][ids[i]], cfg["utilities"][ids[j]]
        c, r = co.pair_clearance(cfg, ui["type"], uj["type"], disabled)
        g[i, j] = g[j, i] = (ui["width_m"] + uj["width_m"]) / 2.0 + c
        rid[i][j] = rid[j][i] = r
    return g, rid


class _Model:
    def __init__(self, nvar):
        self.n = nvar
        self.rows, self.lo, self.hi = [], [], []

    def add(self, coeffs: dict, lo=-np.inf, hi=np.inf):
        row = np.zeros(self.n)
        for k, c in coeffs.items():
            row[k] += c
        self.rows.append(row)
        self.lo.append(lo)
        self.hi.append(hi)


def solve(cfg: dict, reserve: str, ids: list[str], objective: str, *, verge: float | None = None,
          disabled=(), strict_chambers: bool = True, max_waivers: int | None = None,
          off_carriageway=(), existing: dict | None = None, v_max: float | None = None) -> dict:
    """Solve one placement problem.

    objective: "width"     minimise the sidetable width v (reserve = carriageway + 2 v)
               "waivers"   fixed reserve; minimise chambered utilities under the carriageway
               "cost"      fixed reserve; minimise trench cost (plus diversion cost of moved utilities)
    existing:  {id: {"x": .., "cover": ..}} utilities already in the ground; they stay where they are
               unless diverted (binary), and a diverted or new utility must meet every rule.
    """
    n = len(ids)
    existing = existing or {}
    util = [cfg["utilities"][u] for u in ids]
    w = np.array([u["width_m"] for u in util])
    g, _ = _gap_matrix(cfg, ids, disabled)
    # smallest / largest clearance each utility needs to any other one
    clr = g - (w[:, None] + w[None, :]) / 2.0
    c_min_max = ([min((clr[i, j] for j in range(n) if j != i), default=0.0) for i in range(n)],
                 [max((clr[i, j] for j in range(n) if j != i), default=0.0) for i in range(n)])
    off = co.drain_offset(cfg, disabled)[0]
    geom0 = co.geometry(cfg, reserve, verge)
    c_w, dw = geom0["carriageway"], geom0["drain_width"]
    ban = any(r["kind"] == "chamber_ban" and r["id"] not in disabled for r in cfg["rules"])
    pairs = list(itertools.combinations(range(n), 2))

    # variable layout
    ix = lambda i: i
    iz = lambda i, z: n + 3 * i + z
    io = lambda p: 4 * n + p
    iv = 4 * n + len(pairs)
    im = lambda i: iv + 1 + i
    iy = lambda i, z: iv + 1 + n + 3 * i + z
    nvar = iv + 1 + 4 * n

    fixed_v = objective != "width"
    if fixed_v:
        v_lo = v_hi = geom0["verge"]
    else:
        v_lo = dw
        # everything on one side in any order always fits within this width
        v_hi = v_max if v_max is not None else dw + off + float(w.sum()) + float(sum(c_min_max[1])) + 0.1
    big = c_w + 2.0 * v_hi + 1.0

    m = _Model(nvar)
    for i in range(n):
        half = w[i] / 2.0
        m.add({iz(i, 0): 1, iz(i, 1): 1, iz(i, 2): 1}, 1, 1)
        # inside the reserve and clear of both drains: dw+off+half <= x <= c + 2v - dw - off - half
        m.add({ix(i): 1}, dw + off + half, np.inf)
        m.add({ix(i): 1, iv: -2}, -np.inf, c_w - dw - off - half)
        # left sidetable: x + half <= v
        m.add({ix(i): 1, iv: -1, iz(i, 0): big}, -np.inf, big - half)
        # carriageway: v + half <= x <= v + c - half
        m.add({ix(i): 1, iv: -1, iz(i, 1): -big}, half - big, np.inf)
        m.add({ix(i): 1, iv: -1, iz(i, 1): big}, -np.inf, big + c_w - half)
        # right sidetable: x - half >= v + c
        m.add({ix(i): 1, iv: -1, iz(i, 2): -big}, half + c_w - big, np.inf)
    for p, (i, j) in enumerate(pairs):
        # o = 1: i left of j
        m.add({ix(j): 1, ix(i): -1, io(p): -big}, g[i, j] - big, np.inf)
        m.add({ix(i): 1, ix(j): -1, io(p): big}, g[i, j], np.inf)

    # Valid capacity cuts (they only tighten the relaxation). In a row of utilities each adjacent gap is
    # at least the average of the two neighbours' smallest clearances, so the utilities assigned to a zone
    # need at least sum(width + smallest clearance) - largest smallest-clearance of its length.
    a_min = c_min_max[0]
    slack = max(a_min, default=0.0)
    m.add({**{iz(i, 0): w[i] + a_min[i] for i in range(n)}, iv: -1}, -np.inf, slack - dw - off)
    m.add({**{iz(i, 2): w[i] + a_min[i] for i in range(n)}, iv: -1}, -np.inf, slack - dw - off)
    m.add({iz(i, 1): w[i] + a_min[i] for i in range(n)}, -np.inf, slack + c_w)
    if not existing and n:
        m.add({ix(0): 1, iv: -1}, -np.inf, c_w / 2.0)   # mirror symmetry: first utility in the left half

    lb, ub = np.zeros(nvar), np.ones(nvar)
    lb[:n], ub[:n] = 0.0, c_w + 2.0 * v_hi
    lb[iv], ub[iv] = v_lo, v_hi
    integrality = np.ones(nvar)
    integrality[:n] = 0
    integrality[iv] = 0
    cost = np.zeros(nvar)
    chambered = [i for i in range(n) if util[i]["chambers"] or ids[i] in off_carriageway]

    old_zone = {}
    for i, uid in enumerate(ids):
        if uid in existing:
            a, b = existing[uid]["x"] - w[i] / 2.0, existing[uid]["x"] + w[i] / 2.0
            zname = co.zone_name(geom0, a, b)
            old_zone[i] = ZONES.index(zname) if zname in ZONES else None
            need = co.required_cover(cfg, uid, co.zones_touched(geom0, a, b), disabled)[0]
            pinned_ok = existing[uid]["cover"] >= need - co.EPS and old_zone[i] is not None
            # not diverted -> stays exactly where it is
            m.add({ix(i): 1, im(i): -big}, -np.inf, existing[uid]["x"])
            m.add({ix(i): 1, im(i): big}, existing[uid]["x"], np.inf)
            if old_zone[i] is not None:
                m.add({iz(i, old_zone[i]): 1, im(i): 1}, 1, np.inf)
            if not pinned_ok:
                lb[im(i)] = 1          # deficient cover (or straddling the kerb) can only be cured by relaying
            if ban and strict_chambers and i in chambered:
                if old_zone[i] == 1:
                    m.add({iz(i, 1): 1, im(i): 1}, -np.inf, 1)   # grandfathered only while it stays put
                else:
                    ub[iz(i, 1)] = 0
            for z in range(3):
                m.add({iy(i, z): 1, im(i): -1, iz(i, z): -1}, -1, np.inf)
        else:
            ub[im(i)] = 0
            for z in range(3):
                ub[iy(i, z)] = 0
            if ban and strict_chambers and i in chambered:
                ub[iz(i, 1)] = 0
    if ban and max_waivers is not None:
        m.add({iz(i, 1): 1 for i in chambered}, -np.inf, max_waivers)

    if objective == "width":
        cost[iv] = 1.0
    elif objective == "waivers":
        for i in chambered:
            cost[iz(i, 1)] = 1.0
    elif objective == "cost":
        df = cfg["costs"]["diversion_factor"]
        for i, uid in enumerate(ids):
            for z in range(3):
                tc = co.trench_cost(cfg, uid, ZONES[z], disabled=disabled)
                if uid in existing:
                    cost[iy(i, z)] = df * tc
                else:
                    cost[iz(i, z)] = tc
    else:
        raise ValueError(objective)

    res = milp(c=cost, constraints=LinearConstraint(np.array(m.rows), np.array(m.lo), np.array(m.hi)),
               integrality=integrality, bounds=Bounds(lb, ub),
               options={"mip_rel_gap": 0.0, "presolve": True})
    if res.status != 0 or res.x is None:
        raise Infeasible(f"{reserve}: {objective}: {res.message}")
    x = res.x
    zone = [ZONES[int(np.argmax([x[iz(i, z)] for z in range(3)]))] for i in range(n)]
    moved = [uid for i, uid in enumerate(ids) if uid in existing and x[im(i)] > 0.5]
    v = float(x[iv])
    return _canonical(cfg, reserve, ids, [float(x[i]) for i in range(n)], zone, v, fixed_v, disabled,
                      existing, moved, float(res.fun), strict_chambers, verge)


def pack(cfg, geom, ids, zone, order, disabled, pinned=None):
    """Deterministic positions for a given zone assignment and left-to-right order.

    Left-sidetable and carriageway utilities are pushed as far left as the rules allow, right-sidetable
    utilities as far right; `pinned` ids keep their x. Returns None when the order cannot be packed.
    """
    pinned = pinned or {}
    g, _ = _gap_matrix(cfg, ids, disabled)
    w = [cfg["utilities"][u]["width_m"] for u in ids]
    off = co.drain_offset(cfg, disabled)[0]
    x = {}
    lo_all, hi_all = geom["drain_width"] + off, geom["width"] - geom["drain_width"] - off
    lower = {"left": lo_all, "carriageway": max(geom["kerb_left"], lo_all), "right": max(geom["kerb_right"], lo_all)}
    upper = {"left": min(geom["kerb_left"], hi_all), "carriageway": min(geom["kerb_right"], hi_all), "right": hi_all}
    for i in order:
        if ids[i] in pinned:
            x[i] = pinned[ids[i]]
    for i in order:
        if i in x or zone[i] == "right":
            continue
        pos = lower[zone[i]] + w[i] / 2.0
        for j in order[:order.index(i)]:
            if j in x:
                pos = max(pos, x[j] + g[j][i])
        x[i] = pos
    for i in reversed(order):
        if i in x:
            continue
        pos = upper["right"] - w[i] / 2.0
        for j in order[order.index(i) + 1:]:
            pos = min(pos, x[j] - g[i][j])
        x[i] = pos
    for a, b in zip(order, order[1:]):
        if x[b] - x[a] < -co.EPS:
            return None
    for i in order:
        if ids[i] in pinned:
            continue
        if x[i] - w[i] / 2.0 < lower[zone[i]] - co.EPS or x[i] + w[i] / 2.0 > upper[zone[i]] + co.EPS:
            return None
    for i, j in itertools.combinations(order, 2):
        if abs(x[i] - x[j]) < g[i][j] - co.EPS:
            return None
    return {i: float(val) for i, val in x.items()}


def _canonical(cfg, reserve, ids, xs, zone, v, fixed_v, disabled, existing, moved, objective, strict, verge):
    order = sorted(range(len(ids)), key=lambda i: xs[i])
    pinned = {u: existing[u]["x"] for u in existing if u not in moved}
    if fixed_v:
        cands = [verge]
    else:
        v6 = round(v, 6)
        cands = [v6, v6 + 1e-6, v6 + 1e-5, v6 + 1e-4]
    for cand in cands:
        geom = co.geometry(cfg, reserve, cand)
        x = pack(cfg, geom, ids, zone, order, disabled, pinned)
        if x is not None:
            break
    else:
        raise Infeasible(f"{reserve}: solver layout could not be re-packed")
    items = []
    for i, uid in enumerate(ids):
        kind = "carriageway" if zone[i] == "carriageway" else "sidetable"
        if uid in pinned:
            cover = existing[uid]["cover"]
        else:
            cover = co.required_cover(cfg, uid, {kind}, disabled)[0]
        items.append({"id": uid, "x": x[i], "cover": cover, "zone": zone[i]})
    grandfathered = [u for u in pinned]
    waived = [it["id"] for it in items if it["zone"] == "carriageway" and cfg["utilities"][it["id"]]["chambers"]
              and it["id"] not in grandfathered]
    violations = co.check_layout(cfg, geom, items, disabled, grandfathered=grandfathered + ([] if strict else waived))
    if violations:
        raise Infeasible(f"{reserve}: packed layout fails the checker: {violations[:2]}")
    return {"geometry": geom, "items": sorted(items, key=lambda it: it["x"]), "verge_m": geom["verge"],
            "reserve_width_m": geom["width"], "objective": objective, "moved": moved, "waived": waived,
            "binding": binding(cfg, geom, items, disabled)}


def binding(cfg: dict, geom: dict, items: list[dict], disabled=()) -> list[dict]:
    """Constraints that are tight in a layout: pair clearances, drain offsets and kerb lines."""
    out = []
    boxes = {it["id"]: co.outline(cfg, it) for it in items}
    off, off_id = co.drain_offset(cfg, disabled)
    ids = sorted(boxes, key=lambda u: boxes[u][0])
    for a, b in itertools.combinations(ids, 2):
        need, rid = co.pair_clearance(cfg, cfg["utilities"][a]["type"], cfg["utilities"][b]["type"], disabled)
        if rid and abs(co.h_gap(boxes[a], boxes[b]) - need) < TIGHT:
            out.append({"rule": rid, "items": [a, b], "clearance_m": need})
    for u in ids:
        lo, hi = boxes[u][0], boxes[u][1]
        if off_id and (abs(lo - geom["drains"][0][1] - off) < TIGHT or abs(geom["drains"][1][0] - hi - off) < TIGHT):
            out.append({"rule": off_id, "items": [u, "drain"], "clearance_m": off})
        for kerb in (geom["kerb_left"], geom["kerb_right"]):
            if abs(lo - kerb) < TIGHT or abs(hi - kerb) < TIGHT:
                out.append({"rule": "KERB-LINE", "items": [u, "kerb"], "clearance_m": 0.0})
    return out


def total_cost(cfg: dict, items: list[dict], disabled=()) -> float:
    return sum(co.trench_cost(cfg, it["id"], it["zone"], it["cover"], disabled) for it in items)


def brute_min_verge(cfg: dict, reserve: str, ids: list[str], disabled=()) -> float:
    """Exact minimum sidetable width with every utility kept off the carriageway, by enumerating every
    left/right split and every order. Independent of the MIP; used to cross-check it on small sets."""
    g, _ = _gap_matrix(cfg, ids, disabled)
    w = [cfg["utilities"][u]["width_m"] for u in ids]
    start = cfg["geometry"]["drain_width_m"] + co.drain_offset(cfg, disabled)[0]
    n = len(ids)

    def need(side):
        if not side:
            return cfg["geometry"]["drain_width_m"]
        best = float("inf")
        for perm in itertools.permutations(side):
            x = []
            for k, i in enumerate(perm):
                pos = start + w[i] / 2.0
                for kk in range(k):
                    pos = max(pos, x[kk] + g[perm[kk]][i])
                x.append(pos)
            best = min(best, max(x[k] + w[i] / 2.0 for k, i in enumerate(perm)))
        return best

    best = float("inf")
    for mask in range(2 ** n):
        left = [i for i in range(n) if mask >> i & 1]
        right = [i for i in range(n) if not mask >> i & 1]
        best = min(best, max(need(left), need(right)))
    return best
