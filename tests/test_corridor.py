"""Corridor module: rule lookup, checker geometry (hand-worked), crossings, cost and optimiser.

Hand-worked numbers use the local reserve of inputs/corridor.yaml: 15.4 m wide, 7.4 m carriageway, so
4.0 m sidetables, kerbs at x = 4.0 and 11.4, drains over [0, 1] and [14.4, 15.4]. Outer sizes: gas 0.16,
sewer 0.40, water 0.33, telecom 0.30 x 0.30, power_hv 0.60 x 0.30.
"""
import copy
import json
import xml.etree.ElementTree as ET

import pytest

from cstcba import corridor as co
from cstcba import corridor_draw, corridor_opt as op, corridor_run

CFG = co.load()
LOCAL = co.geometry(CFG, "local")
ROOT = co.ROOT


def item(uid, x, cover=1.2):
    return {"id": uid, "x": x, "cover": cover}


def rules_hit(violations):
    return sorted(v["rule"] for v in violations)


# ---------------------------------------------------------------- rule lookup

@pytest.mark.parametrize("a,b,value,rule", [
    ("sewer", "gas", 1.0, "PUB-SEWER-PARALLEL"),
    ("gas", "sewer", 1.0, "PUB-SEWER-PARALLEL"),
    ("gas", "telecom", 0.3, "SP-GAS-CLEARANCE"),
    ("telecom", "power", 0.3, "IMDA-TELECOM-POWER"),
    ("power", "telecom", 0.3, "IMDA-TELECOM-POWER"),
    ("power", "dcs", 0.3, "DEFAULT-CLEARANCE"),
    ("water", "telecom", 1.0, "PUB-WATER-PARALLEL"),
    ("sewer", "water", 1.0, "PUB-SEWER-PARALLEL"),
])
def test_pair_clearance(a, b, value, rule):
    assert co.pair_clearance(CFG, a, b) == (value, rule)


def test_pair_clearance_falls_back_when_rule_disabled():
    assert co.pair_clearance(CFG, "water", "telecom", disabled=("PUB-WATER-PARALLEL",)) == (0.3, "DEFAULT-CLEARANCE")
    assert co.pair_clearance(CFG, "sewer", "gas", disabled=("PUB-SEWER-PARALLEL",)) == (0.3, "SP-GAS-CLEARANCE")


def test_required_cover():
    assert co.required_cover(CFG, "gas", {"sidetable"}) == (1.2, "LTA-DEPTH-SIDETABLE")
    assert co.required_cover(CFG, "gas", {"carriageway"}) == (1.0, "LTA-DEPTH-CARRIAGEWAY")
    assert co.required_cover(CFG, "gas", {"sidetable", "carriageway"})[0] == 1.2
    # sewer invert at 1.5 m, pipe 0.40 high -> top at 1.1 m, deeper than the 1.0 m carriageway cover
    val, rid = co.required_cover(CFG, "sewer", {"carriageway"})
    assert val == pytest.approx(1.1) and rid == "PUB-SEWER-DEPTH"
    assert co.required_cover(CFG, "water", {"carriageway"}, disabled=("LTA-DEPTH-CARRIAGEWAY",)) == \
        (1.0, "PUB-WATER-COVER")


def test_crossing_rule():
    assert co.crossing_rule(CFG, "water") == (1.0, True, "PUB-WATER-CROSSING")
    assert co.crossing_rule(CFG, "sewer") == (1.0, False, "PUB-SEWER-CROSSING")
    assert co.crossing_rule(CFG, "drain") == (1.0, True, "PUB-DRAIN-UNDERCROSS")
    assert co.crossing_rule(CFG, "gas") == (0.3, False, "SP-GAS-CROSSING")
    assert co.crossing_rule(CFG, "power") == (0.3, False, "DEFAULT-CROSSING")


def test_rule_table_integrity():
    for r in CFG["rules"]:
        assert r["clause"].strip()
        if r["status"] == "sourced":
            assert r["source"] in CFG["sources"]
            assert CFG["sources"][r["source"]]["url"].startswith("https://")
        else:
            assert "ASSUMPTION" in r["text"]
    assert {r["id"] for r in CFG["rules"] if r["status"] == "assumption"} == {
        "PUB-WATER-PARALLEL", "DEFAULT-CLEARANCE", "DEFAULT-CROSSING"}


