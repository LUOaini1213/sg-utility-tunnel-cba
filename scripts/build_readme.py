"""Render README.md from docs/README.template.md and results/*.json.

Placeholders:
  {{file.json:dotted.path|fmt}}  fmt: .Nf (fixed), pctN (x100, N decimals), int, list, str
  {{table:name}}                 tables built from results files
Usage: python scripts/build_readme.py [--check]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "docs" / "README.template.md"
README = ROOT / "README.md"
RESULTS = ROOT / "results"
PLACEHOLDER = re.compile(r"\{\{([^}]+)\}\}")


def load_results() -> dict:
    return {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESULTS.glob("*.json"))}


def lookup(data: dict, path: str):
    for part in path.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def fmt_value(v, fmt: str) -> str:
    if fmt == "list":
        return ", ".join(f"`{x}`" for x in v)
    if fmt == "str":
        return str(v)
    if fmt == "int":
        return str(int(round(v)))
    if fmt.startswith("pct"):
        return f"{v * 100:.{int(fmt[3:])}f}%"
    if fmt.startswith("."):
        return format(v, fmt)
    raise ValueError(f"unknown format {fmt}")


def table(name: str, res: dict) -> str:
    cost, sched = res["cost.json"], res["schedule.json"]
    if name.startswith("tornado_"):
        h = name.split("_")[1]
        rows = ["| Assumption | Low | High | NPV at low | NPV at high | Flips decision |",
                "|---|---|---|---|---|---|"]
        for r in cost["tornado"][h]:
            rows.append(f"| `{r['param']}` | {r['low_value']:g} | {r['high_value']:g} | "
                        f"{r['npv_at_low']:.1f} | {r['npv_at_high']:.1f} | {'yes' if r['flips_decision'] else 'no'} |")
        return "\n".join(rows)
    if name == "breakeven_curve":
        rows = ["| Social cost per opening (S$M) | Breakeven openings/km/yr, 50 yr | Breakeven openings/km/yr, 100 yr |",
                "|---|---|---|"]
        for a, b in zip(cost["breakeven_curve"]["h50"], cost["breakeven_curve"]["h100"]):
            rows.append(f"| {a['event_social_cost']:.2f} | {a['events_per_km_yr']:.1f} | {b['events_per_km_yr']:.1f} |")
        return "\n".join(rows)
    if name == "delays":
        rows = ["| Delay scenario | Float before (months) | Ph1 ready slip | Ph2 ready slip |", "|---|---|---|---|"]
        for d in sched["delays"]:
            rows.append(f"| {d['label']} | {d['float_before']:.0f} | {d['m1_slip']:.0f} | {d['m2_slip']:.0f} |")
        return "\n".join(rows)
    raise KeyError(name)


def render(res: dict | None = None) -> str:
    res = res or load_results()
    text = TEMPLATE.read_text(encoding="utf-8")

    def sub(m):
        spec = m.group(1).strip()
        if spec.startswith("table:"):
            return table(spec[6:], res)
        ref, _, fmt = spec.partition("|")
        fname, _, path = ref.partition(":")
        return fmt_value(lookup(res[fname], path), fmt or "str")

    return PLACEHOLDER.sub(sub, text)


def main(argv: list[str]) -> int:
    out = render()
    if "--check" in argv:
        current = README.read_text(encoding="utf-8") if README.exists() else ""
        if current != out:
            print("README.md is stale: run python scripts/build_readme.py")
            return 1
        return 0
    README.write_text(out, encoding="utf-8", newline=chr(10))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
