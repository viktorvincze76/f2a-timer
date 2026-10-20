"""Analyse a bench-test recording: light level, noise floor and model passes.

    python analyze.py recordings/20261012-143000.txt

Answers the questions the sensor design depends on (docs/sensor-design.md §4):
  - photocurrent range  -> is one fixed TIA gain enough?
  - relative noise      -> the simulation assumed 2e-4 per sample at 8 kHz (7.1e-5 after 1 ms smoothing)
  - pass dip and shape  -> the simulation assumed 0.5-0.6 % (15 % contrast), ~5 ms wide
Writes <recording>-overview.png, <recording>-passes.png and <recording>-passes.csv.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FS = 8000.0
SCALE = 3.3 / 4096 / 16  # sum of 16 12-bit readings -> volts


@dataclass
class Recording:
    dc: np.ndarray  # volts
    ac: np.ndarray  # volts
    marks: np.ndarray  # sample positions
    meta: dict
    gaps: int  # status lines that disagreed with the data count (lost USB data)


def load(path: Path) -> Recording:
    data, marks, status, meta = [], [], [], {}
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split()
        if not parts:
            continue
        if line.startswith("##"):
            key, _, value = line[2:].partition(":")
            meta[key.strip()] = value.strip()
        elif parts[0] == "#" and len(parts) == 3:
            status.append((len(data), int(parts[1])))
        elif parts[0] == "M" and len(parts) == 2:
            marks.append(int(parts[1]))
        elif len(parts) == 2:
            try:
                data.append((int(parts[0]), int(parts[1])))
            except ValueError:
                pass
    if not data:
        raise SystemExit(f"{path}: no samples")
    raw = np.array(data, float) * SCALE
    # Device sample index of data position 0, from the first status line
    offset = status[0][1] - status[0][0] if status else 0
    gaps = sum(1 for pos, idx in status if idx - pos != offset)
    marks_pos = np.array([m - offset for m in marks if 0 <= m - offset < len(raw)], int)
    return Recording(raw[:, 0], raw[:, 1], marks_pos, meta, gaps)


def block_median(x: np.ndarray, block: int) -> np.ndarray:
    """Slow baseline: medians of consecutive blocks, interpolated back to every sample."""
    n = len(x) // block
    if n < 2:
        return np.full_like(x, np.median(x))
    med = np.median(x[: n * block].reshape(n, block), axis=1)
    centres = (np.arange(n) + 0.5) * block
    return np.interp(np.arange(len(x)), centres, med)


def moving_average(x: np.ndarray, n: int) -> np.ndarray:
    return np.convolve(x, np.ones(n) / n, mode="same")


@dataclass
class Pass:
    start: int
    end: int
    peak: float  # relative dip
    centroid_s: float
    fwhm_ms: float


def find_passes(rel: np.ndarray, sigma: float, k: float, min_dip: float, max_width_s: float) -> list[Pass]:
    level = max(k * sigma, min_dip)
    above = np.r_[False, rel > level, False]
    edges = np.flatnonzero(np.diff(above.astype(np.int8)))
    passes = []
    for i0, i1 in zip(edges[::2], edges[1::2]):
        if not (0.3e-3 <= (i1 - i0) / FS <= max_width_s):
            continue
        # widen to where the dip falls below 15 % of its peak
        peak_i = i0 + int(np.argmax(rel[i0:i1]))
        peak = rel[peak_i]
        lo, hi = peak_i, peak_i
        while lo > 0 and rel[lo - 1] > 0.15 * peak:
            lo -= 1
        while hi < len(rel) - 1 and rel[hi + 1] > 0.15 * peak:
            hi += 1
        seg = rel[lo : hi + 1] - 0.15 * peak
        centroid = (np.arange(lo, hi + 1) * seg).sum() / seg.sum() / FS
        half = np.flatnonzero(rel[lo : hi + 1] > peak / 2)
        passes.append(Pass(lo, hi, peak, centroid, (half[-1] - half[0] + 1) / FS * 1e3))
    return passes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", type=Path)
    ap.add_argument("--rf", type=float, help="R1 in ohms (default: from the recording header, else 470k)")
    ap.add_argument("--gain", type=float, default=101.0, help="AC stage gain (default 101)")
    ap.add_argument("--vb", type=float, default=0.057, help="TIA bias Vb in volts (default 0.057)")
    ap.add_argument("--k", type=float, default=6.0, help="detection threshold in noise sigmas")
    ap.add_argument("--min-dip", type=float, default=0.0005, help="ignore dips smaller than this (default 0.05 %%)")
    ap.add_argument("--max-width", type=float, default=0.025, help="longest dip counted as a pass, s")
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args()

    rec = load(args.recording)
    rf = args.rf or float(rec.meta.get("rf", 470e3))
    t = np.arange(len(rec.dc)) / FS

    signal = rec.dc - args.vb  # TIA output above its bias: proportional to light
    current_ua = signal / rf * 1e6
    # Fast relative dip from the AC channel: positive = less light
    ac_base = block_median(rec.ac, 400)
    rel = -(rec.ac - ac_base) / (args.gain * np.clip(signal, 1e-3, None))
    rel_s = moving_average(rel, 8)
    mad = lambda x: 1.4826 * np.median(np.abs(x - np.median(x)))  # noqa: E731
    sigma, sigma_s = mad(rel), mad(rel_s)
    passes = find_passes(rel_s, sigma_s, args.k, args.min_dip, args.max_width)

    sat_dc = np.mean(rec.dc > 3.2)
    sat_ac = np.mean((rec.ac > 3.25) | (rec.ac < 0.05))

    print(f"{args.recording.name}: {len(t) / FS:.0f} s, R1 = {rf / 1e3:.0f} kΩ"
          + (f", note: {rec.meta['note']}" if rec.meta.get("note") else ""))
    if rec.gaps:
        print(f"  WARNING: {rec.gaps} status lines disagree with the sample count; data was lost on USB")
    print(f"  Photocurrent: {np.percentile(current_ua, 1):.3f} – {np.percentile(current_ua, 99):.3f} µA "
          f"(TIA output {np.percentile(rec.dc, 1):.3f} – {np.percentile(rec.dc, 99):.3f} V)")
    if sat_dc or sat_ac:
        print(f"  WARNING: saturated {sat_dc:.1%} (DC) / {sat_ac:.1%} (AC) of the time; use a smaller R1")
    # The simulation assumed 2e-4 per sample at 8 kHz, i.e. 7.1e-5 after the same 1 ms smoothing
    print(f"  Noise after 1 ms smoothing: {sigma_s:.2e} relative (simulation assumed 7.1e-05; "
          f"{'better' if sigma_s <= 7.1e-5 else 'WORSE'})")
    print(f"  Passes found: {len(passes)}   marks: {len(rec.marks)}")
    for i, p in enumerate(passes[:30], 1):
        print(f"   {i:3d}  t={p.centroid_s:9.4f} s  dip {p.peak:6.2%}  FWHM {p.fwhm_ms:5.1f} ms")
    if len(passes) > 30:
        print(f"   ... {len(passes) - 30} more in the CSV")
    if passes:
        dips = np.array([p.peak for p in passes])
        print(f"  Dip: median {np.median(dips):.2%}, range {dips.min():.2%} – {dips.max():.2%} "
              f"(simulation: 0.5–0.6 % at 15 % contrast, so contrast here is roughly {np.median(dips) / 0.04:.0%})")

    # Slow passes (model carried by hand) show up in the DC channel only. Baseline:
    # a straight line between the light levels at the two ends of a ±3 s window.
    if len(rec.marks):
        dc_s = moving_average(rec.dc, 400)
        print("  Largest DC dip within ±3 s of each mark (rough; for slow, hand-carried passes):")
        for m in rec.marks:
            a, b = max(0, m - 24000), min(len(rec.dc), m + 24000)
            ends = 4000
            y0, y1 = np.median(signal[a : a + ends]), np.median(signal[b - ends : b])
            base = np.interp(np.arange(a, b), [a + ends / 2, b - ends / 2], [y0, y1])
            print(f"    mark at {m / FS:8.2f} s: {(1 - (dc_s[a:b] - args.vb) / base).max():.2%}")

    stem = args.recording.with_suffix("")
    with open(f"{stem}-passes.csv", "w") as f:
        f.write("centroid_s,peak_dip,fwhm_ms\n")
        for p in passes:
            f.write(f"{p.centroid_s:.6f},{p.peak:.6f},{p.fwhm_ms:.2f}\n")
    if args.no_plots:
        return

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    step = max(1, len(t) // 200_000)
    a1.plot(t[::step], current_ua[::step], lw=0.6)
    a1.set(ylabel="photocurrent (µA)", title=args.recording.name)
    a2.plot(t[::step], rel_s[::step] * 100, lw=0.4)
    for p in passes:
        a2.plot(p.centroid_s, p.peak * 100, "rv", ms=4)
    for m in rec.marks:
        for a in (a1, a2):
            a.axvline(m / FS, color="g", alpha=0.4)
    a2.set(xlabel="time (s)", ylabel="fast dip (%)")
    for a in (a1, a2):
        a.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{stem}-overview.png", dpi=110)

    if passes:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for p in passes[:40]:
            c = int(p.centroid_s * FS)
            w = np.arange(max(0, c - 160), min(len(rel), c + 160))
            ax.plot((w / FS - p.centroid_s) * 1e3, rel[w] * 100, lw=0.8, alpha=0.7)
        ax.set(xlabel="time from centroid (ms)", ylabel="dip (%)",
               title=f"{min(len(passes), 40)} passes, aligned at their centroids")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(f"{stem}-passes.png", dpi=110)
    print(f"  Plots and CSV written next to {args.recording.name}")


if __name__ == "__main__":
    main()