@pytest.mark.parametrize("edit,msg", [
    (lambda c: c["rules"].append(dict(c["rules"][0])), "duplicate"),
    (lambda c: c["rules"][0].update(source="C99"), "known source"),
    (lambda c: co.rule(c, "DEFAULT-CLEARANCE").update(text="0.3 m working clearance"), "labelled"),
    (lambda c: c["rules"][0].update(status="guess"), "status"),
    (lambda c: c["reserves"]["local"].update(carriageway_m=14.0), "do not fit"),
    (lambda c: c["reserves"]["local"]["utilities"].append("steam"), "unknown utility"),
])
def test_validate_rejects_bad_input(edit, msg):
    cfg = copy.deepcopy(CFG)
    edit(cfg)
    with pytest.raises(ValueError, match=msg):
        co.validate(cfg)


# ---------------------------------------------------------------- geometry and checker

def test_geometry_local():
    assert LOCAL["verge"] == pytest.approx(4.0)
    assert (LOCAL["kerb_left"], LOCAL["kerb_right"]) == pytest.approx((4.0, 11.4))
    assert LOCAL["drains"] == [(0.0, 1.0), (pytest.approx(14.4), pytest.approx(15.4))]
    assert co.geometry(CFG, "local", verge=3.0)["width"] == pytest.approx(13.4)


def test_zones():
    assert co.zones_touched(LOCAL, 2.0, 2.5) == {"sidetable"}
    assert co.zones_touched(LOCAL, 5.0, 5.5) == {"carriageway"}
    assert co.zones_touched(LOCAL, 3.9, 4.2) == {"sidetable", "carriageway"}
    assert co.zones_touched(LOCAL, 12.0, 12.5) == {"sidetable"}
    assert [co.zone_name(LOCAL, a, b) for a, b in ((2.0, 4.0), (4.0, 4.6), (11.4, 12.0), (3.9, 4.2))] == \
        ["left", "carriageway", "right", "straddle"]


def test_clean_layout_has_no_violations():
    # gas: outline 1.30-1.46, exactly 0.30 from the drain; sewer: outline 2.46-2.86, exactly 1.00 from gas
    assert co.check_layout(CFG, LOCAL, [item("gas", 1.38), item("sewer", 2.66)]) == []


def test_sewer_parallel_clearance_violation():
    v = co.check_layout(CFG, LOCAL, [item("gas", 1.38), item("sewer", 2.65)])
    assert rules_hit(v) == ["PUB-SEWER-PARALLEL"]
    assert v[0]["actual_m"] == pytest.approx(0.99) and v[0]["shortfall_m"] == pytest.approx(0.01)
    assert v[0]["agency"] == "PUB" and v[0]["items"] == ["gas", "sewer"]


def test_gas_clearance_is_measured_between_outlines():
    # telecom outline 2.00-2.30, gas outline 2.59-2.75: gap 0.29 < 0.30
    assert rules_hit(co.check_layout(CFG, LOCAL, [item("telecom", 2.15), item("gas", 2.67)])) == ["SP-GAS-CLEARANCE"]
    assert co.check_layout(CFG, LOCAL, [item("telecom", 2.15), item("gas", 2.68)]) == []


def test_drain_offset_both_sides():
    assert rules_hit(co.check_layout(CFG, LOCAL, [item("gas", 1.37)])) == ["PUB-DRAIN-OFFSET"]
    # water outline right edge must stay at or left of 14.4 - 0.3 = 14.1 -> centre 13.935
    assert co.check_layout(CFG, LOCAL, [item("water", 13.935)]) == []
    v = co.check_layout(CFG, LOCAL, [item("water", 13.945)])
    assert rules_hit(v) == ["PUB-DRAIN-OFFSET"] and v[0]["items"] == ["water", "drain_right"]
    assert v[0]["actual_m"] == pytest.approx(0.29)


