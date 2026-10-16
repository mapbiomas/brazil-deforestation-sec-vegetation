# -*- coding: utf-8 -*-
"""
Builds the method figure of the Collection 11 deforestation and secondary vegetation pipeline,
in a light and a dark version for the GitHub README.

The rules and the class aggregation are read from the pipeline source (AST, no Earth Engine),
and the example pixel is run through the same rules, so the figure cannot drift from the code.

Usage (from collection11/):
    python docs/figures/build_method_figure.py            # writes HTML and renders the PNGs
    python docs/figures/build_method_figure.py --html-only

Rendering needs Google Chrome (or Chromium) on the PATH; set CHROME to override.
"""

import argparse
import ast
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PIPELINE_SRC = os.path.join(ROOT, "mapbiomas_brazil_deforestation_secondary_vegetation.py")

YEARS = list(range(1985, 2026))
WIDTH = 1600

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

# Transition classes (0-7): the palette of the Collection 9 scripts in this repository.
# Data colors do not change with the theme.
TRANSITION = {
    0: ("#ffffff", "No data"),
    1: ("#faf5d1", "Anthropic"),
    2: ("#3f7849", "Primary vegetation"),
    3: ("#5bcf20", "Secondary vegetation"),
    4: ("#ea1c1c", "Primary vegetation suppression"),
    5: ("#b4f792", "Recovery to secondary vegetation"),
    6: ("#fe9934", "Secondary vegetation suppression"),
    7: ("#303149", "Other transitions"),
}

# Land cover classes used in the illustrations: official Collection 11 legend colors.
LULC = {
    3: ("#1f8d49", "Forest Formation"),
    4: ("#7dc975", "Savanna Formation"),
    12: ("#d6bc74", "Grassland"),
    15: ("#edde8e", "Pasture"),
    39: ("#f5b3c8", "Soybean"),
    41: ("#f54ca9", "Other Temporary Crops"),
    21: ("#ffefc3", "Mosaic of Uses"),
    24: ("#d4271e", "Urban Area"),
    33: ("#2532e4", "River, Lake and Ocean"),
    11: ("#519799", "Wetland"),
}

THEMES = {
    "light": {
        "bg": "#ffffff", "surface": "#f6f8fa", "card": "#ffffff", "border": "#d8dee4",
        "line": "#c6ced6", "text": "#1f2328", "muted": "#59636e", "faint": "#818b98",
        "accent": "#43798a", "accent_soft": "#e7f2f5", "accent_line": "#9cc9d6",
        "shadow": "0 10px 28px -16px rgba(16,40,50,.30)", "cell_stroke": "rgba(31,35,40,.18)",
        "warm": "rgba(31,35,40,.06)",
    },
    "dark": {
        "bg": "#0d1117", "surface": "#141a22", "card": "#171e27", "border": "#2c343e",
        "line": "#3a444f", "text": "#e6edf3", "muted": "#9aa4af", "faint": "#6e7781",
        "accent": "#75c7e0", "accent_soft": "#15292f", "accent_line": "#2c515d",
        "shadow": "0 10px 28px -16px rgba(0,0,0,.8)", "cell_stroke": "rgba(255,255,255,.16)",
        "warm": "rgba(255,255,255,.05)",
    },
}

# ---------------------------------------------------------------------------
# Rules and lookup from the pipeline source
# ---------------------------------------------------------------------------


def load_constants():
    tree = ast.parse(open(PIPELINE_SRC, encoding="utf-8").read())
    scalars, values = {}, {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)):
            continue
        name = node.targets[0].id
        if isinstance(node.value, ast.Constant):
            scalars[name] = node.value.value
        if name.startswith("RULES_"):
            values[name] = ast.literal_eval(node.value)
        if name == "CLASS_LOOKUP":
            values[name] = [(p.elts[0].value, p.elts[1].id) for p in node.value.elts]
    lookup = {k: scalars[v] for k, v in values.pop("CLASS_LOOKUP")}
    return values, lookup, scalars


RULES, LOOKUP, SCALARS = load_constants()


def apply_kernel(series, rule, years):
    bef, aft, min_start = rule
    k = len(bef)
    s = dict(series)
    for i in range(0, len(years) - k + 1):
        if i < min_start:
            continue
        window = years[i:i + k]
        if [s[y] for y in window] == bef:
            for y, v in zip(window, aft):
                s[y] = v
    return s


def apply_set(series, name, years):
    for rule in RULES[name]:
        series = apply_kernel(series, rule, years)
    return series


def run_pixel(aggregated):
    """Single-pixel version of export_deforestation(), with the cumulative frequency of GEE."""
    s = apply_set(aggregated, "RULES_KERNEL3_VEG_BLIP", YEARS)
    blip = dict(s)
    s = apply_set(s, "RULES_KERNEL6_SECONDARY_END", YEARS[-6:])
    s = apply_set(s, "RULES_KERNEL4_SECONDARY_END_REVERT", YEARS[-4:])
    s = apply_set(s, "RULES_KERNEL4", YEARS)
    s = apply_set(s, "RULES_KERNEL4_SECONDARY", YEARS)
    s = apply_set(s, "RULES_KERNEL3_SECONDARY", YEARS)
    s = apply_set(s, "RULES_KERNEL4_END", YEARS[-4:])
    freq = 0
    for y in YEARS:
        freq += aggregated[y] == 1
        if freq > 1 and s[y] == 4:
            s[y] = 6
        if freq > 0 and s[y] == 2:
            s[y] = 3
    a, b, c = YEARS[-3:]
    if s[a] == 1 and s[b] == 3:
        s[b] = 1
    if s[b] == 1 and s[c] == 3:
        s[c] = 1
    return blip, s


