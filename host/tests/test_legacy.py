"""Old Transitrace TT data. The log is real flights, anonymised with tools/anonymise_tt_log.py."""

from pathlib import Path

import pytest

from f2atimer.fai import F2A, Ruling
from f2atimer.legacy import import_folder, parse_name, read_category, read_log, read_names

DATA = Path(__file__).parent / "data"
LOG = DATA / "legacy_anon.txt"

F2A_TTC = """FAI-F2A          Category; One word
9                Timed laps count
3600             Speed calculation: divide this by time
km/h             Unit for speed
3                Attempt time in minutes
2                Count-in laps
0                1 if timing starts at release (USA Proto)
340              Maximum speed in used unit
.12              Stopwatch tolerance
1                Roundoff (see manual)
0                Display lap speeds (0) or lap times (1)
21.5 m           Recommended sensor radial distance (in preferred unit)
0                Not used
"""


def test_reads_category(tmp_path):
    p = tmp_path / "F2A.TTC"
    p.write_bytes(F2A_TTC.replace("\n", "\r\n").encode("cp852"))
    assert read_category(p) == F2A


def test_reads_name_registry(tmp_path):
    p = tmp_path / "NNTEST.TXT"
    p.write_bytes("0\tTest cup\r\n12\tPilot Twelve\r\n3\tPilot Three JUN (SVK)\r\n".encode("cp852"))
    assert read_names(p) == ("Test cup", {12: "Pilot Twelve", 3: "Pilot Three JUN (SVK)"})


@pytest.mark.parametrize("raw, name, country, junior", [
    ("Pilot Three JUN (SVK)", "Pilot Three", "SVK", True),
    ("Pilot Four(SVK)", "Pilot Four", "SVK", False),
    ("Gofast, Marlon", "Gofast, Marlon", "", False),
])
def test_parse_name(raw, name, country, junior):
    c = parse_name(raw)
    assert (c.name, c.country, c.junior) == (name, country, junior)


def test_log_parsed():
    flights = read_log(LOG)
    assert len(flights) == 10
    f = flights[-1]
    assert (f.competitor, f.round, f.attempt, f.ruling) == (5, 1, 1, Ruling.ELECTRONIC)
    assert f.timed_laps == (9, 17) and f.eresult == 274.6
    assert f.handle == [(37.7341453, True)]


def test_new_evaluation_reproduces_every_old_result():
    """Start rule, shifts, re-engages, glitched clocks, inserted laps: same laps, time and speed."""
    checked = 0
    for lf in read_log(LOG):
        if not lf.timed_laps or not lf.etime:
            continue
        ev = lf.to_attempt().evaluate(F2A)
        assert (ev.first_lap, ev.last_lap) == lf.timed_laps
        assert ev.time_s == pytest.approx(lf.etime, abs=6e-5)
        assert ev.result == lf.eresult
        checked += 1
    assert checked == 8


def test_genuine_missed_lap_detected():
    lf = next(f for f in read_log(LOG) if f.started.strftime("%H:%M:%S") == "14:24:09")
    assert lf.to_attempt().flight.suspected_missed_laps(F2A) == [15]


def test_import_folder(tmp_path):
    (tmp_path / "TT000103.TXT").write_bytes(LOG.read_bytes())
    (tmp_path / "F2A.TTC").write_bytes(F2A_TTC.encode("cp852"))
    contests = import_folder(tmp_path)
    assert len(contests) == 1
    c = contests[0]
    assert c.category == F2A and len(c.attempts) == 10
    # Pilot 02 has three official flights all logged as round 1: renumbered 1, 2, 3 (but the
    # flight in an actual round 4 and round 2 keep theirs)
    rounds = sorted(a.round for a in c.attempts if a.competitor == 2 and a.result(F2A) is not None)
    assert rounds == [1, 2, 3]
    assert c.official_results()[4] == {1: 0.0}  # cancelled flight scores 0
