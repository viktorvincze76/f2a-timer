"""Make a synthetic recording with known passes, to check analyze.py end to end.

Passes from the signal model are fed through a model of the bench front end
(TIA, AC stage with its high- and low-pass corners, 12-bit ADC with 16x
oversampling) and written in the Pico's output format.

    python make_test_recording.py && python analyze.py recordings/synthetic.txt
"""

import sys
from pathlib import Path

import numpy as np
from scipy.signal import bilinear, lfilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sim"))
from signal_model import Model, Sensor, dip_waveform  # noqa: E402

FS = 8000
RF, VB, VMID, GAIN = 470e3, 0.057, 1.65, 101.0
LSB = 3.3 / 4096


def first_order(kind, f, x):
    w = 2 * np.pi * f
    b, a = ([1, 0], [1, w]) if kind == "high" else ([w], [1, w])
    bz, az = bilinear(b, a, FS)
    return lfilter(bz, az, x)


def main(seconds=60, current_ua=1.0, noise=1.5e-4, seed=3):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * FS)) / FS
    light = current_ua * (1 + 0.1 * np.sin(2 * np.pi * t / 120))  # slow cloud variation

    sensor, model = Sensor(), Model()
    truth = []
    for k, tc in enumerate(np.arange(5, seconds - 15, 1.6)):
        h = rng.uniform(1.0, 3.0)
        tw, dw = dip_waveform(sensor, model, round(h, 1))
        light *= 1 - np.interp(t - tc, tw, dw, left=0, right=0)
        truth.append(dw.max())
    # a slow, hand-carried pass: 1 % for ~0.3 s at t = seconds - 8
    tm = seconds - 8
    light *= 1 - 0.01 * np.exp(-0.5 * ((t - tm) / 0.1) ** 2)
    light *= 1 + rng.normal(0, noise, t.size)

    tia = VB + light * 1e-6 * RF
    ac = VMID + GAIN * first_order("low", 1600, first_order("high", 3.4, first_order("high", 1.6, tia - tia[0])))

    def adc_sum(v):
        return np.round(np.clip(v, 0, 3.3) / LSB * 16 + rng.normal(0, 4, v.size)).astype(int)

    out = Path(__file__).parent / "recordings" / "synthetic.txt"
    out.parent.mkdir(exist_ok=True)
    dc_s, ac_s = adc_sum(tia), adc_sum(ac)
    with out.open("w") as f:
        f.write(f"## rf: {RF:g}\n## note: synthetic, {len(truth)} passes, {current_ua} µA, noise {noise:g}\n")
        for i in range(t.size):
            f.write(f"{dc_s[i]} {ac_s[i]}\n")
            if (i + 1) % FS == 0:
                f.write(f"# {i + 1} 0\n")
            if i == int((tm - 1) * FS):
                f.write(f"M {i + 1}\n")
    print(f"{out}: {len(truth)} passes, true peak dip median {np.median(truth):.2%} "
          f"({min(truth):.2%} – {max(truth):.2%}), noise {noise:g}, slow pass 1.00 % at {tm} s")


if __name__ == "__main__":
    main()
