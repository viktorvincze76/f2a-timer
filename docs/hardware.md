# Hardware hookup (phase 1)

Board: **Raspberry Pi Pico** (RP2040) or **Pico 2** (RP2350). Not a Pico W: not needed, and its LED is wired differently.

| Pico pin | Use |
|---|---|
| GP2 (pin 4) | Sensor pulse input, through the interface below |
| GP3 (pin 5) | Handle switch to GND (internal pull-up, debounced in firmware) |
| GP15 (pin 20) | Test pulse output. Jumper to GP2 for a loopback test, with no sensor connected |
| GND | Cable ground |
| USB | To the PC; also powers the Pico |

## Sensor input interface

**Treat the GPIOs as 3.3 V only.** The RP2040 is not 5 V tolerant, and the RP2350 only partly. The old sensor drives a 76 m cable
into a printer port. Measure its output with a scope or multimeter (idle level, pass
level and polarity) before connecting anything.

Recommended input stage (it also cleans up the slow edges from the long cable):

```
cable signal ──[10 kΩ]──┬──────────── A ┌──────────────┐
                        │               │ 74LVC1G17    │ Y ──── GP2
                      [1 nF]            │ Schmitt buf. │
                        │       3V3 ─── │ VCC          │
cable GND ──────────────┴── GND ─────── │ GND          │
                                        └──────────────┘
```

- The 74LVC1G17's input tolerates up to 5.5 V when powered from 3.3 V. If the sensor
  can exceed 5 V (it runs from 9 V), add a 3.3–4.7 V Zener or a TVS from A to GND.
- The 10 kΩ / 1 nF filter adds about 10 µs of **constant** delay. Lap times are differences
  between two passes, so it cancels out.
- If the sensor pulls its line **low** on a pass, set `SENSOR_ACTIVE_HIGH 0` in `firmware/main.c`.
- Later: an optocoupler, to keep the 76 m cable's ground separate from the PC's.
