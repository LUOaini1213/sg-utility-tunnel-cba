"""Lifecycle cost model per km: common services tunnel (CST) vs direct-buried (DB) utilities.

All money in SGD million per km, real. Costs common to both options (the pipes and
cables themselves) are excluded; only the differences are modelled.
NPV_CST = PV(DB costs) - PV(CST costs): positive means the CST pays off.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from . import discount

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "inputs" / "cost_inputs.yaml"


def load_inputs(path: Path = INPUTS) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def base_values(cfg: dict) -> dict:
    out = {}
    for name, spec in cfg["params"].items():
        out[name] = spec["value"] if spec["kind"] == "source" else spec["base"]
    return out


def evaluate(p: dict, horizon: int, social: bool = True) -> dict:
    """Return PV components. Values in p may be floats or equal-length numpy arrays.

    p["discount_rate"] None -> Green Book 2026 schedule, else a flat real rate (float only).
    social=False gives the agency/financial view (no disruption costs counted).
    """
    df = discount.factors(horizon, p.get("discount_rate"))
    annuity = df[1:].sum()

    cst_capex = np.asarray(p["mb_cost_per_km"] * p["escalation"] * p["scale_factor"], dtype=float)
    db_capex = cst_capex * p["db_capex_ratio"]

    social_cost = p["event_social_cost"] if social else 0.0
    per_event = p["event_direct_cost"] + social_cost
    db_events_yr = p["events_per_km_yr"] * per_event
    cst_events_yr = p["events_per_km_yr"] * (1.0 - p["cst_event_reduction"]) * per_event
    cst_om_yr = cst_capex * p["cst_om_frac"]

    cycle = np.maximum(1, np.rint(np.asarray(p["replacement_cycle_yr"], dtype=float))).astype(int)
    years = np.arange(1, horizon + 1)
    hit = (years[None, :] % np.atleast_1d(cycle)[:, None]) == 0
    repl_pv_factor = (hit * df[1:][None, :]).sum(axis=1)
    if np.ndim(cycle) == 0:
        repl_pv_factor = repl_pv_factor[0]

    db_repl = db_capex * p["db_repl_civil_frac"] + (
        p["repl_disruption_events"] * social_cost
    )
    cst_repl = db_capex * p["cst_repl_civil_frac"]

    residual = cst_capex * np.maximum(0.0, 1.0 - horizon / np.asarray(p["cst_life_yr"], dtype=float))

    pv_db = db_capex + db_events_yr * annuity + db_repl * repl_pv_factor
    pv_cst = (
        cst_capex
        + (cst_events_yr + cst_om_yr) * annuity
        + cst_repl * repl_pv_factor
        - residual * df[horizon]
    )
    return {
        "cst_capex": cst_capex,
        "db_capex": db_capex,
        "pv_db": pv_db,
        "pv_cst": pv_cst,
        "npv_cst": pv_db - pv_cst,
        "pv_events_avoided": (db_events_yr - cst_events_yr) * annuity,
        "pv_cst_om": cst_om_yr * annuity,
        "pv_replacement_saving": (db_repl - cst_repl) * repl_pv_factor,
        "pv_residual": residual * df[horizon],
    }


def npv(p: dict, horizon: int, social: bool = True) -> float:
    return float(evaluate(p, horizon, social)["npv_cst"])


def breakeven(p: dict, name: str, horizon: int, lo: float, hi: float,
              social: bool = True, tol: float = 1e-6) -> float | None:
    """Value of input `name` in [lo, hi] at which NPV crosses zero (bisection), or None."""
    def f(x):
        q = dict(p)
        q[name] = x
        return npv(q, horizon, social)

    flo, fhi = f(lo), f(hi)
    if flo == 0:
        return lo
    if np.sign(flo) == np.sign(fhi):
        return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if abs(hi - lo) < tol:
            break
        if np.sign(fm) == np.sign(flo):
            lo, flo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)