def example_pixel():
    raw = {}
    for y in YEARS:
        if y <= 1994:
            raw[y] = 3
        elif y <= 2002:
            raw[y] = 15
        elif y <= 2010:
            raw[y] = 3
        elif y <= 2018:
            raw[y] = 39
        elif y <= 2022:
            raw[y] = 15
        else:
            raw[y] = 3
    raw[1998] = 3  # one-year vegetation blip inside the pasture period
    agg = {y: LOOKUP[raw[y]] for y in YEARS}
    blip, final = run_pixel(agg)
    return raw, agg, blip, final


RAW, AGG, BLIP, FINAL = example_pixel()

# Expected outcome of the example, checked so that an edit to the rules that changes the story
# fails here instead of silently drawing a different figure.
EXPECTED_EVENTS = {1995: 4, 1998: 1, 2003: 5, 2004: 3, 2011: 6, 2023: 5, 2024: 3, 2025: 3}
for _y, _v in EXPECTED_EVENTS.items():
    assert FINAL[_y] == _v, f"example pixel changed at {_y}: {FINAL[_y]} != {_v}"

# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------


def esc(s):
    return html.escape(str(s), quote=True)


def cells(values, size, gap=2, radius=3, label=False, x0=0, y0=0, highlight=None):
    """A row of colored cells. values: list of (color, text or None)."""
    out = []
    for i, (color, text) in enumerate(values):
        x = x0 + i * (size + gap)
        out.append(
            f'<rect x="{x}" y="{y0}" width="{size}" height="{size}" rx="{radius}" '
            f'fill="{color}" stroke="var(--cell-stroke)" stroke-width="1"/>'
        )
        if label and text is not None:
            fg = "#ffffff" if color in ("#3f7849", "#303149", "#ea1c1c", "#1f8d49", "#d4271e", "#2532e4") else "#1f2328"
            out.append(
                f'<text x="{x + size / 2}" y="{y0 + size / 2 + size * 0.17}" text-anchor="middle" '
                f'font-size="{size * 0.5:.1f}" font-weight="700" fill="{fg}">{esc(text)}</text>'
            )
    return "".join(out)