def test_cover_rules():
    assert rules_hit(co.check_layout(CFG, LOCAL, [item("gas", 2.0, cover=1.19)])) == ["LTA-DEPTH-SIDETABLE"]
    assert co.check_layout(CFG, LOCAL, [item("power_hv", 6.0, cover=1.0)]) == []
    assert rules_hit(co.check_layout(CFG, LOCAL, [item("power_hv", 6.0, cover=0.95)])) == ["LTA-DEPTH-CARRIAGEWAY"]
    # straddling the kerb takes the deeper of the two
    assert rules_hit(co.check_layout(CFG, LOCAL, [item("power_hv", 4.0, cover=1.0)])) == ["LTA-DEPTH-SIDETABLE"]


def test_chamber_ban_and_grandfathering():
    v = co.check_layout(CFG, LOCAL, [item("sewer", 6.0, cover=1.1)])
    assert rules_hit(v) == ["LTA-NO-CHAMBER-CARRIAGEWAY"]
    assert co.check_layout(CFG, LOCAL, [item("sewer", 6.0, cover=1.1)], grandfathered=["sewer"]) == []
    assert co.check_layout(CFG, LOCAL, [item("sewer", 2.0)]) == []           # in the sidetable: no ban
    v = co.check_layout(CFG, LOCAL, [item("sewer", 6.0, cover=1.05)], grandfathered=["sewer"])
    assert rules_hit(v) == ["PUB-SEWER-DEPTH"]


def test_stacking_and_boundary():
    v = co.check_layout(CFG, LOCAL, [item("telecom", 2.0), item("power_hv", 2.2)])
    assert rules_hit(v) == ["IMDA-TELECOM-POWER", "LTA-NO-STACKING"]
    v = co.check_layout(CFG, LOCAL, [item("gas", 15.35)])
    assert rules_hit(v) == ["PUB-DRAIN-OFFSET", "RESERVE-BOUNDARY"]


def test_disabled_rule_is_not_reported():
    lay = [item("gas", 1.38), item("sewer", 2.0)]
    assert rules_hit(co.check_layout(CFG, LOCAL, lay)) == ["PUB-SEWER-PARALLEL"]
    # gap is 1.80 - 1.46 = 0.34, enough for the 0.30 gas rule that takes over
    assert co.check_layout(CFG, LOCAL, lay, disabled=("PUB-SEWER-PARALLEL",)) == []
    assert rules_hit(co.check_layout(CFG, LOCAL, [item("gas", 1.38), item("sewer", 1.95)],
                                     disabled=("PUB-SEWER-PARALLEL",))) == ["SP-GAS-CLEARANCE"]

def test_summarise():
    v = co.check_layout(CFG, LOCAL, [item("gas", 1.37), item("sewer", 2.0), item("telecom", 2.5, cover=0.5)])
    s = co.summarise(v)
    assert s["total"] == len(v) == sum(s["by_rule"].values()) == sum(s["by_agency"].values())
    assert s["by_agency"]["PUB"] == 3 and s["by_agency"]["LTA"] == 1


# ---------------------------------------------------------------- crossings

TRUNKS = [item("gas", 2.0), item("sewer", 13.0), item("water", 3.0)]


def test_min_undercross_depth_hand_values():
    # across the left drain and the gas main only: drain invert 1.0 + 1.0 = 2.0 governs
    d = co.min_undercross_depth(CFG, LOCAL, TRUNKS, 0.0, 2.5)
    assert d["top_depth_m"] == pytest.approx(2.0) and d["governing_rule"] == "PUB-DRAIN-UNDERCROSS"
    # gas only: 1.2 + 0.16 + 0.3 = 1.66
    d = co.min_undercross_depth(CFG, LOCAL, TRUNKS, 1.5, 2.5)
    assert d["top_depth_m"] == pytest.approx(1.66) and d["governing_rule"] == "SP-GAS-CROSSING"
    # water: 1.2 + 0.33 + 1.0 = 2.53
    d = co.min_undercross_depth(CFG, LOCAL, TRUNKS, 1.5, 3.5)
    assert d["top_depth_m"] == pytest.approx(2.53) and d["governing_object"] == "water"
    # whole reserve: sewer bottom 1.6 + 1.0 = 2.6
    d = co.min_undercross_depth(CFG, LOCAL, TRUNKS, 0.0, LOCAL["width"])
    assert d["top_depth_m"] == pytest.approx(2.6) and d["governing_rule"] == "PUB-SEWER-CROSSING"
    # nothing crossed in the carriageway: LTA cover
    d = co.min_undercross_depth(CFG, LOCAL, TRUNKS, 5.0, 9.0)
    assert d["top_depth_m"] == pytest.approx(1.0) and d["governing_rule"] == "LTA-DEPTH-CARRIAGEWAY"


