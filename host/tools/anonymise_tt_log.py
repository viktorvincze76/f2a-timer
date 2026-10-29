"""Make an anonymised copy of old Transitrace TT logs, safe to commit as test data (GDPR).

Removes everything that identifies a person or an event: names become "Pilot 01"...,
competitor numbers are renumbered, contest names are replaced, dates move to January 2000
(keeping day order and time of day), and free-text comments are dropped. Lap time stamps,
handle events, results and rulings are kept: they are what the tests need.

    python tools/anonymise_tt_log.py LOG [LOG ...] -o tests/data/legacy_anon.txt [--pick 10:07:30 ...]

Always read the output before committing it.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path

KEEP = re.compile(r"^(# (ETime|Timed Flight|Individual laps|Lap |Handle Events|Engaged|Disengaged)|\s+\d+\t|[\d. ]+\t)")


def anonymise(paths: list[Path], pick: set[str] | None = None) -> str:
    blocks = []
    for path in paths:
        text = path.read_bytes().decode("cp852", errors="replace").replace("\r\n", "\n")
        blocks += [b for b in text.split("# TT\t")[1:]]
    numbers: dict[str, int] = {}
    days: dict[str, datetime] = {}
    out = []
    for b in blocks:
        lines = b.splitlines()
        head = lines[0].split("\t")  # category, date, time, round, headline
        if pick and head[2] not in pick:
            continue
        date = datetime.strptime(head[1], "%a %b %d %Y")
        if head[1] not in days:
            days[head[1]] = datetime(2000, 1, 3) + timedelta(days=len(days))
        new_date = days[head[1]]
        res = [f"# TT\t{head[0]}\t{new_date:%a %b %d %Y}\t{head[2]}\t{head[3]}\tAnonymised contest"]
        for line in lines[1:]:
            if line.startswith("# Comp:"):
                f = line.split("\t")
                if f[1].strip() == "0":
                    res.append(line)  # "Auto" practice: no person
                    continue
                n = numbers.setdefault(f[1].strip(), len(numbers) + 1)
                res.append(f"# Comp:\t{n}\tPilot {n:02d}\t\t\t{f[-1]}")
            elif KEEP.match(line) or not line.strip():
                res.append(line)
            # anything else is a free-text comment: dropped
        out.append("\n".join(res).rstrip() + "\n\n\n")
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", type=Path, nargs="+")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--pick", nargs="*", help="only flights started at these times (HH:MM:SS)")
    args = ap.parse_args()
    args.out.write_bytes(anonymise(args.logs, set(args.pick) if args.pick else None)
                         .replace("\n", "\r\n").encode("cp852"))
    print(f"Wrote {args.out}. Check it by eye before committing.")


if __name__ == "__main__":
    main()
