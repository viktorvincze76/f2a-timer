# F2A optical lap timer: modernized

A club rebuild of an optical speed-timing system for control-line speed models (F2A).
The original design dates from 2000. Its proven optical sensor is kept; the
MS-DOS + parallel-port timing chain is replaced.

## Fixing the main weakness of the old design

The old program timestamped sensor pulses **on the PC** by polling the printer port.
Any pause by the OS meant a wrong or missed lap, so it only worked under bare
MS-DOS. Moving to Linux would not fix this, since Linux is not real-time either.

The new design moves the timestamp into a microcontroller:

```
 sensor ──76 m cable──► Raspberry Pi Pico ──USB──► Linux PC (Python)
                        timestamps each edge        counts laps, speeds,
                        in a high-priority IRQ      logs, user interface
                        (1 µs, 64-bit clock)
```

The timestamp is fixed within about 1 µs of the edge (the interrupt handler runs from RAM
and takes the clock reading first). The PC can be seconds late, or briefly unplugged, and the
lap times are unaffected: events are queued and numbered, and a gap in the numbering is reported.

| | Old | New |
|---|---|---|
| Timestamp taken by | PC, polling the port | Pico, hardware interrupt |
| Resolution | 42 µs – 3 ms (depends on the PC) | 1 µs, independent of the PC |
| OS | MS-DOS boot floppy only | Any Linux / macOS / Windows |
| Connection | Parallel port | USB |
| Clock accuracy | PC crystal, < 100 ppm | Pico crystal, about 30 ppm (≈ 0.01 km/h at 300 km/h); GPS calibration planned |

## Layout

- `firmware/`: Pico firmware (C, Pico SDK)
- `host/`: Python host software (`f2atimer` package, CLI, simulator, tests)
- `docs/protocol.md`: the USB line protocol
- `docs/hardware.md`: wiring, and the protected sensor input stage
- `docs/sensor-design.md`: **the new optical sensor**: requirements, simulation results, architecture
- `sensor/sim/`: optical and signal model of the sensor (`python signal_model.py`)
- `docs/bench-test.md`: **breadboard test rig** to measure real sky and model signals (circuit, parts, procedure)
- `docs/pcb-plan.md`: **final system PCBs** (sensor head SH-1, base station BS-1), parts list with order links
- `hardware/*/bom.csv`: parts lists per board, ready for Mouser / DigiKey / LCSC BOM upload
- `sensor/bench/`: capture and analysis scripts for the bench test; `firmware/bench_capture/` is its Pico firmware
- `docs/legacy-software.md`: what the old DOS program (Transitrace TT) does, and what the new contest software keeps

## Try the host software (no hardware needed)

```sh
cd host
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/f2a-timer --sim          # simulated 300 km/h flight in real time (--fast to skip waiting)
.venv/bin/pytest
```

## Contest files and results

`f2a-contest` keeps a contest (competitors, every attempt, the judges' rulings) in one JSON file and prints the
classification following the FAI rules: best speed, ties broken by the second and third best (4.1.18), team results
(4.1.19), juniors, and a printable HTML results sheet.

```sh
.venv/bin/f2a-contest import-legacy ../legacy/TT2 --out ../contests     # old DOS logs -> contest files
.venv/bin/f2a-contest results ../contests/<contest>.json --html results.html
.venv/bin/f2a-contest flight  ../contests/<contest>.json 4   # laps of competitor 4
```

Contest files and the old logs contain competitors' names: they stay on the club computer and are ignored by git
(GDPR). For tests, anonymise real logs with `host/tools/anonymise_tt_log.py`.

## With the Pico

Build the firmware (needs the [Pico SDK](https://github.com/raspberrypi/pico-sdk) and an `arm-none-eabi-gcc` toolchain):

```sh
cd firmware && mkdir build && cd build
cmake .. -DPICO_BOARD=pico      # or pico2
make
```

Hold BOOTSEL while plugging in the Pico, then copy `f2a_timer.uf2` onto it.

Bench test without a sensor: put a jumper from GP15 to GP2, then

```sh
.venv/bin/f2a-timer --test-pulses 1333     # ~300 km/h pulses
```

On Linux, add yourself to the `dialout` group to access `/dev/ttyACM0` without root.

## Roadmap

The old sensors no longer exist, so a new sensor is designed first.

1. ~~Timing core: timestamping, USB protocol, basic lap logic, CLI~~ (done, untested on hardware)
2. **Sensor design** ← *we are here*: simulation done (`docs/sensor-design.md`); bench test rig designed
   (`docs/bench-test.md`); next is building it and measuring real sky and model signals
3. Sensor and base station electronics: plan and parts list done (`docs/pcb-plan.md`); KiCad schematic after the bench test; then enclosure and firmware with on-sensor detection
4. Field tests; compare against manual timing
5. Contest software: F2A flight procedure, manual stopwatch entry, categories, printable flight reports.
   **Started:** FAI flight evaluation, contest files, results tables and import from the old software are done
   (`docs/legacy-software.md`); next is the live contest screen
6. GUI for an outdoor laptop or tablet
7. Optional: dual-slit sensor, wireless link, GPS clock calibration

Original sensor concept and system: Göran Olsson, Stockholm (go-cl.se), 2000–2007.

## License

Copyright (C) 2026 Viktor Vincze and contributors.

This project (software, firmware and hardware design files) is free software under the
[GNU General Public License v3.0](LICENSE): you may use, study, modify and share it, and anyone who
distributes a modified version must publish its source under the same license. That way, the code
used to time official flights can always be inspected.
