"""Utility corridor cross-section: agency rule lookup, conflict checker, crossings and trench cost.

Coordinates: x runs across the road reserve from the left reserve line (0) to the right one (W).
The reserve is  drain | sidetable | carriageway | sidetable | drain , symmetric about the centreline.
Depths are positive downwards from the finished surface. Each utility is a rectangle (outer width x
outer height) given by the x of its centre and its cover (surface to top).

Every clearance figure comes from inputs/corridor.yaml, where each rule is marked `sourced` (public
document and clause) or `assumption`. Personal desk study; not agency guidance.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
EPS = 1e-9
ANY = "*"


def load(path: Path | None = None) -> dict:
    cfg = yaml.safe_load((path or ROOT / "inputs" / "corridor.yaml").read_text(encoding="utf-8"))
    validate(cfg)
    return cfg


def validate(cfg: dict) -> None:
    ids = [r["id"] for r in cfg["rules"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate rule id")
    for r in cfg["rules"]:
        if r["status"] not in ("sourced", "assumption"):
            raise ValueError(f"{r['id']}: status must be sourced or assumption")
        if r["status"] == "sourced" and r.get("source") not in cfg["sources"]:
            raise ValueError(f"{r['id']}: sourced rule needs a known source")
        if r["status"] == "assumption" and "ASSUMPTION" not in r["text"]:
            raise ValueError(f"{r['id']}: assumption must be labelled in its text")
    for name, res in cfg["reserves"].items():
        if res["carriageway_m"] + 2 * cfg["geometry"]["drain_width_m"] > res["reserve_width_m"]:
            raise ValueError(f"{name}: carriageway and drains do not fit the reserve")
        for u in res["utilities"]:
            if u not in cfg["utilities"]:
                raise ValueError(f"{name}: unknown utility {u}")


def rule(cfg: dict, rule_id: str) -> dict:
    for r in cfg["rules"]:
        if r["id"] == rule_id:
            return r
    raise KeyError(rule_id)


def _active(cfg: dict, kind: str, disabled=()):
    return [r for r in cfg["rules"] if r["kind"] == kind and r["id"] not in disabled]


# ---------------------------------------------------------------- rule lookup

def pair_clearance(cfg: dict, type_a: str, type_b: str, disabled=()) -> tuple[float, str | None]:
    """Required clear gap between two parallel services and the rule that governs (largest value)."""
    best, best_id = 0.0, None
    for r in _active(cfg, "parallel", disabled):
        p, q = r["between"]
        hit = (p in (type_a, ANY) and q in (type_b, ANY)) or (p in (type_b, ANY) and q in (type_a, ANY))
        if hit and r["value_m"] > best + EPS:
            best, best_id = float(r["value_m"]), r["id"]
    return best, best_id


def required_cover(cfg: dict, uid: str, zones, disabled=()) -> tuple[float, str | None]:
    """Minimum cover (surface to top of utility) for a utility lying in the given zone(s)."""
    u = cfg["utilities"][uid]
    best, best_id = 0.0, None
    for r in cfg["rules"]:
        if r["id"] in disabled:
            continue
        if r["kind"] == "cover" and r["zone"] in zones:
            val = float(r["value_m"])
        elif r["kind"] == "cover_type" and r["type"] == u["type"]:
            val = float(r["value_m"])
        elif r["kind"] == "invert_depth" and r["type"] == u["type"]:
            val = float(r["value_m"]) - u["height_m"]      # invert at value -> top at value - height
        else:
            continue
        if val > best + EPS:
            best, best_id = val, r["id"]
    return best, best_id


def crossing_rule(cfg: dict, trunk_type: str, disabled=()) -> tuple[float, bool, str | None]:
    """Vertical clearance a crossing lateral must keep from a trunk, and whether it must pass under."""
    best, under, best_id = 0.0, False, None
    for r in _active(cfg, "crossing", disabled):
        if r["trunk"] not in (trunk_type, ANY):
            continue
        under = under or (bool(r["must_undercross"]) and r["trunk"] == trunk_type)
        if r["value_m"] > best + EPS:
            best, best_id = float(r["value_m"]), r["id"]
    return best, under, best_id


def drain_offset(cfg: dict, disabled=()) -> tuple[float, str | None]:
    rs = _active(cfg, "drain_offset", disabled)
    return (float(rs[0]["value_m"]), rs[0]["id"]) if rs else (0.0, None)


# ---------------------------------------------------------------- geometry

def geometry(cfg: dict, reserve: str, verge: float | None = None) -> dict:
    """Reserve geometry. `verge` overrides the sidetable width (drain included) on each side."""
    res = cfg["reserves"][reserve]
    c = float(res["carriageway_m"])
    v = (res["reserve_width_m"] - c) / 2.0 if verge is None else float(verge)
    dw = float(cfg["geometry"]["drain_width_m"])
    w = c + 2.0 * v
    return {"reserve": reserve, "width": w, "carriageway": c, "verge": v, "drain_width": dw,
            "kerb_left": v, "kerb_right": v + c,
            "drains": [(0.0, dw), (w - dw, w)],
            "drain_invert_depth": float(cfg["geometry"]["drain_invert_depth_m"])}


def outline(cfg: dict, item: dict) -> tuple[float, float, float, float]:
    """(left, right, top, bottom) of a placed utility."""
    u = cfg["utilities"][item["id"]]
    return (item["x"] - u["width_m"] / 2.0, item["x"] + u["width_m"] / 2.0,
            item["cover"], item["cover"] + u["height_m"])


def zones_touched(geom: dict, left: float, right: float) -> set[str]:
    z = set()
    if left < geom["kerb_left"] - EPS or right > geom["kerb_right"] + EPS:
        z.add("sidetable")
    if right > geom["kerb_left"] + EPS and left < geom["kerb_right"] - EPS:
        z.add("carriageway")
    return z


def zone_name(geom: dict, left: float, right: float) -> str:
    if right <= geom["kerb_left"] + EPS:
        return "left"
    if left >= geom["kerb_right"] - EPS:
        return "right"
    if left >= geom["kerb_left"] - EPS and right <= geom["kerb_right"] + EPS:
        return "carriageway"
    return "straddle"


def h_gap(a: tuple, b: tuple) -> float:
    """Clear horizontal gap between two outlines; negative when they overlap in plan."""
    return max(a[0], b[0]) - min(a[1], b[1])


# ---------------------------------------------------------------- checker

def _viol(cfg, rule_id, items, required, actual, note=""):
    r = rule(cfg, rule_id)
    return {"rule": rule_id, "agency": r["agency"], "status": r["status"], "kind": r["kind"],
            "items": list(items), "required_m": required, "actual_m": actual,
            "shortfall_m": None if required is None else required - actual, "note": note}


def check_layout(cfg: dict, geom: dict, items: list[dict], disabled=(), grandfathered=()) -> list[dict]:
    """All rule violations of a parallel layout. `grandfathered` ids are exempt from the chamber ban
    (cl. 6.5.1 speaks of new manholes and valves)."""
    out = []
    off, off_id = drain_offset(cfg, disabled)
    boxes = {it["id"]: outline(cfg, it) for it in items}
    if len(boxes) != len(items):
        raise ValueError("duplicate utility id in layout")
    for it in items:
        uid, (lo, hi, top, _) = it["id"], boxes[it["id"]]
        if lo < -EPS or hi > geom["width"] + EPS:
            out.append({"rule": "RESERVE-BOUNDARY", "agency": "none", "status": "geometry", "kind": "boundary",
                        "items": [uid], "required_m": 0.0, "actual_m": min(lo, geom["width"] - hi),
                        "shortfall_m": -min(lo, geom["width"] - hi), "note": "outside the road reserve"})
        if off_id:
            for k, (d0, d1) in enumerate(geom["drains"]):
                gap = max(lo, d0) - min(hi, d1)
                if gap < off - EPS:
                    out.append(_viol(cfg, off_id, [uid, f"drain_{'left' if k == 0 else 'right'}"], off, gap))
        zones = zones_touched(geom, lo, hi)
        need, rid = required_cover(cfg, uid, zones, disabled)
        if rid and top < need - EPS:
            out.append(_viol(cfg, rid, [uid], need, top, "cover to top of utility"))
        if "carriageway" in zones and cfg["utilities"][uid]["chambers"] and uid not in grandfathered:
            for r in _active(cfg, "chamber_ban", disabled):
                out.append(_viol(cfg, r["id"], [uid], None, None, "needs chambers or valves; under carriageway"))
    ids = [it["id"] for it in items]
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            gap = h_gap(boxes[a], boxes[b])
            if gap < -EPS:
                for r in _active(cfg, "no_stacking", disabled):
                    out.append(_viol(cfg, r["id"], [a, b], 0.0, gap, "plan outlines overlap"))
            need, rid = pair_clearance(cfg, cfg["utilities"][a]["type"], cfg["utilities"][b]["type"], disabled)
            if rid and gap < need - EPS:
                out.append(_viol(cfg, rid, [a, b], need, gap))
    return out


def summarise(violations: list[dict]) -> dict:
    by_rule, by_agency = {}, {}
    for v in violations:
        by_rule[v["rule"]] = by_rule.get(v["rule"], 0) + 1
        by_agency[v["agency"]] = by_agency.get(v["agency"], 0) + 1
    return {"total": len(violations), "by_rule": dict(sorted(by_rule.items())),
            "by_agency": dict(sorted(by_agency.items()))}


# ---------------------------------------------------------------- crossings

def _crossed(cfg, geom, items, x_from, x_to):
    """Trunks and drains met by a lateral running from x_from to x_to: (name, type, top, bottom)."""
    lo, hi = min(x_from, x_to), max(x_from, x_to)
    met = []
    for k, (d0, d1) in enumerate(geom["drains"]):
        if d1 > lo + EPS and d0 < hi - EPS:
            met.append((f"drain_{'left' if k == 0 else 'right'}", "drain", 0.0, geom["drain_invert_depth"]))
    for it in items:
        a, b, top, bot = outline(cfg, it)
        if b > lo + EPS and a < hi - EPS:
            met.append((it["id"], cfg["utilities"][it["id"]]["type"], top, bot))
    return met


def check_crossing(cfg: dict, geom: dict, items: list[dict], lateral: dict, disabled=()) -> list[dict]:
    """Violations of a lateral {top, height, x_from, x_to} crossing the trunk utilities and drains."""
    out = []
    top, bot = lateral["top"], lateral["top"] + lateral["height"]
    for name, typ, t_top, t_bot in _crossed(cfg, geom, items, lateral["x_from"], lateral["x_to"]):
        need, under, rid = crossing_rule(cfg, typ, disabled)
        if rid is None:
            continue
        if top >= t_bot - EPS:
            gap, is_under = top - t_bot, True
        elif bot <= t_top + EPS:
            gap, is_under = t_top - bot, False
        else:
            gap, is_under = -(min(bot, t_bot) - max(top, t_top)), False
        if under and not is_under:
            out.append(_viol(cfg, rid, ["lateral", name], need, gap, "must undercross"))
        elif gap < need - EPS:
            out.append(_viol(cfg, rid, ["lateral", name], need, gap, "vertical clearance at crossing"))
    zones = zones_touched(geom, min(lateral["x_from"], lateral["x_to"]), max(lateral["x_from"], lateral["x_to"]))
    for r in _active(cfg, "cover", disabled):
        if r["zone"] in zones and top < r["value_m"] - EPS:
            out.append(_viol(cfg, r["id"], ["lateral"], float(r["value_m"]), top, "cover to top of lateral"))
    return out


def min_undercross_depth(cfg: dict, geom: dict, items: list[dict], x_from: float, x_to: float, disabled=()) -> dict:
    """Shallowest top level of a lateral that passes under everything between x_from and x_to."""
    best, gov, gov_obj = 0.0, None, None
    zones = zones_touched(geom, min(x_from, x_to), max(x_from, x_to))
    for r in _active(cfg, "cover", disabled):
        if r["zone"] in zones and r["value_m"] > best + EPS:
            best, gov, gov_obj = float(r["value_m"]), r["id"], r["zone"]
    for name, typ, _, t_bot in _crossed(cfg, geom, items, x_from, x_to):
        need, _, rid = crossing_rule(cfg, typ, disabled)
        if rid and t_bot + need > best + EPS:
            best, gov, gov_obj = t_bot + need, rid, name
    return {"top_depth_m": best, "governing_rule": gov, "governing_object": gov_obj}


# ---------------------------------------------------------------- cost

def trench_cost(cfg: dict, uid: str, zone: str, cover: float | None = None, disabled=()) -> float:
    """Illustrative trench cost in S$ per metre run: rate x trench width x trench depth."""
    u, g, c = cfg["utilities"][uid], cfg["geometry"], cfg["costs"]
    kind = "carriageway" if zone == "carriageway" else "sidetable"
    if cover is None:
        cover = required_cover(cfg, uid, {kind}, disabled)[0]
    rate = c["carriageway_rate_per_m3"] if kind == "carriageway" else c["sidetable_rate_per_m3"]
    width = u["width_m"] + g["trench_working_width_m"]
    depth = cover + u["height_m"] + g["bedding_m"]
    return rate * width * depth
