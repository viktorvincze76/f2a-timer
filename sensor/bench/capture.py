"""Record the bench-test front end to a file, with a live status line.

    python capture.py --note "overcast, white model, R1=470k"

Writes recordings/<date-time>.txt: the raw stream from the Pico, preceded by
'## key: value' header lines. Analyse it afterwards with analyze.py.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

PICO_USB_VID = 0x2E8A
SCALE = 3.3 / 4096 / 16  # sum of 16 12-bit readings -> volts


def find_port() -> str:
    from serial.tools import list_ports

    ports = [p.device for p in list_ports.comports() if p.vid == PICO_USB_VID]
    if len(ports) != 1:
        sys.exit(f"Found {len(ports)} Picos on USB; pick one with --port")
    return ports[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port")
    ap.add_argument("--minutes", type=float, default=0, help="stop after this long (default: Ctrl+C)")
    ap.add_argument("--note", default="", help="conditions: sky, model, location, R1 value...")
    ap.add_argument("--rf", type=float, default=470e3, help="R1 in ohms (default 470k)")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "recordings")
    args = ap.parse_args()

    import serial

    port = args.port or find_port()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{datetime.now():%Y%m%d-%H%M%S}.txt"
    end = time.monotonic() + args.minutes * 60 if args.minutes else float("inf")

    with serial.Serial(port, 115200, timeout=1) as ser, path.open("w") as f:
        f.write(f"## started: {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"## rf: {args.rf:g}\n## note: {args.note}\n")
        print(f"Recording {port} -> {path}  (Ctrl+C to stop)")
        ser.reset_input_buffer()
        dc_last = ac_min = ac_max = None
        marks = 0
        try:
            while time.monotonic() < end:
                line = ser.readline().decode("ascii", errors="replace")
                if not line:
                    continue
                f.write(line)
                parts = line.split()
                if len(parts) == 2 and parts[0].isdigit():
                    dc, ac = int(parts[0]) * SCALE, int(parts[1]) * SCALE
                    dc_last = dc
                    ac_min = ac if ac_min is None else min(ac_min, ac)
                    ac_max = ac if ac_max is None else max(ac_max, ac)
                elif parts and parts[0] == "M":
                    marks += 1
                    print(f"\n  mark {marks}")
                elif parts and parts[0] == "#" and dc_last is not None:
                    current = (dc_last - 0.057) / args.rf * 1e6
                    warn = "  SATURATED" if dc_last > 3.2 or ac_max > 3.25 or ac_min < 0.05 else ""
                    print(f"\r  t={int(parts[1]) / 8000:7.0f} s  DC {dc_last:5.3f} V ({current:5.2f} µA)  "
                          f"AC {ac_min:5.3f}-{ac_max:5.3f} V  overruns {parts[2]}{warn}   ", end="", flush=True)
                    ac_min = ac_max = None
        except KeyboardInterrupt:
            pass
    print(f"\nSaved {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