def rule_chip(before, after, size=22):
    gap = 3
    w = len(before) * (size + gap) - gap
    arrow_w = 30
    total = w * 2 + arrow_w
    svg = [f'<svg width="{total + 4}" height="{size + 4}" viewBox="-2 -2 {total + 4} {size + 4}" class="chip">']
    svg.append(cells([(TRANSITION[v][0], v) for v in before], size, gap, 4, True))
    ax = w + 6
    svg.append(
        f'<path d="M{ax} {size / 2} H{ax + arrow_w - 14}" stroke="var(--faint)" stroke-width="2" '
        f'stroke-linecap="round"/><path d="M{ax + arrow_w - 16} {size / 2 - 5} L{ax + arrow_w - 10} '
        f'{size / 2} L{ax + arrow_w - 16} {size / 2 + 5}" fill="none" stroke="var(--faint)" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    changed = [(TRANSITION[v][0], v) for v in after]
    svg.append(cells(changed, size, gap, 4, True, x0=w + arrow_w))
    for i, (b, a) in enumerate(zip(before, after)):
        if b != a:
            x = w + arrow_w + i * (size + gap)
            svg.append(
                f'<rect x="{x - 1.5}" y="-1.5" width="{size + 3}" height="{size + 3}" rx="5" fill="none" '
                f'stroke="var(--accent)" stroke-width="2"/>'
            )
    svg.append("</svg>")
    return "".join(svg)


def grid(matrix, palette, size, gap=2, radius=2, extra=""):
    rows, cols = len(matrix), len(matrix[0])
    w = cols * (size + gap) - gap
    h = rows * (size + gap) - gap
    out = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">']
    for r, row in enumerate(matrix):
        for c, v in enumerate(row):
            out.append(
                f'<rect x="{c * (size + gap)}" y="{r * (size + gap)}" width="{size}" height="{size}" '
                f'rx="{radius}" fill="{palette[v][0]}" stroke="var(--cell-stroke)" stroke-width="0.8"/>'
            )
    out.append(extra)
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------------------
# Illustrations
# ---------------------------------------------------------------------------

LULC_TILE = [
    [3, 3, 3, 3, 4, 4, 12, 12],
    [3, 3, 3, 15, 15, 4, 12, 33],
    [3, 3, 15, 15, 15, 39, 33, 33],
    [3, 15, 15, 21, 39, 39, 39, 33],
    [3, 3, 15, 21, 39, 39, 41, 11],
    [3, 3, 3, 15, 24, 24, 41, 11],
]


def illus_stack():
    """Isometric stack of annual land cover maps."""
    size, gap = 9, 1.5
    out = ['<svg width="230" height="190" viewBox="0 0 230 190">']
    labels = ["2025", "…", "1987", "1986", "1985"]
    for layer in range(5):
        dy = 22 + layer * 26
        out.append(f'<g transform="translate(40 {dy}) skewX(-28) scale(1 .55)">')
        out.append(
            f'<rect x="-6" y="-6" width="{8 * (size + gap) + 10}" height="{6 * (size + gap) + 10}" rx="6" '
            f'fill="var(--card)" stroke="var(--line)" stroke-width="1.6"/>'
        )
        for r, row in enumerate(LULC_TILE):
            for c, v in enumerate(row):
                vv = v
                # make the layers differ a little: pasture advances over forest over time
                if layer < 2 and v == 3 and c >= 1 and r in (1, 2, 4):
                    vv = 15
                out.append(
                    f'<rect x="{c * (size + gap)}" y="{r * (size + gap)}" width="{size}" height="{size}" '
                    f'rx="1.5" fill="{LULC[vv][0]}"/>'
                )
        out.append("</g>")
        out.append(
            f'<text x="196" y="{dy + 20}" font-size="12" font-weight="600" fill="var(--muted)">{labels[layer]}</text>'
        )
    out.append("</svg>")
    return "".join(out)


def illus_aggregate():
    size = 11
    left = grid(LULC_TILE, LULC, size)
    agg = [[LOOKUP[v] for v in row] for row in LULC_TILE]
    right = grid(agg, TRANSITION, size)
    return (
        f'<div class="agg"><div>{left}<div class="cap">land cover classes</div></div>'
        f'<div class="mini-arrow">→</div>'
        f'<div>{right}<div class="cap">3 states</div></div></div>'
    )


def illus_window():
    """A sliding 4-year window over a pixel series."""
    seq = [2, 2, 2, 1, 1, 1, 2, 2, 2, 2]
    size, gap = 20, 3
    w = len(seq) * (size + gap)
    out = [f'<svg width="{w + 4}" height="92" viewBox="-2 -2 {w + 4} 96">']
    out.append(cells([(TRANSITION[v][0], v) for v in seq], size, gap, 4, True, y0=18))
    for i, (start, label) in enumerate([(0, "t"), (1, "t+1"), (2, "t+2")]):
        x = start * (size + gap) - 3
        out.append(
            f'<rect x="{x}" y="{12 + i * 0}" width="{4 * (size + gap) + 3}" height="{size + 12}" rx="7" '
            f'fill="none" stroke="var(--accent)" stroke-width="{2.2 if i == 1 else 1.2}" '
            f'stroke-dasharray="{"" if i == 1 else "4 4"}" opacity="{1 if i == 1 else .55}"/>'
        )
    out.append(
        f'<text x="{1 * (size + gap) + 2 * (size + gap)}" y="70" text-anchor="middle" font-size="12" '
        f'font-weight="600" fill="var(--accent)">4-year window slides one year at a time</text>'
    )
    out.append(
        f'<text x="{w / 2}" y="88" text-anchor="middle" font-size="11.5" fill="var(--muted)">'
        f'each match rewrites the window in place</text>'
    )
    out.append("</svg>")
    return "".join(out)


def illus_frequency():
    before = [1, 1, 2, 2, 2, 4]
    after = [1, 1, 3, 3, 3, 6]
    return (
        f'<div class="freq">'
        f'<div class="freq-row"><span>before</span>{rule_chip_row(before)}</div>'
        f'<div class="freq-row"><span>after</span>{rule_chip_row(after, ref=before)}</div>'
        f'</div>'
    )


def rule_chip_row(values, ref=None, size=20):
    gap = 3
    w = len(values) * (size + gap) - gap
    svg = [f'<svg width="{w + 4}" height="{size + 4}" viewBox="-2 -2 {w + 4} {size + 4}">']
    svg.append(cells([(TRANSITION[v][0], v) for v in values], size, gap, 4, True))
    if ref:
        for i, (a, b) in enumerate(zip(ref, values)):
            if a != b:
                svg.append(
                    f'<rect x="{i * (size + gap) - 1.5}" y="-1.5" width="{size + 3}" height="{size + 3}" rx="5" '
                    f'fill="none" stroke="var(--accent)" stroke-width="2"/>'
                )
    svg.append("</svg>")
    return "".join(svg)


FILTER_BEFORE = [
    [2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
    [2, 4, 4, 4, 4, 2, 2, 2, 2, 2],
    [2, 4, 4, 4, 4, 4, 2, 2, 4, 2],
    [2, 4, 4, 4, 4, 4, 2, 4, 4, 2],
    [2, 2, 4, 4, 4, 2, 2, 2, 2, 2],
    [2, 2, 2, 2, 2, 2, 3, 3, 2, 2],
    [2, 2, 2, 2, 2, 2, 2, 3, 2, 2],
]


def illus_filter():
    after = [row[:] for row in FILTER_BEFORE]
    for r, c in [(2, 8), (3, 7), (3, 8), (5, 6), (5, 7), (6, 7)]:
        after[r][c] = 7
    size = 9
    st = size + 2
    ring = (
        f'<rect x="{7 * st - 2}" y="{2 * st - 2}" width="{2 * st + 2}" height="{2 * st + 2}" rx="5" fill="none" '
        f'stroke="var(--accent)" stroke-width="1.8" stroke-dasharray="3 2"/>'
        f'<rect x="{6 * st - 2}" y="{5 * st - 2}" width="{2 * st + 2}" height="{2 * st + 2}" rx="5" fill="none" '
        f'stroke="var(--accent)" stroke-width="1.8" stroke-dasharray="3 2"/>'
    )
    return (
        f'<div class="agg"><div>{grid(FILTER_BEFORE, TRANSITION, size, extra=ring)}'
        f'<div class="cap">year t, before</div></div><div class="mini-arrow">→</div>'
        f'<div>{grid(after, TRANSITION, size)}<div class="cap">year t, after</div></div></div>'
    )


def illus_outputs_map():
    m = [
        [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
        [2, 2, 4, 4, 1, 1, 2, 2, 2, 2, 7, 7],
        [2, 4, 1, 1, 1, 1, 1, 2, 2, 2, 7, 7],
        [2, 1, 1, 3, 3, 1, 1, 6, 2, 2, 2, 7],
        [2, 1, 3, 3, 3, 5, 1, 1, 2, 2, 2, 2],
        [2, 2, 1, 3, 3, 1, 1, 1, 4, 2, 2, 2],
        [2, 2, 2, 1, 1, 1, 2, 2, 2, 2, 2, 0],
        [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0],
    ]
    return grid(m, TRANSITION, 13, 1.5, 1.5)


def illus_age():
    seq = [0, 0, 1, 2, 3, 4, 5, 6, 0, 0, 1, 2]
    w, h = 12 * 15, 64
    out = [f'<svg width="{w}" height="{h + 16}" viewBox="0 0 {w} {h + 16}">']
    for i, v in enumerate(seq):
        bh = 8 + v * 8 if v else 3
        out.append(
            f'<rect x="{i * 15}" y="{h - bh}" width="11" height="{bh}" rx="2" '
            f'fill="{TRANSITION[3][0] if v else "var(--line)"}"/>'
        )
        out.append(
            f'<text x="{i * 15 + 5.5}" y="{h + 13}" text-anchor="middle" font-size="10" fill="var(--muted)">{v}</text>'
        )
    out.append("</svg>")
    return "".join(out)


def illus_freq_map():
    m = [
        [0, 0, 1, 1, 0, 0, 0, 0, 0, 0],
        [0, 1, 2, 1, 1, 0, 0, 0, 1, 0],
        [0, 1, 3, 2, 1, 0, 0, 1, 1, 0],
        [0, 0, 1, 2, 1, 0, 0, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
    ]
    pal = {0: ("var(--surface)", ""), 1: ("#fdd0a2", ""), 2: ("#fd8d3c", ""), 3: ("#d94701", "")}
    return grid(m, pal, 13, 1.5, 1.5)


# ---------------------------------------------------------------------------
# Example pixel (41 years)
# ---------------------------------------------------------------------------


def pixel_story():
    size, gap = 27, 3
    step = size + gap
    label_w = 0
    rows = [
        ("Land cover", [(LULC[RAW[y]][0], None) for y in YEARS]),
        ("Aggregated", [(TRANSITION[AGG[y]][0], AGG[y]) for y in YEARS]),
        ("Blip filter", [(TRANSITION[BLIP[y]][0], BLIP[y]) for y in YEARS]),
        ("Transitions", [(TRANSITION[FINAL[y]][0], FINAL[y]) for y in YEARS]),
    ]
    w = len(YEARS) * step - gap
    row_h = 44
    top = 34
    h = top + len(rows) * row_h + 118
    out = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" class="story">']
    # warm-up band
    out.append(
        f'<rect x="-4" y="{top - 8}" width="{2 * step + 2}" height="{len(rows) * row_h + 2}" rx="8" '
        f'fill="var(--warm)"/>'
    )
    # year axis
    for i, y in enumerate(YEARS):
        if y % 5 == 0 or y in (1987, 2025):
            out.append(
                f'<text x="{i * step + size / 2}" y="16" text-anchor="middle" font-size="12" font-weight="600" '
                f'fill="var(--muted)">{y}</text>'
            )
            out.append(
                f'<path d="M{i * step + size / 2} 22 V27" stroke="var(--line)" stroke-width="1.4"/>'
            )
    for r, (name, vals) in enumerate(rows):
        y0 = top + r * row_h
        out.append(cells(vals, size, gap, 4, label=r > 0, y0=y0))
    # changed cells between rows
    def mark(year, row, color="var(--accent)"):
        i = YEARS.index(year)
        return (
            f'<rect x="{i * step - 2}" y="{top + row * row_h - 2}" width="{size + 4}" height="{size + 4}" rx="6" '
            f'fill="none" stroke="{color}" stroke-width="2.4"/>'
        )
    out.append(mark(1998, 2))
    for y in (1995, 2003, 2004, 2011, 2023, 2024, 2025):
        out.append(mark(y, 3))
    # callouts under the result row
    base = top + 3 * row_h + size + 4
    events = [
        (1995, 0, "1995 · primary vegetation", "suppression (4)"),
        (1998, 1, "1998 · one-year blip", "reverted to anthropic"),
        (2003, 0, "2003 · recovery (5), then", "secondary vegetation (3)"),
        (2011, 0, "2011 · secondary vegetation", "suppression (6)"),
        (2023, 0, "2023–2025 · regeneration still", "under way at the series end"),
    ]
    for year, level, l1, l2 in events:
        i = YEARS.index(year)
        cx = i * step + size / 2
        stem = 16 + level * 46
        if year == 2023:
            tx, anchor = len(YEARS) * step - gap, "end"
        else:
            tx, anchor = cx - size / 2 + 2, "start"
        out.append(f'<path d="M{cx} {base} V{base + stem}" stroke="var(--accent)" stroke-width="1.6"/>')
        out.append(f'<circle cx="{cx}" cy="{base + stem}" r="3" fill="var(--accent)"/>')
        out.append(
            f'<text x="{tx}" y="{base + stem + 20}" text-anchor="{anchor}" font-size="12.5" font-weight="600" '
            f'fill="var(--text)">{esc(l1)}</text>'
        )
        out.append(
            f'<text x="{tx}" y="{base + stem + 37}" text-anchor="{anchor}" font-size="12.5" fill="var(--muted)">{esc(l2)}</text>'
        )
    out.append("</svg>")
    labels = "".join(
        f'<div class="row-label" style="top:{top + r * row_h + 4}px">{esc(name)}</div>'
        for r, (name, _) in enumerate(rows)
    )
    return f'<div class="story-wrap"><div class="row-labels">{labels}</div>{"".join(out)}</div>'


# ---------------------------------------------------------------------------
# Rule catalogue
# ---------------------------------------------------------------------------

RULE_GROUPS = [
    ("1a", "RULES_KERNEL3_VEG_BLIP", "Blip filter", "3-year · whole series",
     ["One vegetation year between anthropic years is noise"]),
    ("1b", "RULES_KERNEL6_SECONDARY_END", "End-of-series windows", "6-year · anchored on 2020–2025",
     ["4 anthropic + 2 vegetation", "5 anthropic + 1 vegetation", "Vegetation, 4 anthropic, vegetation"]),
    ("1b", "RULES_KERNEL4_SECONDARY_END_REVERT", "End-of-series revert", "4-year · anchored on 2022–2025",
     ["Unconfirmed 2-year vegetation block"]),
    ("2", "RULES_KERNEL4", "Primary vegetation suppression", "4-year · whole series",
     ["Two vegetation years, then two anthropic"]),
    ("3", "RULES_KERNEL4_SECONDARY", "Secondary vegetation dynamics", "4-year · whole series",
     ["Establishment", "Recovery", "Persistence", "Suppression", "Suppression with recovery",
      "Persistence", "Persistence", "Short regrowth followed by suppression"]),
    ("4", "RULES_KERNEL3_SECONDARY", "Suppression inside secondary", "3-year · whole series",
     ["Suppression after secondary vegetation"]),
    ("5", "RULES_KERNEL4_END", "Unconfirmed at the series end", "4-year · anchored on 2022–2025",
     ["Primary vegetation suppression", "Secondary vegetation suppression"]),
]


def rule_catalogue():
    cards = []
    for step, name, title, scope, notes in RULE_GROUPS:
        rules = RULES[name]
        assert len(rules) == len(notes), name
        items = []
        for rule, note in zip(rules, notes):
            bef, aft, min_start = rule
            ms = f'<span class="ms{" ms1" if min_start else ""}">min_start {min_start}</span>'
            items.append(
                f'<div class="rule">{rule_chip(bef, aft, 20 if len(bef) > 4 else 22)}'
                f'<div class="rule-note">{esc(note)}{ms}</div></div>'
            )
        wide = " wide" if name == "RULES_KERNEL4_SECONDARY" else ""
        cards.append(
            f'<div class="rcard{wide}"><div class="rhead"><span class="step">Step {step}</span>'
            f'<span class="rtitle">{esc(title)}</span></div><div class="rscope"><code>{name}</code> · {esc(scope)}</div>'
            f'<div class="rules">{"".join(items)}</div></div>'
        )
    return "".join(cards)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

ICONS = {
    "layers": '<path d="M12 3 3 8l9 5 9-5-9-5Z"/><path d="m3 13 9 5 9-5"/><path d="m3 17.5 9 5 9-5" opacity=".5"/>',
    "merge": '<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="12" r="2.5"/><path d="M8.5 6.5 15.5 11M8.5 17.5l7-4.5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "sigma": '<path d="M17 5H7l6 7-6 7h10"/>',
    "filter": '<path d="M4 5h16l-6 8v6l-4-2v-4L4 5Z"/>',
    "out": '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 12h8M13 9l3 3-3 3"/>',
}


def icon(name):
    return (
        f'<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>'
    )


def stage(num, ic, title, sub, body, pill, cls=""):
    return (
        f'<div class="stage {cls}"><div class="bar"></div><div class="shead"><span class="num">{num}</span>'
        f'<div><div class="stitle">{title}</div><div class="ssub">{sub}</div></div>'
        f'<span class="sicon">{icon(ic)}</span></div><div class="sbody">{body}</div>'
        f'<div class="pill">{pill}</div></div>'
    )


def legend():
    items = "".join(
        f'<span class="lg"><i style="background:{c}"></i><b>{k}</b> {esc(n)}</span>'
        for k, (c, n) in TRANSITION.items()
    )
    return f'<div class="legend">{items}</div>'


def lulc_legend():
    used = [3, 15, 39]
    return "".join(
        f'<span class="lg small"><i style="background:{LULC[k][0]}"></i>{esc(LULC[k][1])} ({k})</span>' for k in used
    )


def build_html(theme):
    t = THEMES[theme]
    css_vars = "".join(f"--{k.replace('_', '-')}:{v};" for k, v in t.items())
    n_classes = len(LOOKUP)
    n_rules = sum(len(RULES[g[1]]) for g in RULE_GROUPS)
    group_size = SCALARS["GROUP_SIZE_FILTER"]

    stages = "".join([
        stage("01", "layers", "Land cover input", "Collection 11 integration",
              illus_stack(),
              "41 annual maps · 1985–2025 · 30 m"),
        stage("02", "merge", "Aggregation", "<code>CLASS_LOOKUP</code>",
              illus_aggregate()
              + '<ul><li>Natural vegetation → <b>2</b></li><li>Farming, urban, mining → <b>1</b></li>'
                '<li>Water, beach, rock → <b>7</b></li></ul>',
              f"{n_classes} land cover codes → 3 states"),
        stage("03", "clock", "Temporal rules", "kernels of 3, 4 and 6 years",
              illus_window()
              + '<ul><li>Applied in a fixed order, each set over the output of the previous one</li>'
                '<li><code>min_start = 1</code> keeps 3 and 5 out of the first year</li></ul>',
              f"{n_rules} rules in 7 sets"),
        stage("04", "sigma", "Post-processing", "frequency and tail guard",
              illus_frequency()
              + '<ul><li>Vegetation after any anthropic year is secondary (2→3)</li>'
                '<li>Suppression after 2+ anthropic years is of secondary (4→6)</li>'
                '<li>Tail guard drops 3 right after anthropic in the last 2 years</li></ul>',
              "cumulative anthropic frequency"),
        stage("05", "filter", "Spatial filter", "connected pixels, year by year",
              illus_filter()
              + f'<ul><li>Suppression (4, 6) and secondary (3, 5) filtered on separate masks</li>'
                f'<li>8-connected patches of ≤ {group_size} px become 7</li></ul>',
              f"≤ {group_size} px (~1 ha) → other transitions"),
    ])

    outputs = f'''
      <div class="ocard pub"><div class="obadge">public · v5</div>
        <div class="otitle">Deforestation and secondary vegetation</div>
        <div class="ovis">{illus_outputs_map()}</div>
        <div class="otext">One band per year, codes 0–7<br><code>classification_1987 … 2025</code></div></div>
      <div class="ocard pub"><div class="obadge">public · by_coverage_v1</div>
        <div class="otitle">Crossed with land cover</div>
        <div class="ovis enc"><div class="code-big"><span style="color:{TRANSITION[4][0]}">4</span><span>77</span></div>
          <div class="enc-eq">transition × 100 + land cover (year − 1)</div>
          <div class="enc-ex">477 = primary vegetation suppression on class 77</div></div>
        <div class="otext"><code>uint16</code> · land cover in the public C11 legend (13 → 77)</div></div>
      <div class="ocard"><div class="obadge int">internal</div>
        <div class="otitle">Accumulated by period</div>
        <div class="ovis periods">{periods_svg()}</div>
        <div class="otext">First event in each of 780 periods<br>deforestation and secondary vegetation bands</div></div>
      <div class="ocard"><div class="obadge int">internal</div>
        <div class="otitle">Deforestation frequency</div>
        <div class="ovis">{illus_freq_map()}</div>
        <div class="otext">Years with 4 or 6 in each period<br><code>uint8</code> · 780 bands</div></div>
      <div class="ocard"><div class="obadge int">internal</div>
        <div class="otitle">Secondary vegetation age</div>
        <div class="ovis">{illus_age()}</div>
        <div class="otext">age(t) = (age(t−1) + sv(t)) × sv(t)<br>resets when the pixel leaves 3 or 5</div></div>
    '''

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Method figure ({theme})</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700&family=Open+Sans:wght@400;600;700&display=block" rel="stylesheet">
<style>
:root{{{css_vars}}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:var(--bg)}}
body{{font-family:'Open Sans',sans-serif;color:var(--text);width:{WIDTH}px}}
#wrap{{width:{WIDTH}px;padding:44px 44px 36px;background:var(--bg)}}
code{{font-family:'SFMono-Regular',Menlo,Consolas,monospace;font-size:.88em;background:var(--accent-soft);color:var(--accent);padding:1px 5px;border-radius:4px}}
.over{{font-size:13px;font-weight:700;letter-spacing:.22em;text-transform:uppercase;color:var(--accent)}}
h1{{font-family:'Montserrat','Open Sans',sans-serif;font-size:34px;font-weight:700;line-height:1.2;margin-top:8px;letter-spacing:-.01em}}
h1 em{{font-style:normal;color:var(--accent)}}
.lead{{font-size:16px;line-height:1.55;color:var(--muted);margin-top:10px;max-width:1180px}}
.section{{margin-top:34px}}
.shdr{{display:flex;align-items:baseline;gap:14px;margin-bottom:14px}}
.shdr h2{{font-family:'Montserrat','Open Sans',sans-serif;font-size:19px;font-weight:700}}
.shdr span{{font-size:13.5px;color:var(--muted)}}
.flow{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:30px;position:relative}}
.stage{{background:var(--card);border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);padding:18px 18px 16px;position:relative;display:flex;flex-direction:column;overflow:visible}}
.stage .bar{{position:absolute;left:16px;right:16px;top:-1px;height:4px;border-radius:0 0 4px 4px;background:linear-gradient(90deg,var(--accent),{TRANSITION[3][0]})}}
.stage:not(:last-child)::after{{content:'';position:absolute;right:-27px;top:50%;width:24px;height:24px;
  background:no-repeat center/18px url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M4 12h14M13 6l6 6-6 6' fill='none' stroke='{t["accent"].replace("#", "%23")}' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")}}
.shead{{display:flex;gap:11px;align-items:flex-start}}
.num{{flex:none;width:36px;height:36px;border-radius:10px;background:var(--accent-soft);color:var(--accent);font-weight:700;font-size:14px;display:grid;place-items:center}}
.stitle{{font-size:16.5px;font-weight:700;line-height:1.25}}
.ssub{{font-size:12.5px;color:var(--muted);margin-top:2px}}
.sicon{{margin-left:auto;color:var(--faint)}}
.sbody{{margin-top:14px;flex:1;display:flex;flex-direction:column;align-items:center;gap:12px}}
.sbody ul{{list-style:none;align-self:stretch;display:flex;flex-direction:column;gap:6px}}
.sbody li{{font-size:12.8px;line-height:1.45;color:var(--muted);padding-left:14px;position:relative}}
.sbody li::before{{content:'';position:absolute;left:0;top:7px;width:6px;height:6px;border-radius:2px;background:var(--accent)}}
.sbody li b{{color:var(--text)}}
.pill{{margin-top:14px;align-self:flex-start;font-size:12.3px;font-weight:600;color:var(--accent);background:var(--accent-soft);border:1px solid var(--accent-line);padding:5px 11px;border-radius:100px}}
.agg{{display:flex;align-items:center;gap:10px}}
.mini-arrow{{color:var(--accent);font-size:20px;font-weight:700}}
.cap{{font-size:11px;color:var(--faint);text-align:center;margin-top:5px}}
.freq{{display:flex;flex-direction:column;gap:6px}}
.freq-row{{display:flex;align-items:center;gap:8px}}
.freq-row span{{width:40px;font-size:11px;color:var(--faint);text-align:right}}
.panel{{background:var(--surface);border:1px solid var(--border);border-radius:18px;padding:22px 24px 18px}}
.story-wrap{{position:relative;padding-left:104px}}
.row-labels{{position:absolute;left:0;top:0}}
.row-label{{position:absolute;left:0;width:96px;font-size:13px;font-weight:600;color:var(--muted);white-space:nowrap}}
.story text{{font-family:'Open Sans',sans-serif}}
.story-foot{{display:flex;justify-content:space-between;align-items:center;margin-top:6px;gap:20px}}
.warm-note{{font-size:12.3px;color:var(--muted)}}
.warm-note i{{display:inline-block;width:14px;height:14px;border-radius:4px;background:var(--warm);border:1px solid var(--line);vertical-align:-2px;margin-right:6px}}
.rgrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}
.rcard{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:14px 16px}}
.rcard.wide{{grid-column:span 2;grid-row:span 2}}
.rcard.wide .rules{{display:grid;grid-template-columns:1fr 1fr;gap:12px 18px}}
.rhead{{display:flex;align-items:center;gap:9px}}
.step{{font-size:11px;font-weight:700;color:var(--accent);background:var(--accent-soft);padding:2px 8px;border-radius:100px;white-space:nowrap}}
.rtitle{{font-size:14.5px;font-weight:700}}
.rscope{{font-size:11.6px;color:var(--muted);margin-top:6px}}
.rscope code{{font-size:10.6px}}
.rules{{margin-top:12px;display:flex;flex-direction:column;gap:12px}}
.rule{{display:flex;flex-direction:column;gap:5px}}
.chip text{{font-family:'Open Sans',sans-serif}}
.rule-note{{font-size:12px;color:var(--muted);display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
.ms{{font-size:10.5px;font-weight:600;color:var(--faint);border:1px solid var(--border);border-radius:100px;padding:0 7px}}
.ms1{{color:var(--accent);border-color:var(--accent-line)}}
.ogrid{{display:grid;grid-template-columns:repeat(5,1fr);gap:18px}}
.ocard{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:10px}}
.ocard.pub{{border-color:var(--accent-line);box-shadow:var(--shadow)}}
.obadge{{align-self:flex-start;font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);background:var(--accent-soft);padding:3px 9px;border-radius:100px}}
.obadge.int{{color:var(--muted);background:var(--surface);border:1px solid var(--border)}}
.otitle{{font-size:14.5px;font-weight:700;line-height:1.3}}
.ovis{{min-height:118px;display:grid;place-items:center}}
.otext{{font-size:12px;line-height:1.5;color:var(--muted)}}
.enc{{display:flex;flex-direction:column;align-items:center;gap:6px}}
.code-big{{font-family:'Montserrat',sans-serif;font-size:44px;font-weight:700;letter-spacing:.02em;line-height:1}}
.enc-eq{{font-size:11.5px;font-weight:600;color:var(--text)}}
.enc-ex{{font-size:11px;color:var(--muted)}}
.legend{{display:flex;flex-wrap:wrap;gap:8px 18px}}
.lg{{display:inline-flex;align-items:center;gap:7px;font-size:13px;color:var(--muted)}}
.lg b{{color:var(--text)}}
.lg i{{width:16px;height:16px;border-radius:4px;border:1px solid var(--cell-stroke);display:inline-block}}
.lg.small{{font-size:12px}}
.lg.small i{{width:13px;height:13px}}
.foot{{margin-top:26px;padding-top:16px;border-top:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;gap:24px}}
.src{{font-size:12px;color:var(--faint);line-height:1.5}}
</style></head>
<body><div id="wrap">
  <div class="over">MapBiomas Brazil · Collection 11 · 1985–2025</div>
  <h1>From annual land cover maps to <em>deforestation and secondary vegetation</em></h1>
  <p class="lead">Each pixel's 41-year land cover series is reduced to three states, rewritten by temporal rules that
  confirm every change with the years around it, corrected by its own history, and cleaned of patches smaller than about one hectare.</p>

  <div class="section">
    <div class="shdr"><h2>Processing chain</h2><span>run per 1:1,000,000 CIM block (49 blocks) on Google Earth Engine</span></div>
    <div class="flow">{stages}</div>
  </div>

  <div class="section panel">
    <div class="shdr"><h2>One pixel, 41 years</h2><span>a real run of the rules on an example series</span></div>
    {pixel_story()}
    <div class="story-foot">
      <div class="warm-note"><i></i>1985–1986 are warm-up years for the rules with <code>min_start = 1</code> and are not published</div>
      <div class="legend">{lulc_legend()}</div>
    </div>
  </div>

  <div class="section">
    <div class="shdr"><h2>Rule catalogue</h2><span>before → after, in execution order · outlined cells are the ones a rule rewrites</span></div>
    <div class="rgrid">{rule_catalogue()}</div>
  </div>

  <div class="section">
    <div class="shdr"><h2>Outputs</h2><span>public assets in <code>projects/mapbiomas-public/assets/brazil/lulc/collection11/</code></span></div>
    <div class="ogrid">{outputs}</div>
  </div>

  <div class="foot">
    {legend()}
  </div>
  <div class="src" style="margin-top:12px">Source: <code>mapbiomas_brazil_deforestation_secondary_vegetation.py</code> — rules and class aggregation read from the code; the example pixel is computed by the same rules.</div>
</div>
<script>
document.fonts.ready.then(() => {{
  document.title = 'H=' + Math.ceil(document.getElementById('wrap').getBoundingClientRect().height);
}});
</script>
</body></html>'''


def periods_svg():
    years = 12
    size = 11
    out = [f'<svg width="{years * 13}" height="{5 * 13 + 4}" viewBox="0 0 {years * 13} {5 * 13 + 4}">']
    spans = [(0, 11), (2, 7), (4, 9), (6, 11), (8, 10)]
    for r, (a, b) in enumerate(spans):
        for i in range(years):
            inside = a <= i <= b
            color = "var(--line)"
            if inside:
                color = TRANSITION[4][0] if i == 5 else (TRANSITION[3][0] if i == 9 else "var(--accent-soft)")
                if i == 5 and not (a <= 5 <= b):
                    color = "var(--accent-soft)"
            out.append(
                f'<rect x="{i * 13}" y="{r * 13}" width="{size}" height="{size}" rx="2" fill="{color}" '
                f'opacity="{1 if inside else .45}"/>'
            )
    out.append("</svg>")
    return "".join(out)


def find_chrome():
    for c in [os.environ.get("CHROME"), "google-chrome", "chromium", "chromium-browser", "google-chrome-stable"]:
        if c and shutil.which(c):
            return shutil.which(c)
    sys.exit("Chrome/Chromium not found; set CHROME")


def render(html_path, png_path, chrome):
    url = "file://" + html_path
    common = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
              "--virtual-time-budget=8000", f"--window-size={WIDTH},4000"]
    dom = subprocess.run(common + ["--dump-dom", url], capture_output=True, text=True, check=True).stdout
    m = re.search(r"<title>H=(\d+)</title>", dom)
    if not m:
        sys.exit("could not measure the page height (fonts did not load?)")
    height = int(m.group(1))
    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--virtual-time-budget=8000",
         "--force-device-scale-factor=2", f"--window-size={WIDTH},{height}",
         f"--screenshot={png_path}", url],
        check=True, capture_output=True,
    )
    return height


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--html-only", action="store_true")
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    chrome = None if args.html_only else find_chrome()
    for theme in THEMES:
        html_path = os.path.join(args.out, f"method-{theme}.html")
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(build_html(theme))
        if chrome:
            png = os.path.join(args.out, f"method-{theme}.png")
            h = render(os.path.abspath(html_path), png, chrome)
            print(f"{theme}: {png} ({WIDTH * 2}×{h * 2})")
        else:
            print(f"{theme}: {html_path}")


if __name__ == "__main__":
    main()
