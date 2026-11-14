"""Corridor worked examples: results dictionary, rules table (markdown) and cross-section drawings."""
from __future__ import annotations

import copy

from . import corridor as co
from . import corridor_draw as draw
from . import corridor_opt as op

RELAX_KINDS = ("parallel", "drain_offset", "chamber_ban")


def _items(items):
    return [{"id": it["id"], "x_m": it["x"], "cover_m": it["cover"], "zone": it.get("zone")} for it in items]


def _raw(items):
    return [{"id": it["id"], "x": it["x_m"], "cover": it["cover_m"], "zone": it.get("zone")} for it in items]


def _tight(sol):
    return [{"rule": b["rule"], "items": b["items"], "clearance_m": b["clearance_m"]} for b in sol["binding"]]


def example(cfg: dict, name: str) -> dict:
    res = cfg["reserves"][name]
    ids = list(res["utilities"])
    given = co.geometry(cfg, name)
    out = {"label": res["label"], "reserve_width_m": given["width"], "carriageway_m": given["carriageway"],
           "verge_m": given["verge"], "n_utilities": len(ids)}

    # 1. smallest reserve that takes every utility with every rule met
    mw = op.solve(cfg, name, ids, "width")
    out["min_width"] = {"verge_m": mw["verge_m"], "reserve_width_m": mw["reserve_width_m"],
                        "spare_reserve_m": given["width"] - mw["reserve_width_m"],
                        "fits": bool(mw["reserve_width_m"] <= given["width"] + 1e-6),
                        "items": _items(mw["items"]), "tight": _tight(mw)}

    # 2. which rules bind: reserve width saved if one rule is switched off
    relax = []
    for r in cfg["rules"]:
        if r["kind"] not in RELAX_KINDS:
            continue
        alt = op.solve(cfg, name, ids, "width", disabled=(r["id"],))
        relax.append({"rule": r["id"], "status": r["status"], "reserve_width_m": alt["reserve_width_m"],
                      "saving_m": mw["reserve_width_m"] - alt["reserve_width_m"]})
    relax.sort(key=lambda d: (-round(d["saving_m"], 6), d["rule"]))
    out["relaxation"] = relax
    out["binding_rules"] = [d["rule"] for d in relax if d["saving_m"] > 1e-6]

    # 3. sensitivity to the assumed water-main parallel clearance
    alt_cfg = copy.deepcopy(cfg)
    co.rule(alt_cfg, "PUB-WATER-PARALLEL")["value_m"] = cfg["sensitivity"]["water_parallel_m"]
    alt = op.solve(alt_cfg, name, ids, "width")
    out["water_sensitivity"] = {"clearance_m": cfg["sensitivity"]["water_parallel_m"],
                                "reserve_width_m": alt["reserve_width_m"],
                                "saving_m": mw["reserve_width_m"] - alt["reserve_width_m"]}

    # 4. cheapest compliant layout in the reserve as given
    floor = sum(co.trench_cost(cfg, u, "left") for u in ids)
    try:
        sol = op.solve(cfg, name, ids, "cost")
        waivers = 0
    except op.Infeasible:
        waivers = int(round(op.solve(cfg, name, ids, "waivers", strict_chambers=False)["objective"]))
        sol = op.solve(cfg, name, ids, "cost", strict_chambers=False, max_waivers=waivers)
    cost = op.total_cost(cfg, sol["items"])
    out["as_given"] = {"feasible_without_waiver": waivers == 0, "waivers_needed": waivers, "waived": sol["waived"],
                       "n_under_carriageway": sum(it["zone"] == "carriageway" for it in sol["items"]),
                       "under_carriageway": [it["id"] for it in sol["items"] if it["zone"] == "carriageway"],
                       "cost_per_m": cost, "cost_floor_per_m": floor, "premium_per_m": cost - floor,
                       "items": _items(sol["items"]), "tight": _tight(sol)}

    # 5. a lateral connection passing under the whole corridor
    out["crossing"] = co.min_undercross_depth(cfg, given, sol["items"], 0.0, given["width"])
    return out


