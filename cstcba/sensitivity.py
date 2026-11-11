"""Tornado (one-at-a-time) and Monte Carlo sensitivity on every assumption."""
from __future__ import annotations

import numpy as np

from .costmodel import base_values, evaluate, npv


def swept_params(cfg: dict) -> list[str]:
    return [n for n, s in cfg["params"].items() if s["kind"] == "assumption"]


def tornado(cfg: dict, horizon: int, social: bool = True) -> list[dict]:
    base = base_values(cfg)
    base_npv = npv(base, horizon, social)
    rows = []
    for name in swept_params(cfg):
        spec = cfg["params"][name]
        out = {}
        for end in ("low", "high"):
            q = dict(base)
            q[name] = spec[end]
            out[end] = npv(q, horizon, social)
        flips = bool(np.sign(out["low"]) != np.sign(base_npv) or np.sign(out["high"]) != np.sign(base_npv))
        rows.append({
            "param": name,
            "low_value": spec["low"],
            "high_value": spec["high"],
            "npv_at_low": out["low"],
            "npv_at_high": out["high"],
            "swing": abs(out["high"] - out["low"]),
            "flips_decision": flips,
        })
    rows.sort(key=lambda r: r["swing"], reverse=True)
    return rows


def draw_inputs(cfg: dict, draws: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    p = base_values(cfg)
    for name in swept_params(cfg):
        spec = cfg["params"][name]
        if name == "discount_rate":
            continue
        p[name] = rng.triangular(spec["low"], spec["base"], spec["high"], size=draws)
    return p


def monte_carlo(cfg: dict, horizon: int, social: bool = True, draws: int | None = None,
                seed: int | None = None) -> dict:
    """Independent triangular(low, base, high) draws; discounting stays on the Green Book schedule."""
    mc = cfg["monte_carlo"]
    draws = draws or mc["draws"]
    p = draw_inputs(cfg, draws, mc["seed"] if seed is None else seed)
    v = evaluate(p, horizon, social)["npv_cst"]
    return {
        "draws": draws,
        "p_cst_pays": float((v > 0).mean()),
        "npv_p10": float(np.percentile(v, 10)),
        "npv_p50": float(np.percentile(v, 50)),
        "npv_p90": float(np.percentile(v, 90)),
        "npv_mean": float(v.mean()),
    }
