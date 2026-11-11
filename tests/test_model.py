import math

import pytest

from cstcba import costmodel, discount, sensitivity

CFG = costmodel.load_inputs()
BASE = costmodel.base_values(CFG)


def test_green_book_rates():
    assert discount.rate_for_year(1) == 0.03
    assert discount.rate_for_year(30) == 0.03
    assert discount.rate_for_year(31) == 0.025
    assert discount.rate_for_year(76) == 0.0225


def test_flat_factors():
    df = discount.factors(10, 0.05)
    assert df[0] == 1.0
    assert df[10] == pytest.approx(1.05 ** -10)


def test_schedule_factor_year_40():
    df = discount.factors(40)
    assert df[40] == pytest.approx(1.03 ** -30 * 1.025 ** -10)


def test_npv_increases_with_openings():
    lo = costmodel.npv(dict(BASE, events_per_km_yr=1.0), 100)
    hi = costmodel.npv(dict(BASE, events_per_km_yr=8.0), 100)
    assert hi > lo


def test_npv_is_difference_of_pvs():
    r = costmodel.evaluate(BASE, 100)
    assert float(r["npv_cst"]) == pytest.approx(float(r["pv_db"] - r["pv_cst"]))


def test_breakeven_zeroes_npv():
    x = costmodel.breakeven(BASE, "events_per_km_yr", 100, 0.0, 60.0)
    assert x is not None
    assert costmodel.npv(dict(BASE, events_per_km_yr=x), 100) == pytest.approx(0.0, abs=1e-3)


def test_financial_view_is_worse():
    assert costmodel.npv(BASE, 100, social=False) < costmodel.npv(BASE, 100)


def test_tornado_covers_all_assumptions():
    rows = sensitivity.tornado(CFG, 100)
    assert {r["param"] for r in rows} == set(sensitivity.swept_params(CFG))


def test_monte_carlo_reproducible():
    a = sensitivity.monte_carlo(CFG, 50, draws=500)
    b = sensitivity.monte_carlo(CFG, 50, draws=500)
    assert a == b
    assert 0.0 <= a["p_cst_pays"] <= 1.0


def test_inputs_are_sourced_or_swept():
    src_ids = open(costmodel.ROOT / "docs" / "sources.md", encoding="utf-8").read()
    for name, spec in CFG["params"].items():
        if spec["kind"] == "source":
            assert f"| {spec['source']} |" in src_ids, name
        else:
            assert spec["kind"] == "assumption", name
            if spec["base"] is not None:
                assert spec["low"] < spec["base"] < spec["high"], name
            else:
                assert spec["low"] < spec["high"], name
    for spec in CFG["params"].values():
        if "informed_by" in spec:
            assert f"| {spec['informed_by']} |" in src_ids
    assert math.isclose(CFG["params"]["mb_cost_per_km"]["value"], round((81 + 137) / 3.0, 2))
