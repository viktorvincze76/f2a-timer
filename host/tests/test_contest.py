import pytest

from f2atimer import results
from f2atimer.contest import Attempt, Competitor, Contest
from f2atimer.fai import F2A, Flight, Ruling

LAP = 1_333_333


def flight_at(speed_kmh: float) -> Flight:
    lap = round(LAP * 300 / speed_kmh)
    return Flight([i * lap for i in range(16)], [(lap // 2, True)])


def add(contest, comp, rnd, speed=None, ruling=Ruling.ELECTRONIC, stopwatches=None):
    a = Attempt(comp, rnd, flight=flight_at(speed or 200))
    if stopwatches:
        a.stopwatches = stopwatches
    a.validate(ruling, contest.category)
    contest.attempts.append(a)
    return a


@pytest.fixture
def contest():
    c = Contest("Test cup", F2A, "2026-05-01", rounds=3)
    for n, name, team in [(1, "Alpha", "A"), (2, "Bravo", "A"), (3, "Charlie", "B"), (4, "Delta", "B"), (5, "Echo", "")]:
        c.competitors[n] = Competitor(n, name, team=team, junior=n == 5)
    return c


def test_validate_freezes_result(contest):
    a = add(contest, 1, 1, 280)
    assert a.recorded_result == 280.0
    a.flight.shift = 3  # a later edit does not silently change a published result
    assert a.result(contest.category) == 280.0


def test_cancelled_counts_as_zero_and_attempt_does_not_count(contest):
    add(contest, 1, 1, 280, Ruling.CANCELLED)
    add(contest, 1, 2, 280, Ruling.ATTEMPT)
    assert contest.official_results() == {1: {1: 0.0}}


def test_manual_result(contest):
    a = add(contest, 1, 1, ruling=Ruling.MANUAL, stopwatches=[12.00, 12.04, 12.30])
    assert a.recorded_result == 299.5  # 3600 / 12.02 = 299.50..., truncated


def test_ranking_and_tie_break(contest):
    add(contest, 1, 1, 280); add(contest, 1, 2, 270)
    add(contest, 2, 1, 280); add(contest, 2, 2, 275)  # same best, better second: ahead of 1
    add(contest, 3, 1, 290, Ruling.CANCELLED); add(contest, 3, 2, 260)
    rows = results.individual(contest)
    assert [(r.place, r.competitor) for r in rows] == [(1, 2), (2, 1), (3, 3)]


def test_exact_tie_shares_place(contest):
    add(contest, 1, 1, 280)
    add(contest, 2, 1, 280)
    rows = results.individual(contest)
    assert [r.place for r in rows[:2]] == [1, 1]


def test_juniors_only(contest):
    add(contest, 1, 1, 280)
    add(contest, 5, 1, 250)
    assert [(r.place, r.competitor) for r in results.individual(contest, juniors_only=True)] == [(1, 5)]


def test_team_classification(contest):
    add(contest, 1, 1, 280); add(contest, 2, 1, 270)  # team A: 550
    add(contest, 3, 1, 300); add(contest, 4, 1, 250)  # team B: 550, places 1+4=5 vs A 2+3=5
    tp = results.teams(contest)
    # equal total and equal place sum: best individual placing decides (B has 1st)
    assert [(t.place, t.team) for t in tp] == [(1, "B"), (2, "A")]


def test_save_load_round_trip(contest, tmp_path):
    add(contest, 1, 1, 280, stopwatches=[12.0, None, 12.1])
    path = tmp_path / "c.json"
    contest.save(path)
    again = Contest.load(path)
    assert again == contest
    assert results.text(again) == results.text(contest)


def test_html_output_escapes_names(contest):
    contest.competitors[1].name = "<script>"
    add(contest, 1, 1, 280)
    page = results.html_page(contest)
    assert "&lt;script&gt;" in page and "<script>" not in page
