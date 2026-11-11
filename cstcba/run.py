"""Run every analysis and write results/*.json (the only source of README numbers)."""
from __future__ import annotations

import json
from pathlib import Path

from . import costmodel, discount, interfaces, schedule, sensitivity

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

BREAKEVEN_RANGES = {
    "events_per_km_yr": (0.0, 60.0),
    "event_social_cost": (0.0, 20.0),
    "db_capex_ratio": (0.0, 1.0),
    "scale_factor": (0.05, 3.0),
    "discount_rate": (0.0001, 0.25),
}


LF = chr(10)
SOCIAL_COST_GRID =[0.0, 0.1, 0.2, 0.4, 0.8]


def _round(x):
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_round(v) for v in x]
    return x


def cost_results(cfg: dict) -> dict:
    base = costmodel.base_values(cfg)
    out = {"base": {}, "financial_only": {}, "scenarios": {}, "breakeven": {},
           "tornado": {}, "monte_carlo": {}, "inputs": base}
    for h in cfg["horizons"]:
        key = f"h{h}"
        out["base"][key] = {k: float(v) for k, v in costmodel.evaluate(base, h).items()}
        out["financial_only"][key] = {k: float(v) for k, v in costmodel.evaluate(base, h, social=False).items()}
        out["breakeven"][key] = {
            name: costmodel.breakeven(base, name, h, lo, hi) for name, (lo, hi) in BREAKEVEN_RANGES.items()
        }
        out["breakeven"][key]["events_per_km_yr_financial_only"] = costmodel.breakeven(
            base, "events_per_km_yr", h, *BREAKEVEN_RANGES["events_per_km_yr"], social=False)
        out["tornado"][key] = sensitivity.tornado(cfg, h)
        out["monte_carlo"][key] = sensitivity.monte_carlo(cfg, h)
        out["monte_carlo"][f"{key}_financial_only"] = sensitivity.monte_carlo(cfg, h, social=False)
        for sname, sc in cfg["scenarios"].items():
            p = dict(base)
            p.update({k: v for k, v in sc.items() if k != "label"})
            out["scenarios"].setdefault(sname, {"label": sc["label"]})[key] = costmodel.npv(p, h)
        out["breakeven_curve"] = out.get("breakeven_curve", {})
        out["breakeven_curve"][key] = [
            {"event_social_cost": sc, "events_per_km_yr": costmodel.breakeven(
                dict(base, event_social_cost=sc), "events_per_km_yr", h, *BREAKEVEN_RANGES["events_per_km_yr"])}
            for sc in SOCIAL_COST_GRID
        ]
    out["horizons"] = cfg["horizons"]
    sched = discount.GREEN_BOOK_2026
    out["discount_schedule"] = {"edition": 2026, "bands": [
        {"from_year": (sched[i - 1][0] + 1 if i else 1), "rate": r} for i, (_, r) in enumerate(sched)]}
    out["flip_params_h100"] = [r["param"] for r in out["tornado"]["h100"] if r["flips_decision"]]
    out["flip_params_h50"] = [r["param"] for r in out["tornado"]["h50"] if r["flips_decision"]]
    return out


def schedule_results(cfg: dict) -> dict:
    acts = cfg["activities"]
    base = schedule.cpm(acts, schedule.base_durations(acts))
    return {
        "base": {"finish": base["finish"], "m1": base["ef"]["M1"], "m2": base["ef"]["M2"],
                 "critical_path": base["critical"], "float": base["float"]},
        "delays": schedule.delay_impacts(cfg),
        "monte_carlo": schedule.monte_carlo(cfg),
    }


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    cost = cost_results(costmodel.load_inputs())
    sched = schedule_results(schedule.load())
    icfg = interfaces.load()
    files = {
        "cost.json": cost,
        "schedule.json": sched,
        "interfaces.json": interfaces.summary(icfg),
    }
    for name, data in files.items():
        (RESULTS / name).write_text(json.dumps(_round(data), indent=2) + "\n", encoding="utf-8", newline=LF)
    (RESULTS / "interfaces.md").write_text(interfaces.markdown(icfg), encoding="utf-8", newline=LF)


if __name__ == "__main__":
    main()
