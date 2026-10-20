"""Lap counting and speed calculation from sensor pass timestamps.

All arithmetic is on integer device microseconds, so precision does not depend
on the host at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

F2A_LAP_M = 1000 / 9  # 9 laps = 1 km


@dataclass(frozen=True)
class Lap:
    number: int  # 1-based
    time_us: int
    interpolated: bool = False  # split from an interval with a missed pass

    def speed_kmh(self, lap_m: float) -> float:
        return lap_m / (self.time_us / 1e6) * 3.6


@dataclass
class LapTimer:
    """Turns raw pass timestamps into laps.

    Stray pulses (birds, helpers, chatter) closer than ``min_lap_s`` to the
    last accepted pass are rejected. An interval close to twice the typical
    lap is treated as a missed pass (model flew under the sensor) and split
    into two interpolated laps.
    """

    lap_m: float = F2A_LAP_M
    min_lap_s: float = 0.8
    missed_ratio: float = 1.6  # interval / typical lap that counts as a missed pass

    passes_us: list[int] = field(default_factory=list)
    laps: list[Lap] = field(default_factory=list)
    rejected_us: list[int] = field(default_factory=list)

    def add_pass(self, t_us: int) -> list[Lap]:
        """Feed one pass. Returns the laps it completed (0, 1 or 2)."""
        if not self.passes_us:
            self.passes_us.append(t_us)
            return []

        interval = t_us - self.passes_us[-1]
        if interval < self.min_lap_s * 1e6:
            self.rejected_us.append(t_us)
            return []

        typical = self.typical_lap_us()
        if typical and interval > self.missed_ratio * typical:
            missed = round(interval / typical)
            base, extra = divmod(interval, missed)  # keep the total exact
            new = [self._lap(base + (i < extra), True) for i in range(missed)]
        else:
            new = [self._lap(interval)]
        self.passes_us.append(t_us)
        return new

    def typical_lap_us(self) -> int | None:
        real = [lap.time_us for lap in self.laps if not lap.interpolated]
        return int(median(real[-5:])) if real else None

    def speed_over(self, first: int, count: int) -> float | None:
        """Average speed over ``count`` laps starting at 1-based lap ``first``."""
        laps = self.laps[first - 1 : first - 1 + count]
        if len(laps) < count:
            return None
        total_s = sum(lap.time_us for lap in laps) / 1e6
        return count * self.lap_m / total_s * 3.6

    def _lap(self, time_us: int, interpolated: bool = False) -> Lap:
        lap = Lap(len(self.laps) + 1, time_us, interpolated)
        self.laps.append(lap)
        return lap
