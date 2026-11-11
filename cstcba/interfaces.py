"""Interface (interdependency) matrix for utility systems sharing a CST."""
from __future__ import annotations

from itertools import combinations
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "inputs" / "interfaces.yaml"


def load(path: Path = INPUTS) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def matrix(cfg: dict) -> dict:
    names = list(cfg["systems"])
    m = {a: {b: 0 for b in names} for a in names}
    seen = set()
    for a, b, sev, _ in cfg["pairs"]:
        if a == b or a not in m or b not in m:
            raise ValueError(f"bad pair {a}-{b}")
        key = frozenset((a, b))
        if key in seen:
            raise ValueError(f"duplicate pair {a}-{b}")
        seen.add(key)
        m[a][b] = m[b][a] = int(sev)
    missing = [f"{a}-{b}" for a, b in combinations(names, 2) if frozenset((a, b)) not in seen]
    if missing:
        raise ValueError(f"missing pairs: {missing}")
    return m


def summary(cfg: dict) -> dict:
    m = matrix(cfg)
    load_by_system = {a: sum(row.values()) for a, row in m.items()}
    high = [f"{a}-{b}" for a, b, s, _ in cfg["pairs"] if s == 3]
    return {
        "n_systems": len(m),
        "n_pairs": len(cfg["pairs"]),
        "n_severity_3": len(high),
        "severity_3_pairs": high,
        "interface_load": load_by_system,
        "most_coupled": max(load_by_system, key=load_by_system.get),
    }


def markdown(cfg: dict) -> str:
    m = matrix(cfg)
    names = list(m)
    lines = ["| | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    for a in names:
        cells = ["-" if a == b else str(m[a][b]) for b in names]
        lines.append(f"| **{a}** | " + " | ".join(cells) + " |")
    lines += ["", "| Pair | Severity | Interface risk |", "|---|---|---|"]
    for a, b, s, text in sorted(cfg["pairs"], key=lambda r: -r[2]):
        lines.append(f"| {a} / {b} | {s} | {text} |")
    return "\n".join(lines) + "\n"
