import pytest

from cstcba import interfaces, schedule

TOY = {
    "a": {"after": []},
    "b": {"after": ["a"]},
    "c": {"after": ["a"]},
    "d": {"after": ["b", "c"]},
}


def test_cpm_toy():
    r = schedule.cpm(TOY, {"a": 2, "b": 5, "c": 3, "d": 1})
    assert r["finish"] == 8
    assert r["critical"] == ["a", "b", "d"]
    assert r["float"]["c"] == 2


def test_cycle_detected():
    with pytest.raises(ValueError):
        schedule.topo_order({"x": {"after": ["y"]}, "y": {"after": ["x"]}})


def test_delay_within_float_does_not_slip():
    cfg = schedule.load()
    for d in schedule.delay_impacts(cfg):
        if d["delay_months"] <= d["float_before"]:
            assert d["m2_slip"] == 0


def test_interface_matrix_symmetric():
    cfg = interfaces.load()
    m = interfaces.matrix(cfg)
    for a in m:
        for b in m:
            assert m[a][b] == m[b][a]


def test_interface_missing_pair_rejected():
    cfg = interfaces.load()
    cfg = dict(cfg, pairs=cfg["pairs"][1:])
    with pytest.raises(ValueError):
        interfaces.matrix(cfg)
