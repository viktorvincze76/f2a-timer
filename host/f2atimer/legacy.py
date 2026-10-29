"""Import data from the old Transitrace TT software (MS-DOS): categories, name registries and flight logs.

File formats are described in docs/legacy-software.md. All files are DOS text in code page 852.
The logs contain competitors' names: import them into contest files on the club computer,
never into this repository.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .contest import Attempt, Competitor, Contest
from .fai import F2A, OFFICIAL_RULINGS, Category, Flight, Ruling

ENCODING = "cp852"
TTC_FIELDS = ["name", "timed_laps", "speed_constant", "unit", "attempt_minutes", "count_in_laps",
                    "start_on_release", "max_speed", "stopwatch_tolerance_s", "roundoff", "show_lap_times",
                    "sensor_radius"]
RULINGS = {"Electronic": Ruling.ELECTRONIC, "Manual": Ruling.MANUAL,
           "Cancelled": Ruling.CANCELLED, "Attempt": Ruling.ATTEMPT}


def read_text(path: Path) -> str:
    return path.read_bytes().decode(ENCODING, errors="replace").replace("\r\n", "\n")


# ---------------------------------------------------------------------------------------------
# Categories (.TTC) and name registries (NN*.TXT)


def read_category(path: str | Path) -> Category:
    """A .TTC file: one value per line, then a comment. Value fields are split on 2+ spaces."""
    values = [re.split(r"\s{2,}", line.strip(), maxsplit=1)[0]
              for line in read_text(Path(path)).splitlines() if line.strip()]
    conv = {"timed_laps": int, "speed_constant": float, "attempt_minutes": int, "count_in_laps": int,
            "start_on_release": lambda v: v.strip() == "1", "max_speed": float, "stopwatch_tolerance_s": float,
            "roundoff": int, "show_lap_times": lambda v: v.strip() == "1"}
    data = {k: conv.get(k, str)(v) for k, v in zip(TTC_FIELDS, values)}
    return Category.from_dict(data)


def read_names(path: str | Path) -> tuple[str, dict[int, str]]:
    """A name registry: '0<TAB>headline', then '<number><TAB><name>' lines."""
    headline, names = "", {}
    for line in read_text(Path(path)).splitlines():
        m = re.match(r"\s*(\d+)\s+(.*\S)", line)
        if not m:
            continue
        n, name = int(m[1]), m[2]
        if n == 0:
            headline = name
        else:
            names[n] = name
    return headline, names


_COUNTRY = re.compile(r"\s*\(([A-Z]{3})\)\s*$")
_JUNIOR = re.compile(r"\s+JUN\b")


def parse_name(raw: str) -> Competitor:
    """Split 'Gofast Marlon JUN (SWE)' into name, junior flag and country, as typed in the old program."""
    name, country = raw.strip(), ""
    if m := _COUNTRY.search(name):
        country, name = m[1], name[:m.start()]
    junior = bool(_JUNIOR.search(name))
    name = _JUNIOR.sub("", name).strip()
    return Competitor(0, name, country, junior=junior)  # teams are set by the organiser, not guessed


# ---------------------------------------------------------------------------------------------
# Flight logs (TTyymmdd.TXT)


@dataclass
class LegacyFlight:
    category: str
    started: datetime
    round: int
    headline: str
    competitor: int
    name: str
    attempt: int
    etime: float = 0.0
    stopwatches: list[float] = field(default_factory=list)
    eresult: float = 0.0
    mresult: float = 0.0
    ruling: Ruling | None = None
    timed_laps: tuple[int, int] | None = None
    shift: int = 0
    passes_s: list[float] = field(default_factory=list)
    inserted_flags: list[int] = field(default_factory=list)  # laps the old program marked "missed lap inserted"
    handle: list[tuple[float, bool]] = field(default_factory=list)
    comment: list[str] = field(default_factory=list)

    @property
    def practice(self) -> bool:
        return self.round == 0 or self.competitor == 0

    def to_attempt(self) -> Attempt:
        flight = Flight([round(t * 1e6) for t in self.passes_s],
                        [(round(t * 1e6), on) for t, on in self.handle], shift=self.shift)
        recorded = {Ruling.ELECTRONIC: self.eresult, Ruling.MANUAL: self.mresult,
                    Ruling.CANCELLED: 0.0}.get(self.ruling)
        comment = list(self.comment)
        if self.inserted_flags:
            comment.append("Old software: missed lap inserted by operator; time stamps include it.")
        return Attempt(self.competitor, self.round, self.attempt, self.started.isoformat(), flight,
                       [t or None for t in self.stopwatches] or [None, None, None], self.ruling,
                       "\n".join(comment), self.practice, recorded)


def read_log(path: str | Path) -> list[LegacyFlight]:
    flights: list[LegacyFlight] = []
    cur: LegacyFlight | None = None
    expect_results = False
    for line in read_text(Path(path)).splitlines():
        f = line.split("\t")
        if line.startswith("# TT\t"):
            started = datetime.strptime(f"{f[2]} {f[3]}", "%a %b %d %Y %H:%M:%S")
            rnd = int(f[4].split(":")[1])
            cur = LegacyFlight(f[1], started, rnd, f[5].strip() if len(f) > 5 else "", 0, "", 0)
            flights.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("# Comp:"):
            cur.competitor = int(f[1])
            cur.name = f[2].strip()
            cur.attempt = int(line.rsplit(":", 1)[1])
        elif line.startswith("# ETime"):
            expect_results = True
        elif expect_results:
            expect_results = False
            nums = [float(x) for x in f[:9] if re.fullmatch(r"\s*-?[\d.]+\s*", x)]
            cur.etime, cur.stopwatches = nums[0], nums[1:4]
            if len(nums) >= 8:
                cur.eresult, cur.mresult = nums[6], nums[7]
            if m := re.search(r"\$ (\w+)", line):
                cur.ruling = RULINGS.get(m[1])
        elif line.startswith("# Timed Flight Laps:"):
            m = re.search(r"(\d+)\s*-\s*(\d+)", line)
            cur.timed_laps = (int(m[1]), int(m[2]))
            if m := re.search(r"Shift:\s*(-?\d+)", line):
                cur.shift = int(m[1])
        elif m := re.match(r"\s+(\d+)\t[^\t]*\t\s*([\d.]+)", line):
            cur.passes_s.append(float(m[2]))
            if "Missed lap inserted" in line:
                cur.inserted_flags.append(int(m[1]))
        elif m := re.match(r"# (Engaged|Disengaged)\s+([\d.]+)", line):
            cur.handle.append((float(m[2]), m[1] == "Engaged"))
        elif line.startswith("# Individual laps") or line.startswith("# Lap ") or line.startswith("# Handle"):
            pass
        elif line.strip():
            cur.comment.append(line.lstrip("# ").rstrip())
    return flights


# ---------------------------------------------------------------------------------------------
# Whole folder -> contests


def import_folder(folder: str | Path) -> list[Contest]:
    """Every TT*.TXT log in ``folder`` as contests, one per headline and category.

    Logs without a headline (older ones) become one contest per day and category.
    Names come from the logs, completed from any NN*.TXT registry with the same headline.
    """
    folder = Path(folder)
    categories = {p.stem.upper(): read_category(p) for p in folder.glob("*.[Tt][Tt][Cc]")}
    registries = {}
    for p in folder.glob("[Nn][Nn]*.[Tt][Xx][Tt]"):
        headline, names = read_names(p)
        if headline:
            registries.setdefault(headline, {}).update(names)

    contests: dict[tuple[str, str], Contest] = {}
    used: dict[tuple, set[int]] = {}  # official rounds per (contest, competitor)
    for log in sorted(folder.glob("[Tt][Tt][0-9]*.[Tt][Xx][Tt]")):
        for lf in read_log(log):
            name = lf.headline or f"TT {lf.started:%Y-%m-%d}"
            key = (name, lf.category)
            if key not in contests:
                cat = categories.get(lf.category.upper(), F2A if lf.category.upper() == "F2A" else Category(lf.category))
                contests[key] = Contest(name, cat, lf.started.date().isoformat(), rounds=0,
                                        source=f"Imported from Transitrace TT logs ({log.name}...)")
                for n, raw in registries.get(lf.headline, {}).items():
                    contests[key].competitors[n] = _competitor(n, raw)
            c = contests[key]
            if lf.competitor and lf.name and lf.name != "Auto":
                c.competitors[lf.competitor] = _merge(c.competitors.get(lf.competitor),
                                                      _competitor(lf.competitor, lf.name))
            attempt = lf.to_attempt()
            if attempt.ruling in OFFICIAL_RULINGS and not attempt.practice:
                # The old program kept whatever round number was set, and clubs often never changed
                # it: a second official flight "in round 1" is really the competitor's next round.
                taken = used.setdefault((key, lf.competitor), set())
                if attempt.round in taken:
                    new_round = next(r for r in range(attempt.round + 1, 1000) if r not in taken)
                    attempt.comment = "\n".join(filter(None, [
                        attempt.comment, f"Round renumbered on import: the old log says round {attempt.round}."]))
                    attempt.round = new_round
                taken.add(attempt.round)
            c.attempts.append(attempt)
            c.rounds = max(c.rounds, attempt.round)
    return list(contests.values())


def _competitor(number: int, raw: str) -> Competitor:
    c = parse_name(raw)
    c.number = number
    return c


def _merge(old: Competitor | None, new: Competitor) -> Competitor:
    """Names were retyped on each day; keep country and junior flag if one spelling lacks them."""
    if old is None:
        return new
    return Competitor(new.number, new.name if len(new.name) >= len(old.name) else old.name,
                      new.country or old.country, new.team or old.team, new.junior or old.junior)
