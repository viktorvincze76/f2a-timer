"""Flight evaluation following the FAI Sporting Code, class F2A (section 4.1).

Rule numbers refer to the F2A rules shipped with the old Transitrace software
(docs/legacy-software.md). The timing rules were checked against 117 electronic
results logged by that software; this module reproduces all of them.

Times are integer microseconds on the timer's clock. A flight is a list of
sensor passes: pass 0 is the first, and lap ``n`` ends at pass ``n``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from enum import Enum
from statistics import median


class Ruling(str, Enum):
    """How the speed judge validated an attempt (the old program's E/M/A/C keys)."""

    ELECTRONIC = "electronic"  # official flight, electronic result
    MANUAL = "manual"  # official flight, stopwatch result
    ATTEMPT = "attempt"  # not an official flight: handle not engaged in time (4.1.8)
    CANCELLED = "cancelled"  # official flight, cancelled under 4.1.15: counts, scores 0


OFFICIAL_RULINGS = (Ruling.ELECTRONIC, Ruling.MANUAL, Ruling.CANCELLED)

# The old program's round-off options, same numbering as its category files.
ROUNDOFF = {
    1: (1, ROUND_FLOOR),  # 1 decimal, truncated: FAI 4.1.17 a) v) "nearest lower 1/10 km/h"
    2: (1, ROUND_HALF_UP),
    3: (2, ROUND_FLOOR),
    4: (2, ROUND_HALF_UP),
    5: (3, ROUND_HALF_UP),
}


@dataclass(frozen=True)
class Category:
    """Contest category; the fields of the old program's .TTC files."""

    name: str = "FAI-F2A"
    timed_laps: int = 9  # 4.1.5: 9 laps of a 17.69 m radius = 1 km
    speed_constant: float = 3600.0  # speed = speed_constant / time of the timed laps
    unit: str = "km/h"
    attempt_minutes: int = 3  # 4.1.8
    count_in_laps: int = 2  # 4.1.13
    start_on_release: bool = False  # AMA proto classes: count from model release, not pylon
    max_speed: float = 340.0  # sanity limit, and the stray-pulse filter
    stopwatch_tolerance_s: float = 0.12  # 4.1.17
    roundoff: int = 1
    show_lap_times: bool = False  # display lap times instead of lap speeds
    sensor_radius: str = "21.5 m"  # where the sensor goes for this category

    def speed(self, time_s: float) -> float:
        """Speed over the timed laps, unrounded."""
        return self.speed_constant / time_s

    def lap_speed(self, lap_s: float) -> float:
        return self.speed_constant / (self.timed_laps * lap_s)

    def round_result(self, speed: float) -> float:
        places, mode = ROUNDOFF[self.roundoff]
        # Go through a short decimal string so 300.0 stored as 299.99999999999997 is not truncated to 299.9.
        exact = Decimal(f"{speed:.9f}")
        return float(exact.quantize(Decimal(1).scaleb(-places), rounding=mode))

    def min_lap_us(self) -> int:
        """Shortest believable lap: anything faster is a stray pulse."""
        return int(self.speed_constant / (self.timed_laps * self.max_speed) * 1e6)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Category:
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


F2A = Category()


# ---------------------------------------------------------------------------------------------
# Electronic timing


@dataclass(frozen=True)
class Pass:
    t_us: int
    inserted: bool = False  # added by the operator for a lap the sensor missed


@dataclass(frozen=True)
class Evaluation:
    """Result of evaluating one flight's electronic timing."""

    status: str  # "completed", "not completed" (fewer laps than needed), "not started" (no engage)
    first_lap: int | None = None  # first timed lap (1-based, as in the old logs "Timed Flight Laps")
    last_lap: int | None = None
    time_s: float | None = None
    speed: float | None = None  # unrounded
    result: float | None = None  # rounded per category: the official electronic speed
    handle_released_during_run: bool = False  # 4.1.15 c): grounds for cancellation
    inserted_laps_in_run: tuple[int, ...] = ()  # judge must be aware (4.1.17 Electronic ii)

    @property
    def completed(self) -> bool:
        return self.status == "completed"


class IrregularLapsError(ValueError):
    """Raised when a lap does not look like two laps, so splitting it would invent data."""


@dataclass
class Flight:
    """Electronic data of one attempt, plus the operator's corrections.

    The raw passes and handle events are never modified; corrections (a shift of the
    timed laps, inserted laps) are stored separately so they can be reviewed and undone.
    """

    passes_us: list[int]
    handle: list[tuple[int, bool]] = field(default_factory=list)  # (time, engaged)
    release_us: int | None = None  # model release, for start_on_release categories
    shift: int = 0  # move the timed laps by this many laps (handle judging error)
    inserted: list[int] = field(default_factory=list)  # laps split by the operator, in order applied
    auto: bool = False  # practice without a handle: the first pass starts the count-in

    # -- laps ----------------------------------------------------------------------------------

    def passes(self) -> list[Pass]:
        """Passes after the operator's inserted laps are applied."""
        ps = [Pass(t) for t in self.passes_us]
        for lap in self.inserted:
            a, b = ps[lap - 1].t_us, ps[lap].t_us
            ps.insert(lap, Pass((a + b) // 2, inserted=True))
        return ps

    def lap_times_us(self) -> list[int]:
        ps = self.passes()
        return [b.t_us - a.t_us for a, b in zip(ps, ps[1:])]

    def suspected_missed_laps(self, category: Category = F2A, tolerance: float = 0.2) -> list[int]:
        """Laps that look like two laps: probably a pass the sensor missed (model flew low).

        A lap counts when it is within ``tolerance`` of twice its neighbours and the laps on both
        sides are steady (within ``tolerance / 2`` of each other); take-off and landing laps, which
        stretch gradually, do not trigger it. Only laps from the handle engage to the end of the
        timed laps are checked. Only reported: under FAI 4.1.17 the speed judge decides, so nothing
        changes until :meth:`insert_missed_lap`.
        """
        start = self.start_pass(category)
        if start is None:
            return []
        first = start - category.count_in_laps - self.shift + 1  # first lap after the engage
        last = start + category.timed_laps
        laps = self.lap_times_us()
        return [i + 1 for i in range(max(0, first - 1), min(len(laps), last))
                if _looks_like_two_laps(laps, i, tolerance)]

    def insert_missed_lap(self, lap: int, tolerance: float = 0.2) -> None:
        """Split lap ``lap`` in two equal halves (the old program's I key).

        Refuses when the lap is not close to twice its neighbours (within ``tolerance``),
        like the old program's "Times are too irregular! No action taken."
        """
        laps = self.lap_times_us()
        if not 1 <= lap <= len(laps):
            raise ValueError(f"no lap {lap}")
        if not _looks_like_two_laps(laps, lap - 1, tolerance):
            raise IrregularLapsError(f"lap {lap} is not about twice its neighbours; not split")
        self.inserted.append(lap)

    # -- timed laps ----------------------------------------------------------------------------

    def start_pass(self, category: Category) -> int | None:
        """Index of the pass that starts the timed laps, or None if timing never started."""
        ps = self.passes()
        if self.auto:
            ref = None
        elif category.start_on_release:
            if self.release_us is None:
                return None
            ref = self.release_us
        else:
            engaged = [t for t, on in self.handle if on]
            if not engaged:
                return None
            ref = engaged[-1]  # a re-engage restarts the count-in
        # First pass after the reference: the one after the last pass at or before it. (Not simply
        # "first pass later than ref": the old logs show passes whose clock glitched, and this
        # reproduces them too.)
        first = 0 if ref is None else 1 + max((i for i, p in enumerate(ps) if p.t_us <= ref), default=-1)
        if first >= len(ps):
            return None
        start = first + category.count_in_laps + self.shift
        return start if start >= 0 else None

    def evaluate(self, category: Category = F2A) -> Evaluation:
        ps = self.passes()
        start = self.start_pass(category)
        if start is None:
            return Evaluation("not started")
        end = start + category.timed_laps
        if end >= len(ps):
            return Evaluation("not completed", start + 1, end)
        time_s = (ps[end].t_us - ps[start].t_us) / 1e6
        speed = category.speed(time_s)
        t0, t1 = ps[start].t_us, ps[end].t_us
        released = any(not on and t0 < t <= t1 for t, on in self.handle) if not self.auto else False
        inserted = tuple(i for i in range(start + 1, end + 1) if ps[i].inserted)
        return Evaluation("completed", start + 1, end, time_s, speed, category.round_result(speed),
                          released, inserted)

    def course_speeds(self, category: Category = F2A) -> list[float | None]:
        """Speed over the last ``timed_laps`` laps at every pass (the log's "Course Speed")."""
        ps = self.passes()
        n = category.timed_laps
        return [category.speed((ps[i].t_us - ps[i - n].t_us) / 1e6) if i >= n else None
                for i in range(len(ps))]

    def best_run(self, category: Category = F2A) -> tuple[int, float] | None:
        """Fastest ``timed_laps`` consecutive laps of the flight: (first lap, speed). Informational."""
        speeds = self.course_speeds(category)
        best = max(((s, i) for i, s in enumerate(speeds) if s is not None), default=None)
        if best is None:
            return None
        s, i = best
        return i - category.timed_laps + 1, s


def _looks_like_two_laps(laps: list[int], i: int, tolerance: float) -> bool:
    """Lap ``i`` is about twice the steady laps on both sides of it."""
    before, after = laps[max(0, i - 2):i], laps[i + 1:i + 3]
    if not before or not after:
        return False
    near = before + after
    ref = median(near)
    steady = all(abs(t / ref - 1) <= tolerance / 2 for t in near)
    return steady and abs(laps[i] / ref - 2) <= 2 * tolerance


# ---------------------------------------------------------------------------------------------
# Manual timing (4.1.17)


@dataclass(frozen=True)
class ManualTiming:
    time_s: float | None
    used: tuple[int, ...]  # stopwatch numbers (1-based) that went into the time
    notify_competitor: bool  # competitor may choose this time or a replacement attempt
    note: str


def manual_time(times: list[float | None], tolerance_s: float = 0.12) -> ManualTiming:
    """Combine stopwatch times following 4.1.17.

    Three watches: the mean; a watch further than ``tolerance_s`` from the closer of the
    other two is dropped; if only one remains, it is used and the competitor must be told
    of the right to a replacement attempt. Two watches (backup to electronic timing): the
    mean, or if they disagree, the slower time and the competitor is told. No rounding of
    the mean (4.1.17 a) iv).
    """
    valid = [(i + 1, t) for i, t in enumerate(times) if t]
    if not valid:
        return ManualTiming(None, (), False, "no valid stopwatch time")
    if len(valid) == 1:
        (n, t), = valid
        return ManualTiming(t, (n,), True, "only one stopwatch")
    if len(valid) == 2:
        (n1, t1), (n2, t2) = valid
        if abs(t1 - t2) <= tolerance_s + 1e-9:
            return ManualTiming((t1 + t2) / 2, (n1, n2), False, "mean of two stopwatches")
        n, t = max(valid, key=lambda v: v[1])
        return ManualTiming(t, (n,), True, "two stopwatches disagree: slower time used")

    def gap(i: int) -> float:
        return min(abs(valid[i][1] - valid[j][1]) for j in range(len(valid)) if j != i)

    keep = [v for i, v in enumerate(valid) if gap(i) <= tolerance_s + 1e-9]
    if len(keep) >= 2:
        nums = tuple(n for n, _ in keep)
        note = "mean of three stopwatches" if len(keep) == 3 else f"stopwatch {_dropped(valid, keep)} dropped"
        return ManualTiming(sum(t for _, t in keep) / len(keep), nums, False, note)
    n, t = sorted(valid, key=lambda v: v[1])[1]  # the middle one
    return ManualTiming(t, (n,), True, "stopwatches disagree: middle time only")


def _dropped(valid: list[tuple[int, float]], keep: list[tuple[int, float]]) -> str:
    return ", ".join(str(n) for n, t in valid if (n, t) not in keep)
