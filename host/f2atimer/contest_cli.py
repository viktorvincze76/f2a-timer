"""f2a-contest: contest files, results tables, flight review, and import from the old DOS software."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import results
from .contest import Contest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="f2a-contest", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("import-legacy", help="convert the old Transitrace TT folder (TT2) into contest files")
    p.add_argument("folder", type=Path, help="folder with TT*.TXT logs, NN*.TXT names and *.TTC categories")
    p.add_argument("--out", type=Path, default=Path("contests"), help="output folder (default: ./contests)")

    p = sub.add_parser("results", help="print the classification of a contest")
    p.add_argument("contest", type=Path)
    p.add_argument("--juniors", action="store_true", help="junior classification only")
    p.add_argument("--html", type=Path, metavar="FILE", help="also write a printable HTML page")

    p = sub.add_parser("flight", help="show one competitor's flights: laps, timed laps, result")
    p.add_argument("contest", type=Path)
    p.add_argument("competitor", type=int)
    p.add_argument("round", type=int, nargs="?", help="only this round")

    args = ap.parse_args(argv)
    return {"import-legacy": import_legacy, "results": show_results, "flight": show_flight}[args.cmd](args)


def import_legacy(args) -> int:
    from .legacy import import_folder

    contests = import_folder(args.folder)
    if not contests:
        print(f"No TT*.TXT logs found in {args.folder}", file=sys.stderr)
        return 1
    for c in contests:
        path = args.out / (_slug(f"{c.date} {c.name} {c.category.name}") + ".json")
        c.save(path)
        official = sum(1 for a in c.attempts if a.result(c.category) is not None)
        print(f"{path}: {len(c.competitors)} competitors, {len(c.attempts)} attempts, {official} official flights")
    print("These files contain names: keep them on the club computer, not in the git repository.")
    return 0


def show_results(args) -> int:
    contest = Contest.load(args.contest)
    print(results.text(contest, args.juniors), end="")
    if args.html:
        args.html.write_text(results.html_page(contest, args.juniors), encoding="utf-8")
        print(f"\nWrote {args.html}")
    return 0


def show_flight(args) -> int:
    contest = Contest.load(args.contest)
    cat = contest.category
    c = contest.competitor(args.competitor)
    attempts = [a for a in contest.attempts if a.competitor == args.competitor
                and (args.round is None or a.round == args.round)]
    if not attempts:
        print(f"No attempts for competitor {args.competitor}", file=sys.stderr)
        return 1
    for a in attempts:
        ev = a.evaluate(cat)
        kind = "practice" if a.practice else f"round {a.round}, attempt {a.attempt}"
        print(f"\n{c.number} {c.name} - {kind} - started {a.started.replace('T', ' ')}")
        ps = a.flight.passes()
        course = a.flight.course_speeds(cat)
        timed = range(ev.first_lap or 0, (ev.last_lap or -1) + 1) if ev.completed else range(0)
        print(f"  Lap  {'Time (s)' if cat.show_lap_times else 'Speed':>9}  Time stamp   Course")
        for i, p in enumerate(ps):
            lap = (p.t_us - ps[i - 1].t_us) / 1e6 if i else None
            val = "" if lap is None else (f"{lap:9.4f}" if cat.show_lap_times else f"{cat.lap_speed(lap):9.3f}")
            flags = (" T" if i in timed else "") + (" inserted" if p.inserted else "")
            cs = f"{course[i]:8.3f}" if course[i] else ""
            print(f"  {i:3d}  {val:>9}  {p.t_us / 1e6:11.4f}  {cs:>8}{flags}")
        for t, on in a.flight.handle:
            print(f"  handle {'engaged' if on else 'released'} at {t / 1e6:.4f}")
        if ev.completed:
            print(f"  Timed laps {ev.first_lap}-{ev.last_lap}: {ev.time_s:.4f} s, {ev.speed:.3f} -> {ev.result} {cat.unit}"
                  + (f" (shifted {a.flight.shift:+d})" if a.flight.shift else ""))
        else:
            print(f"  Timing: {ev.status}")
        if ev.handle_released_during_run:
            print("  WARNING: handle released during the timed laps (4.1.15 c)")
        if missed := a.flight.suspected_missed_laps(cat):
            print(f"  WARNING: missed lap? Time doubled at lap {', '.join(map(str, missed))}")
        if best := a.flight.best_run(cat):
            print(f"  Best {cat.timed_laps} laps: {best[0]}-{best[0] + cat.timed_laps - 1}, {best[1]:.3f} {cat.unit}")
        mt = a.manual(cat)
        if mt.time_s:
            print(f"  Manual: {mt.time_s:.3f} s ({mt.note})" + (" - tell the competitor of the right to a new attempt"
                                                              if mt.notify_competitor else ""))
        ruling = a.ruling.value if a.ruling else "not validated"
        r = a.result(cat)
        print(f"  Ruling: {ruling}" + (f", result {r} {cat.unit}" if r is not None else ""))
        if a.comment:
            print("  Comment: " + a.comment.replace("\n", "\n           "))
    return 0


def _slug(s: str) -> str:
    return re.sub(r"[^\w.-]+", "-", s, flags=re.ASCII).strip("-").lower()


if __name__ == "__main__":
    sys.exit(main())
