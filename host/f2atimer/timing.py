"""Live lap counting from sensor pass timestamps.

All arithmetic is on integer device microseconds, so precision does not depend
on the host at all. The official evaluation of a flight (timed laps, result,
corrections) is in :mod:`f2atimer.fai`; this module only turns the live stream
of passes into laps for display.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

F2A_LAP_M = 1000 / 9  # 9 laps = 1 km


@dataclass(frozen=True)
class Lap:
    number: int  # 1-based
    time_us: int
    suspect_missed: bool = False  # about twice the typical lap: the sensor probably missed a pass

    def speed_kmh(self, lap_m: float) -> float:
        return lap_m / (self.time_us / 1e6) * 3.6


@dataclass
class LapTimer:
    """Turns raw pass timestamps into laps.

    Stray pulses (birds, helpers, chatter) closer than ``min_lap_s`` to the
    last accepted pass are rejected. An interval close to twice the typical
    lap is flagged as a suspected missed pass. It is not corrected here: under
    the FAI rules the speed judge decides, see ``fai.Flight.insert_missed_lap``.
    """

    lap_m: float = F2A_LAP_M
    min_lap_s: float = 0.8
    missed_ratio: float = 1.6  # interval / typical lap that counts as a suspected missed pass

    passes_us: list[int] = field(default_factory=list)
    laps: list[Lap] = field(default_factory=list)
    rejected_us: list[int] = field(default_factory=list)

    def add_pass(self, t_us: int) -> Lap | None:
        """Feed one pass. Returns the lap it completed, if any."""
        if not self.passes_us:
            self.passes_us.append(t_us)
            return None

        interval = t_us - self.passes_us[-1]
        if interval < self.min_lap_s * 1e6:
            self.rejected_us.append(t_us)
            return None

        typical = self.typical_lap_us()
        suspect = bool(typical and interval > self.missed_ratio * typical)
        lap = Lap(len(self.laps) + 1, interval, suspect)
        self.laps.append(lap)
        self.passes_us.append(t_us)
        return lap

    def typical_lap_us(self) -> int | None:
        real = [lap.time_us for lap in self.laps if not lap.suspect_missed]
        return int(median(real[-5:])) if real else None

    def speed_over(self, first: int, count: int) -> float | None:
        """Average speed over ``count`` laps starting at 1-based lap ``first``."""
        laps = self.laps[first - 1 : first - 1 + count]
        if len(laps) < count:
            return None
        total_s = sum(lap.time_us for lap in laps) / 1e6
        return count * self.lap_m / total_s * 3.6
