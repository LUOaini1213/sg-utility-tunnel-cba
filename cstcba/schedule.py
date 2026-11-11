"""Critical path method (CPM) with delay scenarios and Monte Carlo duration risk."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "inputs" / "schedule.yaml"


def load(path: Path = INPUTS) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def topo_order(acts: dict) -> list[str]:
    order, state = [], {}

    def visit(a):
        if state.get(a) == 1:
            raise ValueError(f"cycle at {a}")
        if state.get(a) == 2:
            return
        state[a] = 1
        for pred in acts[a]["after"]:
            if pred not in acts:
                raise KeyError(f"{a} depends on unknown {pred}")
            visit(pred)
        state[a] = 2
        order.append(a)

    for a in acts:
        visit(a)
    return order


def cpm(acts: dict, durations: dict) -> dict:
    """Forward/backward pass. Returns early/late start/finish, float and the critical path."""
    order = topo_order(acts)
    es, ef = {}, {}
    for a in order:
        es[a] = max((ef[p] for p in acts[a]["after"]), default=0.0)
        ef[a] = es[a] + durations[a]
    finish = max(ef.values())
    succ = {a: [] for a in acts}
    for a in acts:
        for p in acts[a]["after"]:
            succ[p].append(a)
    lf, ls = {}, {}
    for a in reversed(order):
        lf[a] = min((ls[s] for s in succ[a]), default=finish)
        ls[a] = lf[a] - durations[a]
    tf = {a: ls[a] - es[a] for a in acts}
    critical = [a for a in order if abs(tf[a]) < 1e-9]
    return {"es": es, "ef": ef, "ls": ls, "lf": lf, "float": tf,
            "finish": finish, "critical": critical}


def base_durations(acts: dict) -> dict:
    return {a: float(v["dur"][1]) for a, v in acts.items()}


def delay_impacts(cfg: dict) -> list[dict]:
    acts = cfg["activities"]
    base = cpm(acts, base_durations(acts))
    out = []
    for sc in cfg["delay_scenarios"]:
        d = base_durations(acts)
        d[sc["activity"]] += sc["months"]
        r = cpm(acts, d)
        out.append({
            "label": sc["label"],
            "activity": sc["activity"],
            "delay_months": sc["months"],
            "float_before": base["float"][sc["activity"]],
            "m1_finish": r["ef"]["M1"],
            "m2_finish": r["ef"]["M2"],
            "m1_slip": r["ef"]["M1"] - base["ef"]["M1"],
            "m2_slip": r["ef"]["M2"] - base["ef"]["M2"],
            "critical_after": r["critical"],
        })
    return out


def monte_carlo(cfg: dict, draws: int | None = None) -> dict:
    acts = cfg["activities"]
    mc = cfg["monte_carlo"]
    draws = draws or mc["draws"]
    rng = np.random.default_rng(mc["seed"])
    target = mc["target"]
    finishes = np.empty(draws)
    crit_count = {a: 0 for a in acts}
    for i in range(draws):
        d = {}
        for a, v in acts.items():
            lo, mode, hi = v["dur"]
            d[a] = float(rng.triangular(lo, mode, hi)) if hi > lo else float(mode)
        r = cpm(acts, d)
        finishes[i] = r["ef"][target]
        for a in r["critical"]:
            crit_count[a] += 1
    return {
        "target": target,
        "draws": draws,
        "p50": float(np.percentile(finishes, 50)),
        "p80": float(np.percentile(finishes, 80)),
        "p90": float(np.percentile(finishes, 90)),
        "criticality": {a: crit_count[a] / draws for a in acts},
    }