def test_lateral_at_min_depth_passes_and_shallower_fails():
    d = co.min_undercross_depth(CFG, LOCAL, TRUNKS, 0.0, LOCAL["width"])["top_depth_m"]
    lat = {"top": d, "height": 0.1, "x_from": 0.0, "x_to": LOCAL["width"]}
    assert co.check_crossing(CFG, LOCAL, TRUNKS, lat) == []
    v = co.check_crossing(CFG, LOCAL, TRUNKS, dict(lat, top=d - 0.05))
    assert rules_hit(v) == ["PUB-SEWER-CROSSING"] and v[0]["actual_m"] == pytest.approx(0.95)


def test_water_must_be_undercrossed():
    deep_water = [item("water", 3.0, cover=3.0)]
    lat = {"top": 1.2, "height": 0.1, "x_from": 2.0, "x_to": 3.9}
    v = co.check_crossing(CFG, LOCAL, deep_water, lat)      # 1.7 m above the main, but over it
    assert rules_hit(v) == ["PUB-WATER-CROSSING"] and v[0]["note"] == "must undercross"


def test_sewer_may_be_overcrossed_with_one_metre():
    lat = {"top": 1.2, "height": 0.2, "x_from": 12.0, "x_to": 13.9}
    assert co.check_crossing(CFG, LOCAL, [item("sewer", 13.0, cover=2.4)], lat) == []
    v = co.check_crossing(CFG, LOCAL, [item("sewer", 13.0, cover=2.3)], lat)
    assert rules_hit(v) == ["PUB-SEWER-CROSSING"] and v[0]["actual_m"] == pytest.approx(0.9)
    v = co.check_crossing(CFG, LOCAL, [item("sewer", 13.0, cover=1.3)], lat)    # clash
    assert v[0]["actual_m"] < 0


def test_lateral_cover_and_drain():
    lat = {"top": 1.1, "height": 0.1, "x_from": 0.0, "x_to": 1.2}
    assert rules_hit(co.check_crossing(CFG, LOCAL, [], lat)) == ["LTA-DEPTH-SIDETABLE", "PUB-DRAIN-UNDERCROSS"]


# ---------------------------------------------------------------- cost

def test_trench_cost_hand_values():
    # gas in the sidetable: 150 x (0.16 + 0.6) x (1.2 + 0.16 + 0.15) = 172.14
    assert co.trench_cost(CFG, "gas", "left") == pytest.approx(172.14)
    # gas under the carriageway: 400 x 0.76 x (1.0 + 0.16 + 0.15) = 398.24
    assert co.trench_cost(CFG, "gas", "carriageway") == pytest.approx(398.24)
    assert co.trench_cost(CFG, "gas", "right", cover=2.0) == pytest.approx(150 * 0.76 * 2.31)


# ---------------------------------------------------------------- optimiser

def toy(utilities):
    cfg = copy.deepcopy(CFG)
    cfg["reserves"]["toy"] = {"label": "toy", "reserve_width_m": 15.4, "carriageway_m": 7.4, "utilities": utilities}
    return cfg


def test_min_width_two_utilities_by_hand():
    # one per side: the wider (sewer) needs 1.0 drain + 0.3 offset + 0.40 = 1.70 m of sidetable
    cfg = toy(["sewer", "gas"])
    sol = op.solve(cfg, "toy", ["sewer", "gas"], "width")
    assert sol["verge_m"] == pytest.approx(1.70, abs=1e-5)
    assert sol["reserve_width_m"] == pytest.approx(7.4 + 3.4, abs=1e-5)


