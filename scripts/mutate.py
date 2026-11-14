"""Plant bugs one at a time and check the test suite catches each one.

Usage: python scripts/mutate.py [--suite cba|corridor] --record first|final
Golden tests (comparison with committed results) are excluded, so a kill must come from a
behavioural test. Results are written to results/mutation.json: the cba suite under
first_run / final, the corridor suite under corridor_first / corridor_final.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "mutation.json"
PYTEST = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-m", "not golden"]

MUTANTS = [
    ("cstcba/discount.py", "df[t - 1] / (1.0 + r)", "df[t - 1] / (1.0 + 2 * r)"),
    ("cstcba/discount.py", "if year <= last_year", "if year < last_year"),
    ("cstcba/discount.py", "for t in range(1, horizon + 1)", "for t in range(2, horizon + 1)"),
    ("cstcba/costmodel.py", "annuity = df[1:].sum()", "annuity = df.sum()"),
    ("cstcba/costmodel.py", 'db_capex = cst_capex * p["db_capex_ratio"]', 'db_capex = cst_capex * (1 - p["db_capex_ratio"])'),
    ("cstcba/costmodel.py", 'if social else 0.0', 'if True else 0.0'),
    ("cstcba/costmodel.py", '(1.0 - p["cst_event_reduction"])', 'p["cst_event_reduction"]'),
    ("cstcba/costmodel.py", 'cst_om_yr = cst_capex * p["cst_om_frac"]', 'cst_om_yr = db_capex * p["cst_om_frac"]'),
    ("cstcba/costmodel.py", "% np.atleast_1d(cycle)[:, None]) == 0", "% np.atleast_1d(cycle)[:, None]) != 0"),
    ("cstcba/costmodel.py", "- residual * df[horizon]", "+ residual * df[horizon]"),
    ("cstcba/costmodel.py", "1.0 - horizon / ", "1.0 - horizon * 0.5 / "),
    ("cstcba/costmodel.py", '"npv_cst": pv_db - pv_cst', '"npv_cst": pv_cst - pv_db'),
    ("cstcba/costmodel.py", 'p["repl_disruption_events"] * social_cost', 'p["repl_disruption_events"] * p["event_direct_cost"]'),
    ("cstcba/costmodel.py", "if np.sign(fm) == np.sign(flo):", "if np.sign(fm) != np.sign(flo):"),
    ("cstcba/costmodel.py", "        return None\n", "        return lo\n"),
    ("cstcba/sensitivity.py", 'r["swing"], reverse=True', 'r["swing"], reverse=False'),
    ("cstcba/sensitivity.py", 'or np.sign(out["high"])', 'and np.sign(out["high"])'),
    ("cstcba/sensitivity.py", "(v > 0).mean()", "(v < 0).mean()"),
    ("cstcba/sensitivity.py", 'spec["low"], spec["base"], spec["high"]', 'spec["low"], spec["low"], spec["high"]'),
    ("cstcba/schedule.py", 'es[a] = max(', 'es[a] = min('),
    ("cstcba/schedule.py", 'lf[a] = min(', 'lf[a] = max('),
    ("cstcba/schedule.py", "abs(tf[a]) < 1e-9", "abs(tf[a]) <= 1.0"),
    ("cstcba/schedule.py", 'd[sc["activity"]] += sc["months"]', 'd[sc["activity"]] = sc["months"]'),
    ("cstcba/schedule.py", "if state.get(a) == 1:", "if state.get(a) == 3:"),
    ("cstcba/interfaces.py", "m[a][b] = m[b][a] = int(sev)", "m[a][b] = int(sev)"),
    ("cstcba/interfaces.py", "    if missing:", "    if False:"),
    ("scripts/build_readme.py", "v * 100:.", "v * 10:."),
    ("scripts/build_readme.py", "if current != out:", "if False:"),
    ("cstcba/run.py", 'for r in out["tornado"]["h100"] if r["flips_decision"]', 'for r in out["tornado"]["h100"] if not r["flips_decision"]'),
    ("cstcba/run.py", 'p.update({k: v for k, v in sc.items() if k != "label"})', 'p.update({})'),
]

C, O, R = "cstcba/corridor.py", "cstcba/corridor_opt.py", "cstcba/corridor_run.py"
CORRIDOR_MUTANTS = [
    # rule lookup
    (C, " or (p in (type_b, ANY) and q in (type_a, ANY))", ""),
    (C, 'if hit and r["value_m"] > best + EPS:', 'if hit and best_id is None:'),
    (C, 'val = float(r["value_m"]) - u["height_m"]', 'val = float(r["value_m"])'),
    (C, 'if r["kind"] == "cover" and r["zone"] in zones:', 'if r["kind"] == "cover" and r["zone"] not in zones:'),
    (C, 'if r["trunk"] not in (trunk_type, ANY):', 'if r["trunk"] != trunk_type:'),
    # geometry
    (C, "return max(a[0], b[0]) - min(a[1], b[1])", "return max(a[0], b[0]) - max(a[1], b[1])"),
    (C, 'if right > geom["kerb_left"] + EPS and left < geom["kerb_right"] - EPS:',
        'if right > geom["kerb_left"] + EPS or left < geom["kerb_right"] - EPS:'),
    # checker
    (C, "if gap < off - EPS:", "if gap < -EPS:"),
    (C, "if rid and top < need - EPS:", "if rid and top < need - 0.5:"),
    (C, 'if "carriageway" in zones and cfg["utilities"][uid]["chambers"] and uid not in grandfathered:',
        'if "sidetable" in zones and cfg["utilities"][uid]["chambers"] and uid not in grandfathered:'),
    (C, "if rid and gap < need - EPS:", "if rid and gap < need / 2 - EPS:"),
    (C, "            if gap < -EPS:", "            if gap < -1.0:"),
    # crossings
    (C, "gap, is_under = top - t_bot, True", "gap, is_under = top - t_top, True"),
    (C, "if under and not is_under:", "if False and not is_under:"),
    (C, "best, gov, gov_obj = t_bot + need, rid, name", "best, gov, gov_obj = t_bot, rid, name"),
    # cost
    (C, 'depth = cover + u["height_m"] + g["bedding_m"]', 'depth = cover + g["bedding_m"]'),
    (C, 'if kind == "carriageway" else c["sidetable_rate_per_m3"]', 'if kind != "carriageway" else c["sidetable_rate_per_m3"]'),
    # optimiser
    (O, '(ui["width_m"] + uj["width_m"]) / 2.0 + c', '(ui["width_m"] + uj["width_m"]) + c'),
    (O, "m.add({iz(i, 1): w[i] + a_min[i] for i in range(n)}, -np.inf, slack + c_w)",
        "m.add({iz(i, 1): w[i] + a_min[i] for i in range(n)}, -np.inf, slack)"),
    (O, "m.add({ix(i): 1, iv: -1, iz(i, 0): big}, -np.inf, big - half)",
        "m.add({ix(i): 1, iv: -1, iz(i, 0): big}, -np.inf, big + half)"),
    (O, "                ub[iy(i, z)] = 0\n            if ban and strict_chambers and i in chambered:\n                ub[iz(i, 1)] = 0",
        "                ub[iy(i, z)] = 0\n            if ban and strict_chambers and i in chambered:\n                ub[iz(i, 1)] = 1"),
    (O, "cost[iy(i, z)] = df * tc", "cost[iy(i, z)] = tc"),
    (O, 'existing[uid]["x"], np.inf)', "-np.inf, np.inf)"),
    (O, "lb[im(i)] = 1 ", "lb[im(i)] = 0 "),
    (O, "m.add({iz(i, 1): 1, im(i): 1}, -np.inf, 1)", "m.add({iz(i, 1): 1, im(i): 1}, -np.inf, 2)"),
    (O, "            cost[iz(i, 1)] = 1.0", "            cost[iz(i, 1)] = 0.0"),
    (O, "abs(co.h_gap(boxes[a], boxes[b]) - need) < TIGHT", "abs(co.h_gap(boxes[a], boxes[b]) - need) > TIGHT"),
    # worked-example bookkeeping
    (R, '"saving_m": mw["reserve_width_m"] - alt["reserve_width_m"]})', '"saving_m": alt["reserve_width_m"] - mw["reserve_width_m"]})'),
    (R, 'floor = sum(co.trench_cost(cfg, u, "left") for u in ids)', 'floor = sum(co.trench_cost(cfg, u, "carriageway") for u in ids)'),
    (R, 'out["extra_cost_of_adding_per_m"] - green', 'out["extra_cost_of_adding_per_m"] + green'),
    (R, "waivers == 0, ", "waivers >= 0, "),
]
SUITES = {"cba": (MUTANTS, ""), "corridor": (CORRIDOR_MUTANTS, "corridor_")}


def run_tests() -> bool:
    return subprocess.run(PYTEST, cwd=ROOT, capture_output=True).returncode == 0


def count_tests() -> int:
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    m = re.search(r"(\d+) tests? collected", out)
    return int(m.group(1)) if m else 0


def main(argv: list[str]) -> int:
    key = argv[argv.index("--record") + 1] if "--record" in argv else "final"
    suite = argv[argv.index("--suite") + 1] if "--suite" in argv else "cba"
    mutants, prefix = SUITES[suite]
    if suite == "cba" and key == "first":
        key = "first_run"
    key = prefix + key
    if not run_tests():
        print("suite fails on unmutated code; aborting")
        return 2
    survivors = []
    for i, (rel, old, new) in enumerate(mutants, 1):
        path = ROOT / rel
        src = path.read_bytes().decode("utf-8")
        if src.count(old) != 1:
            print(f"mutant {i}: pattern not unique in {rel}")
            return 2
        try:
            path.write_bytes(src.replace(old, new).encode("utf-8"))
            killed = not run_tests()
        finally:
            path.write_bytes(src.encode("utf-8"))
        print(f"mutant {i:2d} {'killed ' if killed else 'SURVIVED'} {rel}: {new.strip()[:60]}")
        if not killed:
            survivors.append({"id": i, "file": rel, "mutation": new.strip()})
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    if suite == "cba":
        data["n_mutants"] = len(mutants)
    data["tests_collected"] = count_tests()
    data[key] = {"total": len(mutants), "killed": len(mutants) - len(survivors), "survivors": survivors}
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline=chr(10))
    print(f"{key}: killed {len(mutants) - len(survivors)} / {len(mutants)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
