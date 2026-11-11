"""Hand-computed cases and behavioural checks added after the first mutation run."""
import copy
import json

import numpy as np
import pytest

from cstcba import costmodel, run, schedule, sensitivity
from scripts import build_readme

HAND = {
    "mb_cost_per_km": 10.0, "escalation": 1.0, "scale_factor": 1.0, "db_capex_ratio": 0.4,
    "events_per_km_yr": 2.0, "event_direct_cost": 0.1, "event_social_cost": 0.2,
    "cst_event_reduction": 0.75, "cst_om_frac": 0.01, "replacement_cycle_yr": 10,
    "db_repl_civil_frac": 0.5, "repl_disruption_events": 5, "cst_repl_civil_frac": 0.1,
    "cst_life_yr": 40, "discount_rate": 0.05,
}


def _hand_expected(social=True):
    v = 1.05
    a = sum(v ** -t for t in range(1, 21))
    r = v ** -10 + v ** -20
    s = 0.2 if social else 0.0
    per = 0.1 + s
    pv_db = 4 + 2 * per * a + (2 + 5 * s) * r
    pv_cst = 10 + (2 * 0.25 * per + 0.1) * a + 0.4 * r - 5 * v ** -20
    return pv_db, pv_cst


@pytest.mark.parametrize("social", [True, False])
def test_hand_computed_case(social):
    res = costmodel.evaluate(HAND, 20, social=social)
    pv_db, pv_cst = _hand_expected(social)
    assert float(res["pv_db"]) == pytest.approx(pv_db, rel=1e-12)
    assert float(res["pv_cst"]) == pytest.approx(pv_cst, rel=1e-12)
    assert float(res["db_capex"]) == pytest.approx(4.0)


def test_vectorised_matches_scalar():
    p = dict(HAND, replacement_cycle_yr=np.array([10.0, 7.0]), cst_life_yr=np.array([40.0, 30.0]))
    v = costmodel.evaluate(p, 20)["npv_cst"]
    for i, (c, life) in enumerate([(10, 40), (7, 30)]):
        assert v[i] == pytest.approx(costmodel.npv(dict(HAND, replacement_cycle_yr=c, cst_life_yr=life), 20))


def test_breakeven_none_without_crossing():
    assert costmodel.breakeven(HAND, "events_per_km_yr", 20, 0.0, 0.1) is None


CFG = costmodel.load_inputs()


def test_tornado_sorted_and_flags():
    rows = sensitivity.tornado(CFG, 100)
    swings = [r["swing"] for r in rows]
    assert swings == sorted(swings, reverse=True)
    flags = {r["param"]: r["flips_decision"] for r in rows}
    assert flags["events_per_km_yr"] is True      # only the high end flips the sign
    assert flags["event_direct_cost"] is False


def test_monte_carlo_probability_consistent_with_median():
    mc = sensitivity.monte_carlo(CFG, 100, draws=2000)
    assert (mc["p_cst_pays"] < 0.5) == (mc["npv_p50"] < 0)
    assert mc["npv_p10"] < mc["npv_p50"] < mc["npv_p90"]


def test_triangular_sampling_uses_mode():
    p = sensitivity.draw_inputs(CFG, 200000, 1)
    spec = CFG["params"]["events_per_km_yr"]
    assert p["events_per_km_yr"].mean() == pytest.approx((spec["low"] + spec["base"] + spec["high"]) / 3, rel=0.01)


def test_cpm_float_of_one_is_not_critical():
    acts = {"a": {"after": []}, "b": {"after": ["a"]}, "c": {"after": ["a"]}, "d": {"after": ["b", "c"]}}
    r = schedule.cpm(acts, {"a": 2, "b": 5, "c": 4, "d": 1})
    assert r["float"]["c"] == 1
    assert "c" not in r["critical"]


def test_delay_slip_equals_delay_minus_float():
    for d in schedule.delay_impacts(schedule.load()):
        assert d["m2_slip"] == max(0.0, d["delay_months"] - d["float_before"])


def test_readme_check_mode(tmp_path, monkeypatch):
    assert build_readme.main(["--check"]) == 0
    stale = tmp_path / "README.md"
    stale.write_text("old", encoding="utf-8")
    monkeypatch.setattr(build_readme, "README", stale)
    assert build_readme.main(["--check"]) == 1


@pytest.fixture(scope="module")
def small_run():
    cfg = copy.deepcopy(CFG)
    cfg["monte_carlo"]["draws"] = 300
    return cfg, run.cost_results(cfg)


def test_run_flip_list_and_scenarios(small_run):
    cfg, out = small_run
    assert out["flip_params_h100"] == [r["param"] for r in out["tornado"]["h100"] if r["flips_decision"]]
    assert out["flip_params_h100"]
    base = costmodel.base_values(cfg)
    hl = {k: v for k, v in cfg["scenarios"]["high_load"].items() if k != "label"}
    assert out["scenarios"]["high_load"]["h100"] == pytest.approx(costmodel.npv(dict(base, **hl), 100))
    assert out["scenarios"]["high_load"]["h100"] != pytest.approx(out["base"]["h100"]["npv_cst"])


def test_readme_claims_hold_in_results():
    """Qualitative statements written in the README template must match results/cost.json."""
    c = json.loads((build_readme.RESULTS / "cost.json").read_text(encoding="utf-8"))
    for h in ("h50", "h100"):
        assert c["base"][h]["npv_cst"] < 0                     # "at the base inputs it does not pay off"
        assert c["scenarios"]["moderate_load"][h] < 0
        assert c["scenarios"]["high_load"][h] > 0
        assert c["monte_carlo"][f"{h}_financial_only"]["p_cst_pays"] < 0.05   # "almost never"
    assert set(c["flip_params_h100"]) == {"events_per_km_yr", "event_social_cost"}
    s = json.loads((build_readme.RESULTS / "schedule.json").read_text(encoding="utf-8"))
    late = [d for d in s["delays"] if d["activity"] == "J" and d["delay_months"] > d["float_before"]]
    assert late and all("J" in d["critical_after"] for d in late)
    first = [d for d in s["delays"] if d["activity"] == "C"][0]
    assert first["m1_slip"] == first["m2_slip"] == first["delay_months"]
