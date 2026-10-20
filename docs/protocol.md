# Device ↔ host protocol

USB CDC serial (the Pico ignores the baud rate). ASCII, one message per line, `\n` terminated.
All times are **device microseconds since power-up** (64-bit, never wraps in practice).

## Device → host

| Line | Meaning |
|---|---|
| `HELLO f2a-timer <version>` | Sent on connect and in reply to `?` |
| `E <seq> <ch> <active> <t_us>` | An edge. `ch`: `S` sensor, `H` handle switch. `active`: `1` = pass begins / handle engaged, `0` = ends / released |
| `B <t_us> <dropped>` | Heartbeat, once a second. `dropped` = events lost to a full queue since power-up |

`seq` increases by one for every event, including dropped ones, so a gap means lost data.
Events captured while no host is connected are queued (1024 deep) and sent on reconnect.

## Host → device

| Line | Meaning |
|---|---|
| `?` | Re-send `HELLO` |
| `T <period_ms> [width_us]` | Emit test pulses on the test pin (default width 2000 µs) |
| `T 0` | Stop test pulses |