def test_min_width_three_utilities_by_hand():
    # sewer alone on one side; water and gas share the other: 1.3 + 0.33 + 1.0 + 0.16 = 2.79
    cfg = toy(["sewer", "water", "gas"])
    ids = ["sewer", "water", "gas"]
    assert op.solve(cfg, "toy", ids, "width")["verge_m"] == pytest.approx(2.79, abs=1e-5)
    # without the assumed water clearance the gas rule governs: 1.3 + 0.33 + 0.3 + 0.16 = 2.09
    alt = op.solve(cfg, "toy", ids, "width", disabled=("PUB-WATER-PARALLEL",))
    assert alt["verge_m"] == pytest.approx(2.09, abs=1e-5)


def test_local_min_width_and_layout_is_compliant():
    ids = CFG["reserves"]["local"]["utilities"]
    sol = op.solve(CFG, "local", ids, "width")
    # left gas + sewer = 2.86, right water + telecom = 1.3 + 0.33 + 1.0 + 0.30 = 2.93, power under the road
    assert sol["verge_m"] == pytest.approx(2.93, abs=1e-5)
    assert co.check_layout(CFG, sol["geometry"], sol["items"]) == []
    assert [it["id"] for it in sol["items"] if it["zone"] == "carriageway"] == ["power_hv"]
    assert sol["waived"] == []


@pytest.mark.parametrize("disabled", [(), ("PUB-SEWER-PARALLEL",), ("PUB-WATER-PARALLEL",), ("PUB-DRAIN-OFFSET",)])
def test_mip_matches_exhaustive_enumeration(disabled):
    ids = CFG["reserves"]["local"]["utilities"]
    brute = op.brute_min_verge(CFG, "local", ids, disabled)
    sol = op.solve(CFG, "local", ids, "width", disabled=disabled, off_carriageway=["power_hv"])
    assert sol["verge_m"] == pytest.approx(brute, abs=1e-5)
    assert all(it["zone"] != "carriageway" for it in sol["items"])


def test_exhaustive_value_by_hand():
    # everything off the carriageway: {sewer, gas} = 2.86 and {telecom, power, water} = 1.3+0.3+0.3+0.6+1.0+0.33 = 3.83,
    # or {gas, telecom, power} = 1.3+0.16+0.3+0.3+0.3+0.6 = 2.96 with {sewer, water} = 1.3+0.4+1.0+0.33 = 3.03
    assert op.brute_min_verge(CFG, "local", CFG["reserves"]["local"]["utilities"]) == pytest.approx(3.03)


def test_chamber_rule_off_lets_everything_under_the_road():
    ids = CFG["reserves"]["local"]["utilities"]
    sol = op.solve(CFG, "local", ids, "width", disabled=("LTA-NO-CHAMBER-CARRIAGEWAY",))
    assert sol["verge_m"] == pytest.approx(1.0, abs=1e-5)       # only the drain is left in the sidetable


def test_cost_layout_local():
    ids = CFG["reserves"]["local"]["utilities"]
    sol = op.solve(CFG, "local", ids, "cost")
    floor = sum(co.trench_cost(CFG, u, "left") for u in ids)
    assert sol["objective"] == pytest.approx(floor) == pytest.approx(op.total_cost(CFG, sol["items"]))
    assert all(it["zone"] != "carriageway" for it in sol["items"])
    assert co.check_layout(CFG, co.geometry(CFG, "local"), sol["items"]) == []


def test_narrow_reserve_needs_a_waiver():
    ids = CFG["reserves"]["local"]["utilities"]
    with pytest.raises(op.Infeasible):
        op.solve(CFG, "local", ids, "cost", verge=2.5)
    w = op.solve(CFG, "local", ids, "waivers", verge=2.5, strict_chambers=False)
    assert round(w["objective"]) == 1 and len(w["waived"]) == 1
    sol = op.solve(CFG, "local", ids, "cost", verge=2.5, strict_chambers=False, max_waivers=1)
    geom = co.geometry(CFG, "local", 2.5)
    assert len(sol["waived"]) == 1
    assert rules_hit(co.check_layout(CFG, geom, sol["items"])) == ["LTA-NO-CHAMBER-CARRIAGEWAY"]
    assert co.check_layout(CFG, geom, sol["items"], grandfathered=sol["waived"]) == []


