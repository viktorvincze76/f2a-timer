"""Contest classification: individual (FAI 4.1.18) and team (4.1.19), as text or printable HTML."""

from __future__ import annotations

import html
from dataclasses import dataclass

from .contest import Contest


@dataclass(frozen=True)
class Placing:
    place: int | None  # None: no official flight yet
    competitor: int
    name: str
    country: str
    junior: bool
    rounds: dict[int, float]  # round -> official speed (0.0 = cancelled)

    @property
    def ranking_key(self) -> tuple[float, ...]:
        """Best speed, then second best, then third... (4.1.18 a)."""
        return tuple(sorted(self.rounds.values(), reverse=True))

    @property
    def best(self) -> float | None:
        return max(self.rounds.values()) if self.rounds else None


@dataclass(frozen=True)
class TeamPlacing:
    place: int
    team: str
    total: float
    members: tuple[Placing, ...]


def individual(contest: Contest, juniors_only: bool = False) -> list[Placing]:
    results = contest.official_results()
    numbers = set(results) | {a.competitor for a in contest.attempts if not a.practice}
    rows = []
    for n in numbers:
        c = contest.competitor(n)
        if juniors_only and not c.junior:
            continue
        rows.append(Placing(None, n, c.name, c.country, c.junior, results.get(n, {})))
    ranked = sorted((r for r in rows if r.rounds), key=lambda r: r.ranking_key, reverse=True)
    out, prev, place = [], None, 0
    for i, r in enumerate(ranked, 1):
        if r.ranking_key != prev:  # equal on every flight: shared place
            place, prev = i, r.ranking_key
        out.append(Placing(place, r.competitor, r.name, r.country, r.junior, r.rounds))
    unplaced = sorted((r for r in rows if not r.rounds), key=lambda r: r.competitor)
    return out + unplaced


def teams(contest: Contest, placings: list[Placing] | None = None) -> list[TeamPlacing]:
    """Sum of each member's best speed; ties: lower sum of places, then best individual place."""
    placings = placings or individual(contest)
    by_team: dict[str, list[Placing]] = {}
    for p in placings:
        team = contest.competitor(p.competitor).team
        if team and p.place is not None:
            by_team.setdefault(team, []).append(p)
    if not by_team:
        return []

    def key(item):
        team, members = item
        total = round(sum(m.best for m in members), 1)
        return (-total, sum(m.place for m in members), min(m.place for m in members))

    ordered = sorted(by_team.items(), key=key)
    out, prev, place = [], None, 0
    for i, item in enumerate(ordered, 1):
        k = key(item)
        if k != prev:
            place, prev = i, k
        team, members = item
        out.append(TeamPlacing(place, team, -k[0], tuple(members)))
    return out


# ---------------------------------------------------------------------------------------------
# Output


def _speed(v: float | None) -> str:
    if v is None:
        return "-"
    return "C" if v == 0 else f"{v:.1f}"


def text(contest: Contest, juniors_only: bool = False) -> str:
    rows = individual(contest, juniors_only)
    nrounds = max([contest.rounds] + [max(r.rounds) for r in rows if r.rounds])
    unit = contest.category.unit
    title = f"{contest.name} - {contest.category.name}" + (" - juniors" if juniors_only else "")
    head = f"{'Pl':>3}  {'No':>3}  {'Name':<30} {'Ctry':<4}" + "".join(f"{'R' + str(i):>8}" for i in range(1, nrounds + 1))
    head += f"{'Best':>9}"
    lines = [title, contest.date, "", head, "-" * len(head)]
    for r in rows:
        pl = f"{r.place:>3}" if r.place else "   "
        name = r.name + (" (J)" if r.junior and not juniors_only else "")
        lines.append(f"{pl}  {r.competitor:>3}  {name[:30]:<30} {r.country[:4]:<4}"
                     + "".join(f"{_speed(r.rounds.get(i)):>8}" for i in range(1, nrounds + 1))
                     + f"{_speed(r.best):>9}")
    lines += ["", f"Speeds in {unit}. C = cancelled flight (4.1.15). Ties: 2nd, then 3rd best speed (4.1.18)."]
    tp = teams(contest) if not juniors_only else []
    if tp:
        lines += ["", "TEAMS", f"{'Pl':>3}  {'Team':<20}{'Total':>10}  Members (best speed, place)"]
        for t in tp:
            members = ", ".join(f"{m.name} {_speed(m.best)} ({m.place})" for m in t.members)
            lines.append(f"{t.place:>3}  {t.team:<20}{t.total:>10.1f}  {members}")
    return "\n".join(lines) + "\n"


def html_page(contest: Contest, juniors_only: bool = False) -> str:
    """A self-contained page that prints on one A4 sheet per ~40 competitors."""
    rows = individual(contest, juniors_only)
    nrounds = max([contest.rounds] + [max(r.rounds) for r in rows if r.rounds])
    e = html.escape
    title = f"{contest.name} – {contest.category.name}" + (" – juniors" if juniors_only else "")
    th = "".join(f"<th>R{i}</th>" for i in range(1, nrounds + 1))
    body = []
    for r in rows:
        best_round = max(r.rounds, key=r.rounds.get) if r.rounds else None
        tds = "".join(
            f"<td class=n>{'<b>' if i == best_round else ''}{_speed(r.rounds.get(i))}{'</b>' if i == best_round else ''}</td>"
            for i in range(1, nrounds + 1))
        jun = " <small>J</small>" if r.junior and not juniors_only else ""
        body.append(f"<tr><td class=n>{r.place or ''}</td><td class=n>{r.competitor}</td>"
                    f"<td>{e(r.name)}{jun}</td><td>{e(r.country)}</td>{tds}<td class=n><b>{_speed(r.best)}</b></td></tr>")
    team_html = ""
    tp = teams(contest) if not juniors_only else []
    if tp:
        trs = "".join(
            f"<tr><td class=n>{t.place}</td><td>{e(t.team)}</td><td class=n><b>{t.total:.1f}</b></td>"
            f"<td>{e(', '.join(f'{m.name} {_speed(m.best)}' for m in t.members))}</td></tr>" for t in tp)
        team_html = f"<h2>Teams</h2><table><tr><th>Pl</th><th>Team</th><th>Total</th><th>Members</th></tr>{trs}</table>"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{e(title)}</title>
<style>
body {{ font: 11pt/1.35 system-ui, sans-serif; margin: 2em; color: #000; background: #fff; }}
h1 {{ font-size: 16pt; margin: 0; }} h2 {{ font-size: 13pt; margin-top: 1.5em; }}
p.sub {{ margin: .2em 0 1em; color: #444; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #ccc; padding: .25em .5em; text-align: left; }}
th {{ border-bottom: 2px solid #000; }}
td.n, th:not(:nth-child(3)):not(:nth-child(4)) {{ text-align: right; font-variant-numeric: tabular-nums; }}
footer {{ margin-top: 1.5em; font-size: 9pt; color: #444; }}
@page {{ size: A4; margin: 15mm; }} @media print {{ body {{ margin: 0; }} }}
</style></head><body>
<h1>{e(title)}</h1><p class=sub>{e(contest.date)}</p>
<table><tr><th>Pl</th><th>No</th><th>Name</th><th>Country</th>{th}<th>Best</th></tr>
{''.join(body)}</table>
{team_html}
<footer>Speeds in {e(contest.category.unit)}, best flight in bold. C = cancelled flight (FAI 4.1.15).
Ties are separated by the second, then third best speed (4.1.18).</footer>
</body></html>
"""
