"""Command-line timer: shows laps and speeds live and writes a raw log."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .protocol import HANDLE, SENSOR, Edge, Heartbeat, Hello, parse_line, pulse_command
from .timing import F2A_LAP_M, LapTimer


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="f2a-timer", description=__doc__)
    ap.add_argument("--port", help="serial port (default: auto-detect the Pico)")
    ap.add_argument("--sim", action="store_true", help="use the built-in simulator instead of hardware")
    ap.add_argument("--fast", action="store_true", help="with --sim: don't wait in real time")
    ap.add_argument("--test-pulses", type=int, metavar="PERIOD_MS",
                    help="make the device emit test pulses on its test pin (0 = off)")
    ap.add_argument("--lap-m", type=float, default=F2A_LAP_M, help="lap length in metres (default: F2A, 1000/9)")
    ap.add_argument("--timed-laps", type=int, default=9, help="laps in the timed run (default: 9)")
    ap.add_argument("--log-dir", type=Path, default=Path("logs"), help="where raw logs go (default: ./logs)")
    args = ap.parse_args(argv)

    if args.sim:
        from .simulator import SimulatedDevice
        device = SimulatedDevice(realtime=not args.fast)
    else:
        from .device import SerialDevice
        try:
            device = SerialDevice(args.port)
        except Exception as e:  # missing pyserial, no device, permissions...
            print(f"error: {e}", file=sys.stderr)
            return 1

    if args.test_pulses is not None:
        device.send(pulse_command(args.test_pulses))

    args.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.log_dir / f"{datetime.now():%Y%m%d-%H%M%S}.log"
    print(f"Connected to {device.port}, logging raw data to {log_path}. Ctrl+C to stop.")

    timer = LapTimer(lap_m=args.lap_m)
    last_seq: int | None = None
    try:
        with log_path.open("w") as log:
            for line in device.lines():
                log.write(line + "\n")
                log.flush()
                msg = parse_line(line)
                match msg:
                    case Hello(version):
                        print(f"Device firmware {version}")
                    case Heartbeat(dropped=dropped) if dropped:
                        print(f"WARNING: device dropped {dropped} events (queue full)")
                    case Edge(seq=seq):
                        if last_seq is not None and seq != last_seq + 1:
                            print(f"WARNING: {seq - last_seq - 1} events missing before #{seq}")
                        last_seq = seq
                        report(timer, msg, args.timed_laps)
    except KeyboardInterrupt:
        pass
    finally:
        device.close()

    summary(timer, args.timed_laps)
    return 0


def report(timer: LapTimer, edge: Edge, timed_laps: int) -> None:
    t = edge.t_us / 1e6
    if edge.channel == HANDLE:
        print(f"{t:12.6f}  handle {'IN pylon' if edge.active else 'released'}")
        return
    if edge.channel != SENSOR or not edge.active:
        return
    first = not timer.passes_us
    lap = timer.add_pass(edge.t_us)
    if lap:
        note = "  WARNING: missed lap? (time doubled)" if lap.suspect_missed else ""
        print(f"{t:12.6f}  lap {lap.number:2d}  {lap.time_us / 1e6:8.4f} s  "
              f"{lap.speed_kmh(timer.lap_m):7.2f} km/h{note}")
    if first:
        print(f"{t:12.6f}  first pass")
    elif timer.rejected_us and timer.rejected_us[-1] == edge.t_us:
        print(f"{t:12.6f}  stray pulse ignored")


def summary(timer: LapTimer, timed_laps: int) -> None:
    n = len(timer.laps)
    print(f"\n{n} laps, {len(timer.rejected_us)} stray pulses ignored")
    if n < timed_laps:
        return
    runs = [(timer.speed_over(i, timed_laps), i) for i in range(1, n - timed_laps + 2)]
    speed, first = max(runs)
    print(f"Best {timed_laps}-lap speed: {speed:.2f} km/h (laps {first}-{first + timed_laps - 1})")


if __name__ == "__main__":
    sys.exit(main())