def test_pack_positions_by_hand():
    ids = ["gas", "sewer", "water"]
    x = op.pack(CFG, LOCAL, ids, ["left", "left", "right"], [0, 1, 2], ())
    assert x[0] == pytest.approx(1.38) and x[1] == pytest.approx(2.66) and x[2] == pytest.approx(13.935)
    # sewer then gas then telecom then power cannot fit in a 4.0 m sidetable together with water
    assert op.pack(CFG, LOCAL, ["sewer", "water", "gas", "power_hv", "telecom"], ["left"] * 5, [0, 1, 2, 3, 4], ()) is None


def test_binding_reports_tight_pairs():
    items = [dict(item("gas", 1.38), zone="left"), dict(item("sewer", 2.66), zone="left"),
             dict(item("telecom", 13.0), zone="right")]
    b = op.binding(CFG, LOCAL, items)
    assert {"rule": "PUB-SEWER-PARALLEL", "items": ["gas", "sewer"], "clearance_m": 1.0} in b
    assert {"rule": "PUB-DRAIN-OFFSET", "items": ["gas", "drain"], "clearance_m": 0.3} in b
    assert all("telecom" not in t["items"] for t in b)


# ---------------------------------------------------------------- worked examples and brownfield

@pytest.fixture(scope="module")
def local_example():
    return corridor_run.example(CFG, "local")


@pytest.fixture(scope="module")
def brown():
    return corridor_run.brownfield(CFG)


def test_local_example(local_example):
    ex = local_example
    assert ex["min_width"]["reserve_width_m"] == pytest.approx(13.26, abs=1e-4)
    assert ex["min_width"]["spare_reserve_m"] == pytest.approx(2.14, abs=1e-4) and ex["min_width"]["fits"]
    sav = {d["rule"]: d["saving_m"] for d in ex["relaxation"]}
    assert sav["LTA-NO-CHAMBER-CARRIAGEWAY"] == pytest.approx(13.26 - 9.4, abs=1e-4)
    assert sav["SP-GAS-CLEARANCE"] == pytest.approx(0.0, abs=1e-4)
    assert all(s >= -1e-6 for s in sav.values())
    assert "SP-GAS-CLEARANCE" not in ex["binding_rules"] and ex["binding_rules"][0] == "LTA-NO-CHAMBER-CARRIAGEWAY"
    assert ex["as_given"]["feasible_without_waiver"] and ex["as_given"]["premium_per_m"] == pytest.approx(0.0)
    assert ex["crossing"]["top_depth_m"] == pytest.approx(2.6)
    assert ex["water_sensitivity"]["saving_m"] > 0


def test_brownfield_audit_by_hand(brown):
    v = {x["rule"]: x for x in brown["as_built"]["violations"]}
    assert set(v) == {"LTA-DEPTH-SIDETABLE", "PUB-SEWER-PARALLEL", "PUB-WATER-PARALLEL"}
    assert v["PUB-SEWER-PARALLEL"]["actual_m"] == pytest.approx(0.42)       # 2.52 - 2.10
    assert v["PUB-WATER-PARALLEL"]["actual_m"] == pytest.approx(0.285)      # 19.05 - 18.765
    assert v["LTA-DEPTH-SIDETABLE"]["items"] == ["telecom"]
    assert brown["as_built"]["in_conflict"] == ["gas", "sewer", "telecom", "telecom_b", "water"]


def test_brownfield_cure_by_hand(brown):
    cure = brown["cure_only"]
    # cheapest: relay telecom (cover), gas (not the sewer) and telecom_b (not the water main)
    assert cure["diverted"] == ["gas", "telecom", "telecom_b"]
    assert cure["cost_per_m"] == pytest.approx(1.5 * (172.14 + 222.75 + 222.75))
    as_built = {it["id"]: it["x_m"] for it in brown["as_built"]["items"]}
    for it in cure["items"]:
        if it["id"] not in cure["diverted"]:
            assert it["x_m"] == pytest.approx(as_built[it["id"]])


