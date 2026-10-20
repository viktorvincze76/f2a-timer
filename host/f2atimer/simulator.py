"""A stand-in for the device, emitting realistic protocol lines for one flight.

Lets the host software be developed and tested without hardware or a model.
"""

from __future__ import annotations

import random
import time
from collections.abc import Iterator

from .timing import F2A_LAP_M


class SimulatedDevice:
    def __init__(self, speed_kmh: float = 300.0, laps: int = 14, realtime: bool = True, seed: int | None = None):
        self.speed_kmh = speed_kmh
        self.laps = laps
        self.realtime = realtime
        self.port = "simulator"
        self._rng = random.Random(seed)

    def send(self, command: str) -> None:
        pass

    def close(self) -> None:
        pass

    def lines(self) -> Iterator[str]:
        rng = self._rng
        lap_us = F2A_LAP_M / (self.speed_kmh / 3.6) * 1e6
        t = 5_000_000  # device has been on for 5 s
        seq = 0
        events: list[tuple[int, str, int]] = []

        events.append((t, "H", 0))
        t += 2_000_000
        missed = rng.randrange(4, self.laps - 2)  # one underflown lap
        bird = rng.choice([i for i in range(2, self.laps - 2) if i != missed])  # one stray pulse
        for lap in range(self.laps + 1):
            if lap != missed:
                width = rng.randrange(2000, 5000)
                events += [(t, "S", 1), (t + width, "S", 0)]
            if lap == bird:
                stray = t + int(lap_us * rng.uniform(0.2, 0.5))
                events += [(stray, "S", 1), (stray + 1500, "S", 0)]
            t += int(lap_us * rng.gauss(1.0, 0.004))
        events.append((t + 3_000_000, "H", 1))
        events.sort()

        yield "HELLO f2a-timer sim"
        start_wall = time.monotonic()
        start_dev = events[0][0]
        next_beat = (start_dev // 1_000_000 + 1) * 1_000_000
        for t_us, ch, active in events:
            while next_beat <= t_us:
                self._wait(start_wall, next_beat - start_dev)
                yield f"B {next_beat} 0"
                next_beat += 1_000_000
            self._wait(start_wall, t_us - start_dev)
            yield f"E {seq} {ch} {active} {t_us}"
            seq += 1

    def _wait(self, start_wall: float, offset_us: int) -> None:
        if self.realtime:
            delay = start_wall + offset_us / 1e6 - time.monotonic()
            if delay > 0:
                time.sleep(delay)
