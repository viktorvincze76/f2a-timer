"""Contest data: competitors, attempts and their validation, stored as one JSON file per contest.

A contest replaces the old program's name registry (NN*.TXT) plus its per-day logs
(TT*.TXT): one file holds everything for a contest, even when it runs over several days.
Contest files contain personal data (competitor names); keep them out of the repository.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .fai import F2A, OFFICIAL_RULINGS, Category, Evaluation, Flight, ManualTiming, Ruling, manual_time

FORMAT_VERSION = 1


@dataclass
class Competitor:
    number: int
    name: str
    country: str = ""  # e.g. "SVK"
    team: str = ""  # team for the team classification (4.1.19); usually the country
    junior: bool = False


@dataclass
class Attempt:
    """One attempt: who, when, the electronic data and the judge's validation."""

    competitor: int
    round: int
    attempt: int = 1
    started: str = ""  # ISO date and time
    flight: Flight = field(default_factory=lambda: Flight([]))
    stopwatches: list[float | None] = field(default_factory=lambda: [None, None, None])
    ruling: Ruling | None = None
    comment: str = ""
    practice: bool = False
    # Result as recorded at validation (and by the old software, for imported attempts).
    # Kept so a later change in evaluation code can never silently change a published result.
    recorded_result: float | None = None

    def evaluate(self, category: Category) -> Evaluation:
        return self.flight.evaluate(category)

    def manual(self, category: Category) -> ManualTiming:
        return manual_time(self.stopwatches, category.stopwatch_tolerance_s)

    def result(self, category: Category) -> float | None:
        """Official speed of this attempt, or None if it is not an official flight."""
        if self.practice or self.ruling not in OFFICIAL_RULINGS:
            return None
        if self.recorded_result is not None:
            return self.recorded_result
        if self.ruling is Ruling.CANCELLED:
            return 0.0
        if self.ruling is Ruling.ELECTRONIC:
            return self.evaluate(category).result
        mt = self.manual(category)
        return category.round_result(category.speed(mt.time_s)) if mt.time_s else None

    def validate(self, ruling: Ruling, category: Category) -> float | None:
        """Record the judge's ruling and freeze the result."""
        self.ruling = ruling
        self.recorded_result = None
        self.recorded_result = self.result(category)
        return self.recorded_result


@dataclass
class Contest:
    name: str
    category: Category = F2A
    date: str = ""  # first day, ISO
    rounds: int = 4  # 4.1.11: 3 or 4, fixed before the start
    competitors: dict[int, Competitor] = field(default_factory=dict)
    attempts: list[Attempt] = field(default_factory=list)
    source: str = ""  # e.g. "imported from Transitrace logs"

    def competitor(self, number: int) -> Competitor:
        return self.competitors.get(number) or Competitor(number, f"#{number}")

    def official_results(self) -> dict[int, dict[int, float]]:
        """{competitor: {round: speed}} for official flights (cancelled = 0.0)."""
        out: dict[int, dict[int, float]] = {}
        for a in self.attempts:
            r = a.result(self.category)
            if r is not None:
                out.setdefault(a.competitor, {})[a.round] = r  # a later validated flight replaces
        return out

    # -- storage -------------------------------------------------------------------------------

    def to_dict(self) -> dict:
        d = asdict(self)
        d["format"] = FORMAT_VERSION
        d["competitors"] = [asdict(c) for c in self.competitors.values()]
        for a in d["attempts"]:
            a["ruling"] = a["ruling"].value if a["ruling"] else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Contest:
        attempts = []
        for a in d.get("attempts", []):
            fl = a.pop("flight")
            fl["handle"] = [tuple(h) for h in fl.get("handle", [])]
            attempts.append(Attempt(**{**a, "flight": Flight(**fl),
                                       "ruling": Ruling(a["ruling"]) if a.get("ruling") else None}))
        return cls(
            name=d["name"],
            category=Category.from_dict(d.get("category", {})),
            date=d.get("date", ""),
            rounds=d.get("rounds", 4),
            competitors={c["number"]: Competitor(**c) for c in d.get("competitors", [])},
            attempts=attempts,
            source=d.get("source", ""),
        )

    def save(self, path: str | Path) -> None:
        """Write atomically, so a crash or a flat laptop battery never leaves half a file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> Contest:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
