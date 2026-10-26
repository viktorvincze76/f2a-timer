"""Breadboard layout for the bench-test front end, checked against the schematic.

Every part leg and jumper wire is given as a breadboard hole. The script works
out which holes are connected (strips, power rails, wires), compares the
result with the schematic's netlist, and only then draws the layout and prints
a step-by-step wiring list.

    ../sim/.venv/bin/python breadboard.py     # writes docs/img/bench_breadboard.png/.svg

Breadboard: standard 830 holes, rows 1-63, columns a-e | gap | f-j. Each half
row (a-e or f-j) is one strip. Two rails on each long side:
L+ / L- next to column a, R+ / R- next to column j.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "docs" / "img"
COLS = "abcdefghij"
RAILS = ("L+", "L-", "R+", "R-")

# ---- the layout -------------------------------------------------------------
# Hole = (column letter or rail name, row). Parts list legs in pin order.

PICO_ROWS = range(1, 21)  # Pico 2 H straddles the gap: left pins in c, right pins in h, USB at row 1


def pico_pin_hole(pin: int):
    """Pico pin 1-20 down the left side (column c), 21-40 up the right side (column h)."""
    return ("c", pin) if pin <= 20 else ("h", 41 - pin)


PICO = {"3V3": 36, "AGND": 33, "GP26": 31, "GP27": 32, "GP15": 20}

U1 = {1: ("e", 30), 2: ("e", 31), 3: ("e", 32), 4: ("e", 33),  # MCP6022, notch towards row 29
      8: ("f", 30), 7: ("f", 31), 6: ("f", 32), 5: ("f", 33)}

# name: (kind, label, [legs in pin order])
PARTS = {
    "R10": ("R", "10Ω", [("i", 5), ("R+", 5)]),
    "C10": ("E", "100µ", [("R+", 7), ("R-", 7)]),          # + first
    "C11": ("C", "100n", [("R+", 10), ("R-", 10)]),
    "R1": ("R", "470k", [("b", 31), ("b", 30)]),           # TIA in -> TIA out
    "C1": ("C", "22p", [("c", 31), ("c", 30)]),
    "R2": ("R", "1k", [("d", 30), ("d", 25)]),             # TIA out -> ADC0
    "C2": ("C", "10n", [("b", 25), ("L-", 25)]),
    "R11": ("R", "56k", [("L+", 32), ("a", 32)]),          # VA -> Vb
    "R12": ("R", "1k", [("b", 32), ("L-", 34)]),           # Vb -> AGND
    "C12": ("C", "100n", [("c", 32), ("L-", 36)]),
    "C3": ("F", "1µ film", [("g", 35), ("g", 33)]),        # TIA out (via wire) -> U1 pin 5
    "R3": ("R", "100k", [("h", 33), ("h", 38)]),           # pin 5 -> Vmid
    "R4": ("R", "100k", [("R+", 38), ("i", 38)]),          # VA -> Vmid
    "R5": ("R", "100k", [("j", 38), ("R-", 39)]),          # Vmid -> AGND
    "C4": ("C", "10µ", [("g", 38), ("R-", 41)]),
    "R6": ("R", "100k", [("g", 32), ("g", 31)]),           # pin 6 -> pin 7
    "C5": ("C", "1n", [("h", 32), ("h", 31)]),
    "R7": ("R", "1k", [("i", 32), ("i", 37)]),             # pin 6 -> C6
    "C6": ("E", "47µ", [("j", 37), ("R-", 37)]),           # + first
    "R8": ("R", "1k", [("i", 31), ("i", 26)]),             # pin 7 -> ADC1
    "C7": ("C", "10n", [("j", 26), ("R-", 26)]),
    "SW1": ("SW", "mark", [("e", 55), ("f", 57)]),         # the two diagonal legs; works either way round
    "D1": ("D", "BPW21R", [("a", 31), ("L-", 31)]),        # cathode, anode: twisted pair from the box
}

# name: (colour, from, to)
WIRES = {
    "W1": ("black", ("j", 8), ("R-", 8)),        # Pico AGND -> R- rail
    "W2": ("orange", ("j", 10), ("a", 25)),      # Pico GP26 <- ADC0 node
    "W3": ("purple", ("j", 9), ("h", 26)),       # Pico GP27 <- ADC1 node
    "W4": ("red", ("j", 30), ("R+", 30)),        # U1 pin 8 -> VA
    "W5": ("black", ("a", 33), ("L-", 33)),      # U1 pin 4 -> AGND
    "W6": ("yellow", ("a", 30), ("h", 35)),      # TIA out -> C3
    "W7": ("white", ("b", 20), ("a", 55)),       # Pico GP15 -> button
    "W8": ("black", ("j", 57), ("R-", 57)),      # button -> AGND
    "W9": ("red", ("R+", 62), ("L+", 62)),       # join the + rails
    "W10": ("black", ("R-", 63), ("L-", 63)),    # join the - rails
}

# ---- the schematic netlist (docs/img/bench_schematic.png) ---------------------
EXPECTED = {
    "3V3": {"PICO.3V3", "R10.1"},
    "VA": {"R10.2", "C10.1", "C11.1", "U1.8", "R11.1", "R4.1"},
    "AGND": {"PICO.AGND", "C10.2", "C11.2", "C12.2", "R12.2", "C4.2", "R5.2", "U1.4", "D1.2",
             "C2.2", "C6.2", "C7.2", "SW1.2"},
    "VB": {"R11.2", "R12.1", "C12.1", "U1.3"},
    "VMID": {"R4.2", "R5.1", "C4.1", "R3.2"},
    "TIA_IN": {"U1.2", "D1.1", "R1.1", "C1.1"},
    "TIA_OUT": {"U1.1", "R1.2", "C1.2", "R2.1", "C3.1"},
    "ADC0": {"R2.2", "C2.1", "PICO.GP26"},
    "HP": {"U1.5", "C3.2", "R3.1"},
    "INB": {"U1.6", "R6.1", "C5.1", "R7.1"},
    "R7C6": {"R7.2", "C6.1"},
    "OUTB": {"U1.7", "R6.2", "C5.2", "R8.1"},
    "ADC1": {"R8.2", "C7.1", "PICO.GP27"},
    "GP15": {"PICO.GP15", "SW1.1"},
}

# ---- connectivity -------------------------------------------------------------


def node_of(hole):
    col, row = hole
    if col in RAILS:
        return col
    return (row, "L" if col in "abcde" else "R")


def pin_holes():
    pins = {f"PICO.{n}": pico_pin_hole(p) for n, p in PICO.items()}
    pins.update({f"U1.{p}": h for p, h in U1.items()})
    for name, (_, _, legs) in PARTS.items():
        for i, h in enumerate(legs, 1):
            pins[f"{name}.{i}"] = h
    return pins


def check() -> list[str]:
    errors = []
    pins = pin_holes()

    # every physical hole used once, nothing under the Pico or in the gap
    used = defaultdict(list)
    for pin, h in pins.items():
        used[h].append(pin)
    for name, (_, a, b) in WIRES.items():
        used[a].append(name)
        used[b].append(name)
    for h, who in used.items():
        if len(who) > 1:
            errors.append(f"hole {h} used twice: {who}")
        col, row = h
        if col not in RAILS and row in PICO_ROWS and col in "defg":
            errors.append(f"hole {h} is under the Pico ({who})")
        if col not in RAILS and row in PICO_ROWS and col in "ch" and not who[0].startswith("PICO"):
            errors.append(f"hole {h} is a Pico pin ({who})")

    # union-find over strips joined by wires
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _, a, b in WIRES.values():
        parent[find(node_of(a))] = find(node_of(b))

    # Pico pins each occupy their own strip; make sure no unused Pico pin shares one
    for p in range(1, 41):
        h = pico_pin_hole(p)
        if p not in PICO.values():
            for pin, ph in pins.items():
                if not pin.startswith("PICO") and find(node_of(ph)) == find(node_of(h)):
                    errors.append(f"{pin} shares a strip with unused Pico pin {p}")

    actual = defaultdict(set)
    for pin, h in pins.items():
        actual[find(node_of(h))].add(pin)
    got = sorted(map(frozenset, actual.values()), key=sorted)
    want = sorted(map(frozenset, EXPECTED.values()), key=sorted)
    if got != want:
        names = {frozenset(v): k for k, v in EXPECTED.items()}
        for s in got:
            if s not in names:
                errors.append(f"unexpected net: {sorted(s)}")
        for s in want:
            if s not in got:
                errors.append(f"missing net {names[s]}: {sorted(s)}")
    return errors


# ---- drawing -------------------------------------------------------------------

Y = {c: i for i, c in enumerate("abcde")} | {c: i + 2 for i, c in enumerate("fghij", 5)}
Y |= {"L-": -1.6, "L+": -2.4, "R-": 13.6, "R+": 14.4}


def xy(hole):
    col, row = hole
    return row, Y[col]


# label offsets (dx, dy) for parts whose default label would collide, per view
LABEL_OFFSET = {"R6": (-0.2, 1.6), "C5": (1.5, 1.6), "R3": (0.2, 0.75), "C6": (-1.5, 0.0),
                "R7": (0.0, 0.7), "R8": (0.0, 0.7)}
LABEL_AT = {"R1": (26.8, 0.7), "C1": (26.8, 1.9), "C3": (37.2, 7.3), "R4": (36.6, 15.6), "R5": (40.0, 15.6),
            "C4": (40.6, 8.2), "R11": (28.2, -4.4), "R12": (34.6, -4.4), "C12": (37.8, -4.4)}
WIRE_LABEL_T = {"W6": 0.72}
ZOOM = (22.5, 41.5)


def draw():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle

    fig = plt.figure(figsize=(22, 17))
    ax_full = fig.add_axes([0.02, 0.56, 0.96, 0.42])
    ax_zoom = fig.add_axes([0.14, 0.01, 0.72, 0.53])
    _draw(ax_full, (-3.5, 66), full=True)
    _draw(ax_zoom, (ZOOM[0] - 0.3, ZOOM[1] + 0.3), full=False)
    ax_full.add_patch(Rectangle((ZOOM[0], -3.0), ZOOM[1] - ZOOM[0], 17.9, fill=False, ec="#06c", lw=2, ls="--", zorder=20))
    ax_full.text(ZOOM[0] + 0.2, -4.1, "enlarged below", color="#06c", fontsize=10, zorder=20)
    ax_full.text(0, 16.6, "Bench test: breadboard layout  (checked against the schematic by sensor/bench/breadboard.py)",
                 fontsize=14, weight="bold")
    ax_full.text(0, 15.7, "Rails: L+ / R+ = +VA (filtered 3.3 V), L\u2212 / R\u2212 = AGND.  "
                 "Rail rows are approximate: any hole of the same rail works.  "
                 "Row numbers are printed on most breadboards.", fontsize=10, color="#444")
    ax_zoom.text(ZOOM[0], 16.2, f"Rows {ZOOM[0] + 0.5:.0f}–{ZOOM[1] - 0.5:.0f} enlarged: the analog front end",
                 fontsize=13, weight="bold", color="#06c")

    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "bench_breadboard.png", dpi=100)
    fig.savefig(OUT / "bench_breadboard.svg")


def _draw(ax, xlim, full):
    _draw_items(ax, xlim, full)
    for t in ax.texts:
        t.set_clip_on(True)


def _draw_items(ax, xlim, full):
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle

    k = 1.0 if full else 1.9  # font / marker scale
    in_zoom = lambda *xs: all(ZOOM[0] <= x <= ZOOM[1] for x in xs)  # noqa: E731
    show_label = lambda *xs: not full or not in_zoom(*xs)  # noqa: E731

    ax.set_xlim(*xlim)
    ax.set_ylim(-5.6 if full else -6.6, 17.0)
    ax.set_aspect("equal")
    ax.axis("off")

    # board
    ax.add_patch(FancyBboxPatch((-0.6, -3.2), 64.6, 18.4, boxstyle="round,pad=0.3", fc="#f4f1ea", ec="#999"))
    ax.add_patch(Rectangle((-0.6, 4.4), 64.6, 2.2, fc="#e4e0d6", ec="none"))  # centre gap
    for rail, colour in (("L+", "#d22"), ("L-", "#24c"), ("R+", "#d22"), ("R-", "#24c")):
        y = Y[rail]
        ax.plot([0.5, 63.5], [y + (0.4 if rail in ("R+", "L-") else -0.4)] * 2, color=colour, lw=1.2)
        sign = "+" if rail[1] == "+" else "\u2212"
        for x in ((-1.4, 64.6) if full else (xlim[0] + 0.4,)):
            ax.text(x, y, sign, color=colour, fontsize=13 * k, ha="center", va="center", weight="bold")
        for r in range(1, 64):
            if r % 6:  # rails come in groups of five
                ax.plot(r, y, "s", ms=3.2 * k, color="#bbb")
    for r in range(1, 64):
        for c in COLS:
            ax.plot(r, Y[c], "s", ms=3.2 * k, color="#bbb")
        if full and (r == 1 or r % 5 == 0) or not full:
            ax.text(r, -0.6, str(r), fontsize=7 * k, ha="center", va="center", color="#777")
            ax.text(r, 11.6, str(r), fontsize=7 * k, ha="center", va="center", color="#777")
    for c in COLS:
        ax.text(xlim[0] + (0.9 if full else 0.75), Y[c], c, fontsize=8 * k, ha="right", va="center", color="#777")

    # Pico 2 H
    ax.add_patch(FancyBboxPatch((0.4, Y["c"] - 0.6), 20.2, Y["h"] - Y["c"] + 1.2,
                                boxstyle="round,pad=0.1", fc="#2e8b57", ec="#1b5e3a", alpha=0.92, zorder=3))
    ax.add_patch(Rectangle((-1.2, 4.6), 1.7, 1.8, fc="#bbb", ec="#666", zorder=4))
    ax.text(-0.35, 5.5, "USB", fontsize=7, ha="center", va="center", zorder=5)
    ax.text(10.5, 5.5, "Raspberry Pi Pico 2 H\n(USB end at row 1)", color="white", fontsize=12,
            ha="center", va="center", zorder=5, weight="bold")
    for p in range(1, 41):
        x, y = xy(pico_pin_hole(p))
        ax.plot(x, y, "o", ms=4, color="#e8c547", zorder=5)
    # pin labels staggered outside the board, with leader lines
    label_pos = {"3V3": (3.0, 15.6), "AGND": (7.0, 15.6), "GP27": (11.0, 15.6), "GP26": (15.0, 15.6),
                 "GP15": (20.0, -4.6)}
    if full:
        for name, p in PICO.items():
            x, y = xy(pico_pin_hole(p))
            lx, ly = label_pos[name]
            ly = ly - 0.6 if ly > 5 else ly
            ax.plot([x, lx], [y, ly - (0.5 if ly > 5 else -0.5)], color="#1b5e3a", lw=0.8, ls=":", zorder=6)
            ax.text(lx, ly, f"{name} (pin {p})", fontsize=8, ha="center", va="center", color="white",
                    zorder=6, weight="bold", bbox=dict(fc="#1b5e3a", ec="none", pad=2))

    # MCP6022
    ax.add_patch(Rectangle((29.55, Y["e"] - 0.25), 3.9, Y["f"] - Y["e"] + 0.5, fc="#222", ec="#000", zorder=3))
    ax.add_patch(plt.Circle((29.75, 5.5), 0.25, fc="#666", zorder=4))
    ax.text(31.5, 5.5, "U1  MCP6022", color="white", fontsize=9 * (k * 0.8 if not full else 1), ha="center",
            va="center", zorder=5)
    for p, h in U1.items():
        x, y = xy(h)
        ax.plot(x, y, "s", ms=5 * k, color="#ccc", zorder=4)
        if not full:
            ax.text(x, y + (0.55 if y < 5 else -0.55), str(p), fontsize=9 * k, ha="center", va="center",
                    zorder=5, color="white", weight="bold")

    def lead(a, b, colour="#888", lw=1.4, z=6):
        ax.plot([a[0], b[0]], [a[1], b[1]], color=colour, lw=lw * (1.4 if not full else 1), zorder=z,
                solid_capstyle="round")
        for p in (a, b):
            ax.plot(*p, "o", ms=3.5 * k, color="#555", zorder=z + 1)

    style = {"R": ("#d9b26f", 0.55), "C": ("#e5a82e", 0.45), "F": ("#c33", 0.6), "E": ("#334", 0.6),
             "D": ("#888", 0.4), "SW": ("#444", 0.8)}
    for name, (kind, label, legs) in PARTS.items():
        (x1, y1), (x2, y2) = xy(legs[0]), xy(legs[1])
        if kind == "D":
            px, py = 31.0, -4.5
            ax.add_patch(plt.Circle((px, py), 0.55, fc="#ccc", ec="#333", zorder=8))
            if full:
                ax.text(px + 0.9, py, "D1 BPW21R (in the box), twisted pair < 10 cm", fontsize=8, va="center")
            else:
                ax.text(px, py - 1.2, "D1 BPW21R (in the box)\ntwisted pair < 10 cm", fontsize=11,
                        ha="center", va="center")
            lead((px - 0.25, py + 0.5), (x1, y1), "#3a3", 1.8)
            lead((px + 0.25, py + 0.5), (x2, y2), "#333", 1.8)
            ax.text(x1 - 0.45, y1 - 0.75, "K", fontsize=9 * k, color="#3a3", weight="bold")
            ax.text(x2 + 0.25, y2 - 0.75, "A", fontsize=9 * k, color="#333", weight="bold")
            continue
        if kind == "SW":
            ax.add_patch(Rectangle((55 - 0.3, Y["e"] - 0.3), 2.6, Y["f"] - Y["e"] + 0.6, fc="#555", ec="#222", zorder=6))
            ax.add_patch(plt.Circle((56, 5.5), 0.7, fc="#222", zorder=7))
            for h in (("e", 55), ("f", 55), ("e", 57), ("f", 57)):
                ax.plot(*xy(h), "s", ms=4, color="#aaa", zorder=7)
            ax.text(56, 1.6, "SW1 mark button\ndiagonal legs in e55 and f57", fontsize=8, ha="center", va="center")
            continue
        colour, width = style[kind]
        lead((x1, y1), (x2, y2))
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        horiz = abs(x2 - x1) >= abs(y2 - y1)
        w, h = (abs(x2 - x1) * 0.55 or 0.5, width) if horiz else (width, abs(y2 - y1) * 0.55 or 0.5)
        ax.add_patch(FancyBboxPatch((mx - w / 2, my - h / 2), w, h, boxstyle="round,pad=0.05",
                                    fc=colour, ec="#333", zorder=8))
        if kind == "E":
            ax.text(x1 + 0.35, y1 + 0.1, "+", fontsize=11 * k, ha="left", va="center", color="#c00",
                    weight="bold", zorder=9)
        if show_label(x1, x2):
            tx, ty = (mx, my + 0.7) if horiz else (mx + 0.6, my)
            if not full and name in LABEL_OFFSET:
                dx, dy = LABEL_OFFSET[name]
                tx, ty = mx + dx, my + dy
            if not full and name in LABEL_AT:
                tx, ty = LABEL_AT[name]
                ax.plot([tx, mx], [ty, my], color="#666", lw=0.8, ls=":", zorder=14)
            ax.text(tx, ty, f"{name} {label}", fontsize=7 * (1 if full else 1.45), ha="center", va="center",
                    zorder=15, bbox=dict(fc="white", ec="#999", alpha=0.95, pad=1.2, lw=0.5))

    colours = {"black": "#222", "red": "#e02020", "orange": "#ff8c00", "purple": "#8a2be2",
               "yellow": "#e6c200", "white": "#ddd"}
    for name, (colour, a, b) in WIRES.items():
        (x1, y1), (x2, y2) = xy(a), xy(b)
        lw = 2.6 * (1.5 if not full else 1)
        ax.plot([x1, x2], [y1, y2], color="#000" if colour == "white" else colours[colour],
                lw=lw + (1.6 if colour == "white" else 0), zorder=11, solid_capstyle="round", alpha=0.95)
        if colour == "white":
            ax.plot([x1, x2], [y1, y2], color="#f8f8f8", lw=lw, zorder=12, solid_capstyle="round")
        # put the wire label on the visible part of the wire
        t = WIRE_LABEL_T.get(name, 0.5)
        if not full and not in_zoom(x1 + (x2 - x1) * t):
            t = 0.8 if in_zoom(x2) else 0.2
        lx, ly = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        if full or in_zoom(lx):
            ax.text(lx, ly, f"{name} {colour}", fontsize=7 * (1 if full else 1.4), ha="center", va="center",
                    zorder=13, bbox=dict(fc="white", ec=colours[colour] if colour != "white" else "#888", pad=0.8))


def hole_name(h):
    col, row = h
    return f"{col} rail (row ~{row})" if col in RAILS else f"{col}{row}"


def wiring_list():
    lines = ["| Step | Part | Value | Leg 1 | Leg 2 |", "|---|---|---|---|---|"]
    step = 0
    lines.append("| 1 | Pico 2 H | | pins 1–20 in **c1–c20**, pins 40–21 in **h1–h20** | USB end at row 1 |")
    lines.append("| 2 | U1 MCP6022 | | pins 1–4 in **e30–e33** (notch/dot towards row 29) | pins 8–5 in **f30–f33** |")
    step = 2
    for name, (kind, label, legs) in PARTS.items():
        step += 1
        a, b = (hole_name(h) for h in legs)
        if kind == "E":
            a, b = f"**+** {a}", f"− {b}"
        if kind == "D":
            a, b = f"cathode → {a}", f"anode → {b}"
        lines.append(f"| {step} | {name} | {label} | {a} | {b} |")
    for name, (colour, a, b) in WIRES.items():
        step += 1
        lines.append(f"| {step} | {name} wire | {colour} | {hole_name(a)} | {hole_name(b)} |")
    return "\n".join(lines)


if __name__ == "__main__":
    errs = check()
    if errs:
        print("LAYOUT DOES NOT MATCH THE SCHEMATIC:")
        print("\n".join(f"  - {e}" for e in errs))
        sys.exit(1)
    print(f"Layout matches the schematic: {len(EXPECTED)} nets, {len(PARTS)} parts, {len(WIRES)} wires.")
    draw()
    print(f"Drawing written to {OUT}/bench_breadboard.png/.svg\n")
    print(wiring_list())