def test_brownfield_add(brown):
    add = brown["cure_and_add"]
    assert add["cost_per_m"] >= brown["cure_only"]["cost_per_m"]
    assert list(add["new_zone"]) == ["newater"] and add["new_zone"]["newater"] in ("left", "right")
    assert add["cost_per_m"] == pytest.approx(add["new_utility_cost_per_m"] + add["diversion_cost_per_m"])
    assert brown["extra_cost_of_adding_per_m"] == pytest.approx(add["cost_per_m"] - brown["cure_only"]["cost_per_m"])
    assert brown["extra_cost_of_adding_per_m"] >= brown["new_utility_greenfield_cost_per_m"] - 1e-6
    geom = co.geometry(CFG, "primary")
    items = [{"id": it["id"], "x": it["x_m"], "cover": it["cover_m"]} for it in add["items"]]
    assert co.check_layout(CFG, geom, items) == []


def test_existing_chambered_utility_under_road_is_grandfathered():
    existing = {"sewer": {"x": 6.0, "cover": 1.2}}
    sol = op.solve(CFG, "local", ["sewer"], "cost", existing=existing)
    assert sol["moved"] == [] and sol["objective"] == pytest.approx(0.0)
    assert sol["items"][0]["x"] == pytest.approx(6.0)


# ---------------------------------------------------------------- tests added after the first mutation run

def test_largest_applicable_clearance_governs_whatever_the_rule_order():
    cfg = copy.deepcopy(CFG)
    cfg["rules"].reverse()                      # the default 0.3 m rule now comes first
    assert co.pair_clearance(cfg, "sewer", "gas") == (1.0, "PUB-SEWER-PARALLEL")
    assert co.pair_clearance(cfg, "water", "power") == (1.0, "PUB-WATER-PARALLEL")
    assert co.pair_clearance(cfg, "power", "dcs")[0] == 0.3


def test_relaid_chambered_utility_may_not_return_under_the_road():
    # a sewer under the carriageway with too little cover has to be relaid; with 1.5 m sidetables there is
    # no room off the carriageway, so the placement model itself must be infeasible
    existing = {"sewer": {"x": 6.0, "cover": 0.9}}
    with pytest.raises(op.Infeasible, match="problem is infeasible"):
        op.solve(CFG, "local", ["sewer"], "cost", existing=existing, verge=1.5)
    # with the full 4.0 m sidetable it is relaid there at 1.5 x the sidetable trench cost
    sol = op.solve(CFG, "local", ["sewer"], "cost", existing=existing)
    assert sol["moved"] == ["sewer"] and sol["items"][0]["zone"] != "carriageway"
    assert sol["objective"] == pytest.approx(1.5 * co.trench_cost(CFG, "sewer", "left"))


def test_congestion_premium_by_hand(brown):
    # adding the NEWater main forces the water main to move as well: 1.5 x 150 x 0.93 x 1.68 = 351.54
    assert brown["new_utility_greenfield_cost_per_m"] == pytest.approx(150 * 0.82 * 1.57)
    assert brown["congestion_premium_per_m"] == pytest.approx(
        brown["extra_cost_of_adding_per_m"] - brown["new_utility_greenfield_cost_per_m"])
    assert brown["congestion_premium_per_m"] == pytest.approx(351.54)
    assert set(brown["cure_and_add"]["diverted"]) - set(brown["cure_only"]["diverted"]) == {"water"}


def test_example_reports_waiver_when_the_reserve_is_too_narrow():
    cfg = copy.deepcopy(CFG)
    cfg["reserves"]["narrow"] = {"label": "narrow", "reserve_width_m": 12.4, "carriageway_m": 7.4,
                                 "utilities": list(CFG["reserves"]["local"]["utilities"])}
    ex = corridor_run.example(cfg, "narrow")
    assert ex["min_width"]["fits"] is False and ex["min_width"]["spare_reserve_m"] == pytest.approx(12.4 - 13.26, abs=1e-4)
    g = ex["as_given"]
    assert g["feasible_without_waiver"] is False and g["waivers_needed"] == 1 and len(g["waived"]) == 1
    assert g["premium_per_m"] > 0 and g["waived"][0] in g["under_carriageway"]


