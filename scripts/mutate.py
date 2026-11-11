"""Plant bugs one at a time and check the test suite catches each one.

Usage: python scripts/mutate.py --record first|final
Golden tests (comparison with committed results) are excluded, so a kill must come from a
behavioural test. Results are written to results/mutation.json under the given key.
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


def run_tests() -> bool:
    return subprocess.run(PYTEST, cwd=ROOT, capture_output=True).returncode == 0


def count_tests() -> int:
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    m = re.search(r"(\d+) tests? collected", out)
    return int(m.group(1)) if m else 0


def main(argv: list[str]) -> int:
    key = argv[argv.index("--record") + 1] if "--record" in argv else "final"
    if not run_tests():
        print("suite fails on unmutated code; aborting")
        return 2
    survivors = []
    for i, (rel, old, new) in enumerate(MUTANTS, 1):
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
    data["n_mutants"] = len(MUTANTS)
    data["tests_collected"] = count_tests()
    data[key] = {"total": len(MUTANTS), "killed": len(MUTANTS) - len(survivors), "survivors": survivors}
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline=chr(10))
    print(f"{key}: killed {len(MUTANTS) - len(survivors)} / {len(MUTANTS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
