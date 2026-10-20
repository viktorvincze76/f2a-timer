"""Draws the bench-test front end schematic to docs/img/bench_schematic.svg/.png.

Run with the sensor/sim environment:  ../sim/.venv/bin/python schematic.py
"""

from pathlib import Path

import schemdraw
import schemdraw.elements as elm

OUT = Path(__file__).resolve().parents[2] / "docs" / "img"


def draw():
    schemdraw.config(fontsize=11)
    d = schemdraw.Drawing(show=False)

    # ---- ① transimpedance amplifier: photocurrent -> voltage -----------------
    d += elm.Label().at((-3.0, 3.9)).label("① TIA: light → voltage", halign="left", fontsize=12)
    op1 = d.add(elm.Opamp(leads=True).at((0, 0)).anchor("in1")
                .label("U1A\nMCP6022", loc="center", ofst=(-0.3, 0), fontsize=9))
    d += elm.Line().at(op1.in1).left(0.8).dot()
    n_in = d.here
    d += elm.Line().left(0.9)
    d += elm.Photodiode().down(2.0).reverse().label("D1 BPW21R\n(cathode up)", loc="top")
    d += elm.Ground()
    out_x = 4.0
    d += elm.Line().at(op1.out).right(out_x - op1.out[0]).dot()
    n_out = d.here
    d += elm.Line().at(n_in).up(1.5)
    d += elm.Resistor().right(out_x - n_in[0]).label("R1 470k  (1M on dull days)")
    d += elm.Line().down(1.5 - op1.out[1])
    d += elm.Line().at((n_in[0], 1.5)).up(1.4)
    d += elm.Capacitor().right(out_x - n_in[0]).label("C1 22p C0G")
    d += elm.Line().down(1.4)
    d += elm.Line().at((op1.in2[0] - 0.4, op1.in2[1])).to(op1.in2)
    d += elm.Line().at((op1.in2[0] - 0.4, op1.in2[1])).down(0.9)
    d += elm.Dot(open=True).label("Vb", loc="bottom")

    # DC level -> ADC0
    d += elm.Resistor().at(n_out).right(2.5).label("R2 1k")
    d += elm.Dot()
    n = d.here
    d += elm.Line().right(0.8)
    d += elm.Dot(open=True).label("GP26 / ADC0  (DC level)", loc="right")
    d += elm.Capacitor().at(n).down(1.5).label("C2 10n", loc="bottom")
    d += elm.Ground()

    # ---- ② AC gain x101 ------------------------------------------------------
    d += elm.Label().at((-3.0, -6.6)).label("② AC gain ×101, 3–1600 Hz", halign="left", fontsize=12)
    d += elm.Capacitor().at(n_out).down(2.5).label("C3 1µ film", loc="bottom")
    d += elm.Line().down(5.0 - 0.62 - 2.5)
    d += elm.Dot()
    n_hp = d.here
    d += elm.Resistor().left(2.5).label("R3 100k")
    d += elm.Dot(open=True).label("Vmid", loc="left")
    op2 = d.add(elm.Opamp(leads=True).flip().right().at((n_hp[0] + 2.0, n_hp[1])).anchor("in2")
                .label("U1B", loc="center", ofst=(-0.3, 0), fontsize=9))
    d += elm.Line().at(n_hp).to(op2.in2)
    d += elm.Line().at(op2.in1).left(0.6).dot()
    n_in2 = d.here
    fb_x = op2.out[0] + 0.6
    d += elm.Line().at(op2.out).right(0.6).dot()
    n_out2 = d.here
    d += elm.Line().at(n_in2).down(1.3)
    d += elm.Resistor().right(fb_x - n_in2[0]).label("R6 100k", loc="bottom")
    d += elm.Line().up(n_out2[1] - d.here[1])
    d += elm.Line().at((n_in2[0], n_in2[1] - 1.3)).down(1.3)
    d += elm.Capacitor().right(fb_x - n_in2[0]).label("C5 1n C0G", loc="bottom")
    d += elm.Line().up(1.3)
    d += elm.Line().at((n_in2[0], n_in2[1] - 2.6)).down(0.4)
    d += elm.Resistor().down(1.6).label("R7 1k")
    d += elm.Capacitor(polar=True).down(1.6).label("C6 47µ")
    d += elm.Ground()

    # AC signal -> ADC1
    d += elm.Resistor().at(n_out2).right(2.5).label("R8 1k")
    d += elm.Dot()
    n = d.here
    d += elm.Line().right(0.8)
    d += elm.Dot(open=True).label("GP27 / ADC1  (AC signal)", loc="right")
    d += elm.Capacitor().at(n).down(1.5).label("C7 10n", loc="bottom")
    d += elm.Ground()

    # ---- ③ supply and references --------------------------------------------
    x0, y0 = -1.0, -15.0
    d += elm.Label().at((-3.0, y0 + 1.5)).label("③ Supply and references   (all grounds = AGND, Pico pin 33)",
                                               halign="left", fontsize=12)
    d += elm.Dot(open=True).at((x0, y0)).label("3V3 (Pico pin 36)", loc="left")
    d += elm.Resistor().at((x0, y0)).right(2.5).label("R10 10Ω")
    d += elm.Dot()
    n_va = d.here
    d += elm.Capacitor(polar=True).down(1.5).label("C10 100µ", loc="bottom")
    d += elm.Ground()
    d += elm.Line().at(n_va).right(2.5).dot()
    n = d.here
    d += elm.Capacitor().down(1.5).label("C11 100n", loc="bottom")
    d += elm.Ground()
    d += elm.Line().at(n).right(1.0)
    d += elm.Label().label("+VA → U1 pin 8   (U1 pin 4 → AGND)", loc="right", halign="left")

    def divider(x, top, bottom, cap, out_label):
        y = y0 - 3.6
        d.add(elm.Dot(open=True).at((x, y)).label("+VA", loc="top"))
        d.add(elm.Resistor().at((x, y)).down(1.6).label(top))
        n = d.add(elm.Dot()).center
        d.add(elm.Resistor().down(1.6).label(bottom))
        d.add(elm.Ground())
        d.add(elm.Line().at(n).right(1.8).dot())
        m = d.here
        d.add(elm.Capacitor().down(1.6).label(cap, loc="bottom"))
        d.add(elm.Ground())
        d.add(elm.Line().at(m).right(0.8))
        d.add(elm.Label().label(out_label, loc="right", halign="left"))

    divider(x0 - 1.0, "R11 56k", "R12 1k", "C12 100n", "Vb ≈ 57 mV  → U1 pin 3")
    divider(x0 + 7.5, "R4 100k", "R5 100k", "C4 10µ", "Vmid 1.65 V → R3")

    # ---- Pico extras ----------------------------------------------------------
    xb, yb = x0 + 16.0, y0 - 3.6
    d += elm.Label().at((xb - 1.5, yb + 0.8)).label("Mark button", halign="left")
    d += elm.Dot(open=True).at((xb, yb)).label("GP15", loc="left")
    d += elm.Button().at((xb, yb)).right(1.6)
    d += elm.Ground()
    d += elm.Label().at((xb - 1.5, yb - 2.2)).label(
        "The firmware drives GP23 high\n(quiet mode for the Pico's own\n3.3 V regulator).", halign="left", fontsize=9)

    d.save(str(OUT / "bench_schematic.svg"))
    d.save(str(OUT / "bench_schematic.png"), dpi=110)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    draw()
    print(f"written to {OUT}")