# ---------------------------------------------------------------- committed results, docs and drawings

def committed():
    return json.loads((ROOT / "results" / "corridor.json").read_text(encoding="utf-8"))


def test_every_committed_layout_passes_the_checker():
    res = committed()
    for name, ex in res["examples"].items():
        mw = ex["min_width"]
        geom = co.geometry(CFG, name, mw["verge_m"])
        items = [{"id": it["id"], "x": it["x_m"], "cover": it["cover_m"]} for it in mw["items"]]
        assert co.check_layout(CFG, geom, items) == [], name
        assert geom["width"] == pytest.approx(mw["reserve_width_m"], abs=1e-3)
        g = ex["as_given"]
        items = [{"id": it["id"], "x": it["x_m"], "cover": it["cover_m"], "zone": it["zone"]} for it in g["items"]]
        assert co.check_layout(CFG, co.geometry(CFG, name), items, grandfathered=g["waived"]) == [], name
        assert op.total_cost(CFG, items) == pytest.approx(g["cost_per_m"], abs=0.01)
        assert len(items) == ex["n_utilities"] == len(CFG["reserves"][name]["utilities"])


def test_committed_rule_counts_match_inputs():
    res = committed()["rules"]
    assert res["n_total"] == len(CFG["rules"]) == res["n_sourced"] + res["n_assumption"]
    assert res["n_assumption"] == 3 and res["n_sources"] == len(CFG["sources"])


def test_rules_doc_and_drawings_are_fresh():
    assert (ROOT / "docs" / "corridor_rules.md").read_text(encoding="utf-8") == corridor_run.rules_markdown(CFG)
    for name, text in corridor_run.drawings(CFG, committed()).items():
        assert (ROOT / "docs" / "img" / name).read_text(encoding="utf-8") == text, name


def test_rules_doc_cites_every_rule_and_source():
    md = corridor_run.rules_markdown(CFG)
    for r in CFG["rules"]:
        assert f"`{r['id']}`" in md and r["clause"] in md
    for s in CFG["sources"].values():
        assert s["url"] in md
    assert "not a URA/agency study" in md


def test_svg_is_well_formed_and_marks_conflicts():
    items = [item("gas", 1.38), item("sewer", 2.0)]
    text = corridor_draw.svg(CFG, LOCAL, items, "t", flagged={"sewer"})
    root = ET.fromstring(text)
    assert root.tag.endswith("svg")
    assert "need 1.00" in text and text.count('stroke="#cc0000" stroke-width="2.5"') == 1
    assert "Not an agency drawing" in text


@pytest.mark.golden
def test_corridor_results_match_inputs():
    fresh = json.loads(json.dumps(corridor_run.results(CFG), default=float))
    old = committed()
    assert fresh["rules"] == old["rules"]
    for name, ex in old["examples"].items():
        f = fresh["examples"][name]
        assert f["min_width"]["reserve_width_m"] == pytest.approx(ex["min_width"]["reserve_width_m"], abs=1e-3)
        assert f["as_given"]["cost_per_m"] == pytest.approx(ex["as_given"]["cost_per_m"], abs=0.01)
        assert f["as_given"]["waivers_needed"] == ex["as_given"]["waivers_needed"]
        assert f["crossing"]["top_depth_m"] == pytest.approx(ex["crossing"]["top_depth_m"], abs=1e-3)
        assert f["water_sensitivity"]["reserve_width_m"] == pytest.approx(ex["water_sensitivity"]["reserve_width_m"], abs=1e-3)
        for a, b in zip(sorted(f["relaxation"], key=lambda d: d["rule"]), sorted(ex["relaxation"], key=lambda d: d["rule"])):
            assert a["rule"] == b["rule"] and a["saving_m"] == pytest.approx(b["saving_m"], abs=1e-3)
    for key in ("cure_only", "cure_and_add"):
        assert fresh["brownfield"][key]["cost_per_m"] == pytest.approx(old["brownfield"][key]["cost_per_m"], abs=0.01)
    assert fresh["brownfield"]["as_built"]["summary"] == old["brownfield"]["as_built"]["summary"]
