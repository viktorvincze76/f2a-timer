"""Signal model for the slit-type optical pass sensor.

Answers the first design questions for the new sensor before any hardware
exists: how large and how long is the light dip a passing F2A model makes,
how does it change with flying height, and how precisely can a pass be
timestamped from a sampled signal (fixed threshold vs constant fraction).

Units: metres, seconds, degrees unless noted. Coordinates: origin at the
sensor slit, x towards the pylon, y along the flight direction at the
crossing point, z up. Path curvature over the ~1 m seen by the sensor is
ignored (sagitta < 10 mm).

Run:  python signal_model.py            (writes plots to docs/img)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.signal import lfilter

DEG = np.pi / 180


@dataclass(frozen=True)
class Sensor:
    radius: float = 21.5  # distance from the pylon centre
    slit_height: float = 0.15  # above ground
    elev_min: float = 9.0
    elev_max: float = 50.0
    fwhm: float = 4.0  # horizontal field of view, full width at half maximum
    edge: float = 0.6  # width of each flank of the horizontal response
    roll: float = 0.0  # sideways tilt, i.e. levelling error

    def response(self, phi, elev):
        flank = np.clip((self.fwhm / 2 + self.edge / 2 - np.abs(phi)) / self.edge, 0, 1)
        return flank * ((elev >= self.elev_min) & (elev <= self.elev_max))

    def field_solid_angle(self) -> float:
        return self.fwhm * DEG * (np.sin(self.elev_max * DEG) - np.sin(self.elev_min * DEG))


@dataclass(frozen=True)
class Model:
    """A typical F2A speed model. All dimensions are assumptions; adjust to real models."""

    path_radius: float = 17.69  # 9 laps = 1 km
    speed_kmh: float = 300.0
    fuse_len: float = 0.55
    fuse_height: float = 0.06
    fuse_width: float = 0.045
    wing_span: float = 0.30  # mono-wing, inboard (towards the pylon)
    wing_chord: float = 0.09
    wing_thick: float = 0.010
    wing_pos: float = 0.03  # wing centre ahead of the fuselage centre
    tail_span: float = 0.14
    tail_chord: float = 0.05
    tail_pos: float = -0.22
    line_dia: float = 0.0004
    lines: int = 1
    handle_height: float = 1.2  # where the line meets the pylon
    # 1 = model black against the sky. 0.15 reproduces the ~0.5 % dip measured on
    # the original sensor (models reflect light and are seen against bright sky).
    contrast: float = 0.15

    @property
    def speed(self) -> float:
        return self.speed_kmh / 3.6


def box_facets(center, size, step=0.005):
    """Sample the six faces of a box as (points, areas, outward normals)."""
    c, s = np.asarray(center, float), np.asarray(size, float)
    pts, areas, normals = [], [], []
    for axis in range(3):
        u, v = (a for a in range(3) if a != axis)
        nu, nv = max(1, int(np.ceil(s[u] / step))), max(1, int(np.ceil(s[v] / step)))
        gu = ((np.arange(nu) + 0.5) / nu - 0.5) * s[u]
        gv = ((np.arange(nv) + 0.5) / nv - 0.5) * s[v]
        U, V = (g.ravel() for g in np.meshgrid(gu, gv, indexing="ij"))
        for sign in (-1, 1):
            p = np.zeros((U.size, 3))
            p[:, u], p[:, v], p[:, axis] = U, V, sign * s[axis] / 2
            n = np.zeros((U.size, 3))
            n[:, axis] = sign
            pts.append(c + p)
            areas.append(np.full(U.size, s[u] * s[v] / U.size))
            normals.append(n)
    return np.concatenate(pts), np.concatenate(areas), np.concatenate(normals)


def model_bodies(sensor: Sensor, model: Model, height: float):
    xm, zm = sensor.radius - model.path_radius, height - sensor.slit_height
    m = model
    return {
        "fuselage": box_facets((xm, 0, zm), (m.fuse_width, m.fuse_len, m.fuse_height)),
        "wing": box_facets((xm + m.fuse_width / 2 + m.wing_span / 2, m.wing_pos, zm),
                           (m.wing_span, m.wing_chord, m.wing_thick)),
        "tail": box_facets((xm, m.tail_pos, zm), (m.tail_span, m.tail_chord, m.wing_thick / 2)),
    }


def _angles(sensor: Sensor, P):
    """Horizontal angle and elevation of points P (..., 3) in the sensor frame."""
    c, s = np.cos(sensor.roll * DEG), np.sin(sensor.roll * DEG)
    x, y, z = P[..., 0], c * P[..., 1] + s * P[..., 2], -s * P[..., 1] + c * P[..., 2]
    return np.arctan2(y, x) / DEG, np.arctan2(z, np.hypot(x, y)) / DEG


def dip_components(sensor: Sensor, model: Model, height: float, t: np.ndarray):
    """Fractional light drop per model part at times t (t=0: fuselage centre on the sensor axis)."""
    t = np.atleast_1d(np.asarray(t, float))
    omega = sensor.field_solid_angle()
    shift = np.zeros((t.size, 1, 3))
    shift[:, 0, 1] = model.speed * t
    out = {}

    for name, (p, a, n) in model_bodies(sensor, model, height).items():
        total = np.empty(t.size)
        for i in range(0, t.size, 200):  # chunk to bound memory
            P = p[None] + shift[i : i + 200]
            r = np.linalg.norm(P, axis=-1)
            facing = np.clip(-(P * n[None]).sum(-1) / r, 0, None)  # only faces towards the sensor
            total[i : i + 200] = (a * facing / r**2 * sensor.response(*_angles(sensor, P))).sum(-1)
        out[name] = total / omega

    # Control line(s): thin cylinder from the wing tip to the pylon handle
    xm, zm = sensor.radius - model.path_radius, height - sensor.slit_height
    k = 800
    s = (np.arange(k) + 0.5) / k
    A = np.stack([np.full(t.size, xm + model.fuse_width / 2 + model.wing_span),
                  model.speed * t + model.wing_pos, np.full(t.size, zm)], -1)
    B = np.array([sensor.radius, 0.0, model.handle_height - sensor.slit_height])
    P = A[:, None] + s[None, :, None] * (B - A)[:, None]
    seg = np.linalg.norm(B - A, axis=-1)
    d = (B - A) / seg[:, None]
    r = np.linalg.norm(P, axis=-1)
    sin_view = np.linalg.norm(np.cross(d[:, None], P / r[..., None]), axis=-1)
    w = model.line_dia * (seg / k)[:, None] * sin_view / r**2
    out["line"] = model.lines * (w * sensor.response(*_angles(sensor, P))).sum(-1) / omega

    return {k: v * model.contrast for k, v in out.items()}


@lru_cache(maxsize=None)
def dip_waveform(sensor: Sensor, model: Model, height: float, dt=5e-6, span=0.02):
    """Total dip on a fine time grid (cached), for interpolation at sample times."""
    t = np.arange(-span, span, dt)
    return t, sum(dip_components(sensor, model, height, t).values())


# ---- detection (prototype of the firmware algorithm) ------------------------


@dataclass(frozen=True)
class Detector:
    fs: float = 8000.0  # ADC sample rate
    baseline_tau: float = 0.1  # sky-level tracking time constant
    guard: float = 0.02  # baseline taken from this long before the current sample
    smooth: int = 8  # moving average length (samples), a simple low-pass
    trigger_sigma: float = 6.0  # trigger at this many noise sigmas
    max_width: float = 0.025  # longer dips are sky changes, not models
    # (label, kind, level or fraction of peak). "mid" = midpoint of the leading and
    # trailing crossings, "centroid" = centre of mass of the pulse above the fraction.
    methods: tuple = (("leading edge, fixed 0.1 %", "fixed", 0.001),
                      ("leading edge, 15 % of peak", "cfd", 0.15),
                      ("leading edge, 50 % of peak", "cfd", 0.50),
                      ("midpoint at 50 % of peak", "mid", 0.50),
                      ("centroid above 15 % of peak", "centroid", 0.15))

    def normalised_dip(self, light):
        """Relative dip vs a ramp-tracking sky baseline (Brown's double exponential smoothing)."""
        a = 1 - np.exp(-1 / (self.fs * self.baseline_tau))
        s1 = lfilter([a], [1, a - 1], light, zi=[(1 - a) * light[0]])[0]
        s2 = lfilter([a], [1, a - 1], s1, zi=[(1 - a) * light[0]])[0]
        level, trend = 2 * s1 - s2, a / (1 - a) * (s1 - s2)
        g = int(self.guard * self.fs)
        base = np.empty_like(light)
        base[g:] = level[:-g] + g * trend[:-g]
        base[:g] = light[0]
        sm = lfilter(np.ones(self.smooth) / self.smooth, [1], light, zi=np.full(self.smooth - 1, light[0]))[0]
        y = 1 - sm / base
        y[: int((3 * self.baseline_tau + self.guard) * self.fs)] = 0  # baseline still settling
        return y

    def detect(self, t, light, noise):
        """Time of the first model-like dip for each method in ``methods`` (None if not found)."""
        y = self.normalised_dip(light)
        sigma = noise / np.sqrt(self.smooth)
        above = y > self.trigger_sigma * sigma
        # contiguous runs above the trigger level; keep the first short enough to be a model
        edges = np.flatnonzero(np.diff(above.astype(np.int8)))
        starts, ends = edges[::2] + 1, edges[1::2] + 1
        if above[0]:
            starts = np.r_[0, starts]
        for i0, i1 in zip(starts, ends):
            if (i1 - i0) / self.fs <= self.max_width:
                break
        else:
            return [None] * len(self.methods)
        peak_i = i0 + int(np.argmax(y[i0:i1]))
        peak = y[peak_i]

        def leading(level):
            # last sample below `level` before the peak, then interpolate
            below = np.flatnonzero(y[: peak_i + 1] < level)
            if not below.size or level >= peak:
                return None
            j = below[-1]
            return t[j] + (level - y[j]) / (y[j + 1] - y[j]) * (t[j + 1] - t[j])

        def trailing(level):
            below = np.flatnonzero(y[peak_i:] < level)
            if not below.size or level >= peak:
                return None
            j = peak_i + below[0]
            return t[j - 1] + (y[j - 1] - level) / (y[j - 1] - y[j]) * (t[j] - t[j - 1])

        def centroid(level):
            a = leading(level)
            b = trailing(level)
            if a is None or b is None:
                return None
            sel = (t >= a) & (t <= b)
            w = y[sel] - level
            return (t[sel] * w).sum() / w.sum()

        def measure(kind, v):
            if kind == "fixed":
                return leading(v)
            if kind == "cfd":
                return leading(v * peak)
            if kind == "mid":
                a, b = leading(v * peak), trailing(v * peak)
                return None if a is None or b is None else (a + b) / 2
            return centroid(v * peak)

        return [measure(kind, v) for _, kind, v in self.methods]


def simulate_pass(sensor, model, det, height, noise, rng, drift=0.0):
    """ADC samples around one pass: random sample phase, white noise and a sky brightness ramp."""
    tw, dw = dip_waveform(sensor, model, height)
    t = np.arange(-0.6, 0.05, 1 / det.fs) + rng.uniform(0, 1 / det.fs)
    light = (1 + drift * t) * (1 - np.interp(t, tw, dw, left=0, right=0))
    return t, light + rng.normal(0, noise, t.size)


# ---- report ------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "docs" / "img")
    ap.add_argument("--noise", type=float, default=2e-4, help="relative noise per sample (default 0.02 %%)")
    ap.add_argument("--drift", type=float, default=0.05, help="sky brightness ramp per second (default 5 %%/s)")
    ap.add_argument("--contrast", type=float, default=Model.contrast)
    ap.add_argument("--trials", type=int, default=200)
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sensor, model, det = Sensor(), Model(contrast=args.contrast), Detector()
    rng = np.random.default_rng(1)
    heights = np.round(np.arange(0.6, 4.21, 0.2), 2)
    args.out.mkdir(parents=True, exist_ok=True)

    # 1. Peak dip by part vs height
    peaks = {}
    for h in heights:
        t = np.linspace(-0.006, 0.006, 241)
        comps = dip_components(sensor, model, h, t)
        total = sum(comps.values())
        for k, v in comps.items():
            peaks.setdefault(k, []).append(v.max() * 100)
        peaks.setdefault("total", []).append(total.max() * 100)
    fig, ax = plt.subplots(figsize=(7, 4))
    for k, v in peaks.items():
        ax.plot(heights, v, lw=2.5 if k == "total" else 1.2, label=k)
    ax.set(xlabel="flying height (m)", ylabel="peak light dip (%)", title="Peak dip vs flying height")
    ax.grid(alpha=0.3); ax.legend()
    fig.tight_layout(); fig.savefig(args.out / "dip_vs_height.png", dpi=130)

    # 2. Pulse shapes
    fig, ax = plt.subplots(figsize=(7, 4))
    for h in (0.8, 1.5, 2.5, 3.5):
        tw, dw = dip_waveform(sensor, model, h)
        ax.plot(tw * 1e3, dw * 100, label=f"{h} m")
    ax.set(xlim=(-10, 10), xlabel="time from crossing (ms)", ylabel="light dip (%)",
           title=f"Pulse shape at {model.speed_kmh:.0f} km/h")
    ax.grid(alpha=0.3); ax.legend(title="height")
    fig.tight_layout(); fig.savefig(args.out / "pulse_shapes.png", dpi=130)

    # 3. Timing offset vs height for each detection method
    stats = {label: ([], []) for label, *_ in det.methods}
    misses = dict.fromkeys(stats, 0)
    for h in heights:
        res = {label: [] for label in stats}
        for _ in range(args.trials):
            t, light = simulate_pass(sensor, model, det, h, args.noise, rng, args.drift)
            for label, v in zip(stats, det.detect(t, light, args.noise)):
                if v is None:
                    misses[label] += 1
                else:
                    res[label].append(v)
        for label in stats:
            r = np.array(res[label]) * 1e6
            stats[label][0].append(r.mean() if r.size else np.nan)
            stats[label][1].append(r.std() if r.size else np.nan)

    fig, ax = plt.subplots(figsize=(7, 4))
    for label, (m, s) in stats.items():
        m, s = np.array(m), np.array(s)
        ax.plot(heights, m, label=label)
        ax.fill_between(heights, m - s, m + s, alpha=0.25)
    ax.set(xlabel="flying height (m)", ylabel="detected time - true crossing (µs)",
           title="Timing walk with height (band = ±1σ noise jitter)")
    ax.grid(alpha=0.3); ax.legend()
    fig.tight_layout(); fig.savefig(args.out / "timing_walk.png", dpi=130)

    # 4. Levelling error: pulse-peak time vs height for a sideways-tilted sensor
    tilt = {}
    for roll in (0.0, 1.0, 3.0):
        s_roll = replace(sensor, roll=roll)
        tilt[roll] = []
        for h in heights:
            tw, dw = dip_waveform(s_roll, model, h)
            tilt[roll].append(tw[np.argmax(dw)] * 1e6)

    # Summary
    def span(vals, lo=1.0, hi=3.0):
        v = np.array(vals)[(heights >= lo) & (heights <= hi)]
        return np.nanmax(v) - np.nanmin(v)

    flyable = (heights >= 1.0) & (heights <= 3.0)

    pulse_t, pulse = dip_waveform(sensor, model, 2.0)
    above = pulse_t[pulse > pulse.max() / 2]
    print(f"Model {model.speed_kmh:.0f} km/h, sensor field {sensor.fwhm}° x {sensor.elev_min}-{sensor.elev_max}°, "
          f"contrast {model.contrast:.0%}, noise {args.noise:.3%}/sample @ {det.fs:.0f} Hz, "
          f"sky drift {args.drift:.0%}/s\n")
    print("Peak dip (%) by height:")
    for h in (0.6, 1.0, 2.0, 3.0, 4.0):
        i = int(np.argmin(np.abs(heights - h)))
        parts = ", ".join(f"{k} {peaks[k][i]:.2f}" for k in peaks if k != "total")
        print(f"  {h:.1f} m: total {peaks['total'][i]:.2f}   ({parts})")
    print(f"\nPulse width at half maximum, 2 m: {(above[-1] - above[0]) * 1e3:.1f} ms")
    print(f"\nTiming, flying height 1-3 m ({args.trials} simulated passes per height):")
    for label, (m, s) in stats.items():
        print(f"  {label:24s} walk {span(m):5.0f} µs, jitter σ {np.nanmean(np.array(s)[flyable]):4.0f} µs, "
              f"missed {misses[label]} of {len(heights) * args.trials} (all heights)")
    for roll, v in tilt.items():
        print(f"  peak-time walk with {roll:.0f}° levelling error: {span(v):5.0f} µs")
    print(f"\nPlots written to {args.out}")


if __name__ == "__main__":
    main()
