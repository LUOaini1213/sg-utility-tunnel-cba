"""Draw a corridor cross-section as a plain SVG string (no plotting library, deterministic output)."""
from __future__ import annotations

from . import corridor as co

SX, SY = 46.0, 70.0            # pixels per metre across / down
PAD_L, PAD_T, PAD_B = 30.0, 150.0, 130.0
COLOURS = {"water": "#2f7ed8", "sewer": "#8a5a2b", "gas": "#e6b800", "power": "#d62728",
           "telecom": "#2ca02c", "dcs": "#17a2b8"}
ROUND = {"water", "sewer", "gas"}
FONT = 'font-family="Arial, Helvetica, sans-serif"'


def _f(v: float) -> str:
    return f"{v:.1f}"


def svg(cfg: dict, geom: dict, items: list[dict], title: str, tight: list[dict] | None = None,
        flagged: set[str] | None = None, note: str = "") -> str:
    """items: [{id, x, cover}]; tight: pair clearances drawn in red; flagged: ids outlined in red."""
    flagged = flagged or set()
    tight_pairs = {tuple(sorted(t["items"])) for t in (tight or [])}
    depth = max([co.outline(cfg, it)[3] for it in items] + [geom["drain_invert_depth"]]) + 0.6
    width_px = PAD_L * 2 + geom["width"] * SX
    height_px = PAD_T + depth * SY + PAD_B
    X = lambda x: PAD_L + x * SX
    Y = lambda d: PAD_T + d * SY
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_f(width_px)} {_f(height_px)}" '
           f'width="{_f(width_px)}" height="{_f(height_px)}" {FONT}>',
           f'<rect width="{_f(width_px)}" height="{_f(height_px)}" fill="#ffffff"/>',
           f'<text x="{_f(PAD_L)}" y="22" font-size="15" font-weight="bold" fill="#222222">{title}</text>',
           f'<text x="{_f(PAD_L)}" y="40" font-size="11" fill="#555555">Illustrative cross-section, personal desk '
           f'study. Not an agency drawing. Dimensions in metres. {note}</text>']
    # ground and zones
    out.append(f'<rect x="{_f(X(0))}" y="{_f(Y(0))}" width="{_f(geom["width"] * SX)}" height="{_f(depth * SY)}" '
               f'fill="#f3ead9"/>')
    out.append(f'<rect x="{_f(X(geom["kerb_left"]))}" y="{_f(Y(0) - 7)}" width="{_f(geom["carriageway"] * SX)}" '
               f'height="7" fill="#555555"/>')
    for a, b in ((0.0, geom["kerb_left"]), (geom["kerb_right"], geom["width"])):
        out.append(f'<rect x="{_f(X(a))}" y="{_f(Y(0) - 4)}" width="{_f((b - a) * SX)}" height="4" fill="#9bbf7f"/>')
    for d0, d1 in geom["drains"]:
        out.append(f'<rect x="{_f(X(d0))}" y="{_f(Y(0) - 4)}" width="{_f((d1 - d0) * SX)}" '
                   f'height="{_f(geom["drain_invert_depth"] * SY + 4)}" fill="#cfe3f5" stroke="#5b7c99"/>')
        out.append(f'<text x="{_f(X((d0 + d1) / 2))}" y="{_f(Y(geom["drain_invert_depth"] / 2))}" font-size="10" '
                   f'text-anchor="middle" fill="#34536e">drain</text>')
    for x in (geom["kerb_left"], geom["kerb_right"]):
        out.append(f'<line x1="{_f(X(x))}" y1="{_f(Y(0) - 12)}" x2="{_f(X(x))}" y2="{_f(Y(depth))}" '
                   f'stroke="#999999" stroke-dasharray="4 4"/>')
    # top dimension line
    yd = PAD_T - 38
    marks = [0.0, geom["kerb_left"], geom["kerb_right"], geom["width"]]
    names = ["sidetable", "carriageway", "sidetable"]
    out.append(f'<line x1="{_f(X(0))}" y1="{_f(yd)}" x2="{_f(X(geom["width"]))}" y2="{_f(yd)}" stroke="#333333"/>')
    for mx in marks:
        out.append(f'<line x1="{_f(X(mx))}" y1="{_f(yd - 5)}" x2="{_f(X(mx))}" y2="{_f(yd + 5)}" stroke="#333333"/>')
    for (a, b), nm in zip(zip(marks, marks[1:]), names):
        out.append(f'<text x="{_f(X((a + b) / 2))}" y="{_f(yd - 8)}" font-size="11" text-anchor="middle" '
                   f'fill="#333333">{nm} {b - a:.2f}</text>')
    out.append(f'<text x="{_f(X(geom["width"]))}" y="{_f(yd - 26)}" font-size="11" text-anchor="end" '
               f'fill="#333333">road reserve {geom["width"]:.2f}</text>')
    # utilities
    ordered = sorted(items, key=lambda it: it["x"])
    for k, it in enumerate(ordered):
        u = cfg["utilities"][it["id"]]
        lo, hi, top, bot = co.outline(cfg, it)
        col = COLOURS[u["type"]]
        stroke = "#cc0000" if it["id"] in flagged else "#222222"
        sw = "2.5" if it["id"] in flagged else "1"
        if u["type"] in ROUND:
            out.append(f'<ellipse cx="{_f(X(it["x"]))}" cy="{_f(Y((top + bot) / 2))}" rx="{_f((hi - lo) / 2 * SX)}" '
                       f'ry="{_f((bot - top) / 2 * SY)}" fill="{col}" stroke="{stroke}" stroke-width="{sw}"/>')
        else:
            out.append(f'<rect x="{_f(X(lo))}" y="{_f(Y(top))}" width="{_f((hi - lo) * SX)}" '
                       f'height="{_f((bot - top) * SY)}" fill="{col}" stroke="{stroke}" stroke-width="{sw}"/>')
        out.append(f'<line x1="{_f(X(it["x"]))}" y1="{_f(Y(0))}" x2="{_f(X(it["x"]))}" y2="{_f(Y(top))}" '
                   f'stroke="#777777" stroke-width="0.7"/>')
        ly = Y(depth) + 16 + (k % 3) * 25
        out.append(f'<line x1="{_f(X(it["x"]))}" y1="{_f(Y(bot))}" x2="{_f(X(it["x"]))}" y2="{_f(ly - 10)}" '
                   f'stroke="#999999" stroke-width="0.6" stroke-dasharray="2 2"/>')
        out.append(f'<text x="{_f(X(it["x"]))}" y="{_f(ly)}" font-size="10" text-anchor="middle" '
                   f'fill="#222222">{it["id"]}</text>')
        out.append(f'<text x="{_f(X(it["x"]))}" y="{_f(ly + 11)}" font-size="9" text-anchor="middle" '
                   f'fill="#555555">cover {it["cover"]:.2f}</text>')
    # gaps between neighbours
    shown = 0
    for a, b in zip(ordered, ordered[1:]):
        ba, bb = co.outline(cfg, a), co.outline(cfg, b)
        gap = co.h_gap(ba, bb)
        need, _ = co.pair_clearance(cfg, cfg["utilities"][a["id"]]["type"], cfg["utilities"][b["id"]]["type"])
        if gap > 3.0:
            continue
        yg = Y(0) + 20 + (shown % 2) * 22
        shown += 1
        bad = gap < need - co.EPS
        is_tight = tuple(sorted((a["id"], b["id"]))) in tight_pairs
        col = "#cc0000" if (bad or is_tight) else "#444444"
        x0, x1 = (ba[1], bb[0]) if gap >= 0 else (bb[0], ba[1])
        out.append(f'<line x1="{_f(X(x0))}" y1="{_f(yg)}" x2="{_f(X(x1))}" y2="{_f(yg)}" stroke="{col}" '
                   f'stroke-width="{"2" if (bad or is_tight) else "1"}"/>')
        label = f"{gap:.2f}" + (f" (need {need:.2f})" if bad else "")
        out.append(f'<text x="{_f(X((ba[1] + bb[0]) / 2))}" y="{_f(yg - 5)}" font-size="9" text-anchor="middle" '
                   f'fill="{col}">{label}</text>')
    # legend
    lx, ly = PAD_L, height_px - 14
    for typ in ("water", "sewer", "gas", "power", "telecom", "dcs"):
        out.append(f'<rect x="{_f(lx)}" y="{_f(ly - 9)}" width="12" height="10" fill="{COLOURS[typ]}" stroke="#222222"/>')
        out.append(f'<text x="{_f(lx + 16)}" y="{_f(ly)}" font-size="10" fill="#222222">{typ}</text>')
        lx += 78
    out.append(f'<text x="{_f(lx + 10)}" y="{_f(ly)}" font-size="10" fill="#cc0000">red: clearance at its minimum, '
               f'or a conflict</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"