def brownfield(cfg: dict) -> dict:
    bf = cfg["brownfield"]
    name = bf["reserve"]
    geom = co.geometry(cfg, name)
    as_built = [{"id": it["id"], "x": float(it["x_m"]), "cover": float(it["cover_m"])} for it in bf["as_built"]]
    for it in as_built:
        it["zone"] = co.zone_name(geom, *co.outline(cfg, it)[:2])
    ids = [it["id"] for it in as_built]
    existing = {it["id"]: {"x": it["x"], "cover": it["cover"]} for it in as_built}
    viol = co.check_layout(cfg, geom, as_built, grandfathered=ids)
    out = {"reserve": name, "n_existing": len(ids), "new": list(bf["new"]),
           "as_built": {"items": _items(as_built), "violations": viol, "summary": co.summarise(viol),
                        "in_conflict": sorted({u for v in viol for u in v["items"] if u in ids})}}
    for key, extra in (("cure_only", []), ("cure_and_add", list(bf["new"]))):
        sol = op.solve(cfg, name, ids + extra, "cost", existing=existing)
        new_cost = sum(co.trench_cost(cfg, it["id"], it["zone"], it["cover"]) for it in sol["items"]
                       if it["id"] in extra)
        out[key] = {"cost_per_m": sol["objective"], "diverted": sorted(sol["moved"]), "n_diverted": len(sol["moved"]),
                    "new_utility_cost_per_m": new_cost, "diversion_cost_per_m": sol["objective"] - new_cost,
                    "items": _items(sol["items"]), "tight": _tight(sol),
                    "new_zone": {it["id"]: it["zone"] for it in sol["items"] if it["id"] in extra}}
    out["extra_cost_of_adding_per_m"] = out["cure_and_add"]["cost_per_m"] - out["cure_only"]["cost_per_m"]
    green = sum(co.trench_cost(cfg, u, "left") for u in bf["new"])
    out["new_utility_greenfield_cost_per_m"] = green
    out["congestion_premium_per_m"] = out["extra_cost_of_adding_per_m"] - green
    df = cfg["costs"]["diversion_factor"]
    out["diversion_unit_costs"] = [
        {"id": u, "sidetable_per_m": df * co.trench_cost(cfg, u, "left"),
         "carriageway_per_m": df * co.trench_cost(cfg, u, "carriageway")} for u in ids]
    return out


def results(cfg: dict) -> dict:
    rules = cfg["rules"]
    out = {
        "rules": {"n_total": len(rules),
                  "n_sourced": sum(r["status"] == "sourced" for r in rules),
                  "n_assumption": sum(r["status"] == "assumption" for r in rules),
                  "n_sources": len(cfg["sources"]),
                  "table": [{"id": r["id"], "agency": r["agency"], "kind": r["kind"], "status": r["status"],
                             "value_m": r.get("value_m")} for r in rules]},
        "geometry": dict(cfg["geometry"]),
        "costs": dict(cfg["costs"]),
        "examples": {name: example(cfg, name) for name in cfg["reserves"]},
        "brownfield": brownfield(cfg),
    }
    return out


def rules_markdown(cfg: dict) -> str:
    lines = ["# Utility corridor clearance rules", "",
             "Generated by `python -m cstcba.run` from `inputs/corridor.yaml`. Personal desk study on public",
             "documents; not a URA/agency study and not a design standard. Only single figures are cited; no text",
             "or tables are reproduced. `sourced` = figure read from the cited document and clause on 2026-11-14;",
             "`assumption` = no public figure found, value is the author's.", "",
             "| Rule | Agency | Value (m) | Status | Source and clause | How it is applied |", "|---|---|---|---|---|---|"]
    for r in cfg["rules"]:
        val = "-" if r.get("value_m") is None else f"{r['value_m']:g}"
        src = (f"{r['source']} " if r.get("source") else "") + r["clause"]
        text = r["text"] + (f" *{r['interpretation']}*" if r.get("interpretation") else "")
        lines.append(f"| `{r['id']}` | {r['agency']} | {val} | **{r['status']}** | {src} | {text} |")
    lines += ["", "## Sources", ""]
    for sid, s in cfg["sources"].items():
        lines.append(f"- **{sid}** {s['title']}. <{s['url']}>")
    lines += ["", "Everything under `geometry`, `costs`, `utilities` (outer sizes, which utilities need chambers) and",
              "`reserves` in `inputs/corridor.yaml` is a scenario assumption. What was looked for and not found is",
              "listed in [sources.md](sources.md).", ""]
    return "\n".join(lines)


def drawings(cfg: dict, res: dict) -> dict[str, str]:
    """{file name: svg text} for docs/img/."""
    out = {}
    for name, ex in res["examples"].items():
        geom = co.geometry(cfg, name)
        waived = set(ex["as_given"]["waived"])
        note = "Red outline: chambered utility under the carriageway (LTA waiver needed)." if waived else ""
        out[f"corridor_{name}.svg"] = draw.svg(
            cfg, geom, _raw(ex["as_given"]["items"]),
            f"{ex['label']}: cheapest compliant layout in a {geom['width']:.1f} m reserve",
            tight=ex["as_given"]["tight"], flagged=waived, note=note)
    bf = res["brownfield"]
    geom = co.geometry(cfg, bf["reserve"])
    out["corridor_asbuilt.svg"] = draw.svg(
        cfg, geom, _raw(bf["as_built"]["items"]), "Brownfield case: invented as-built corridor with conflicts",
        flagged=set(bf["as_built"]["in_conflict"]), note="Red outline: utility in at least one conflict.")
    out["corridor_diverted.svg"] = draw.svg(
        cfg, geom, _raw(bf["cure_and_add"]["items"]),
        "Brownfield case: cheapest diversion that cures the conflicts and adds the new main",
        tight=bf["cure_and_add"]["tight"], flagged=set(bf["cure_and_add"]["diverted"]) | set(bf["new"]),
        note="Red outline: diverted or new utility.")
    return out
