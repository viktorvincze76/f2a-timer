import pytest

from f2atimer.fai import F2A, Category, Flight, IrregularLapsError, manual_time

LAP = 1_333_333  # ~300 km/h


def steady(n, lap=LAP, t0=0):
    return [t0 + i * lap for i in range(n + 1)]


def test_timing_starts_two_laps_after_engage():
    # engage just after pass 3: first pass after it is pass 4, count-in 2 -> timing from pass 6
    fl = Flight(steady(20), [(3 * LAP + 1000, True)])
    ev = fl.evaluate()
    assert (ev.first_lap, ev.last_lap) == (7, 15)
    assert ev.time_s == pytest.approx(9 * LAP / 1e6)
    assert ev.result == 300.0


def test_last_engage_counts():
    fl = Flight(steady(25), [(2 * LAP + 5, True), (3 * LAP + 5, False), (8 * LAP + 5, True)])
    assert fl.evaluate().first_lap == 12


def test_result_truncated_not_rounded():
    # 13.1062 s -> 274.678 km/h -> 274.6 (FAI 4.1.17: nearest lower 1/10)
    assert F2A.round_result(3600 / 13.1062) == 274.6
    assert Category(roundoff=2).round_result(3600 / 13.1062) == 274.7
    assert F2A.round_result(300.0) == 300.0
    assert F2A.round_result(3600 / 12.0) == 300.0


def test_not_completed_and_not_started():
    assert Flight(steady(8), [(1, True)]).evaluate().status == "not completed"
    assert Flight(steady(20), []).evaluate().status == "not started"


def test_shift_moves_timed_laps():
    fl = Flight(steady(20), [(3 * LAP + 1000, True)], shift=-1)
    assert fl.evaluate().first_lap == 6


def test_handle_released_during_run_is_flagged():
    fl = Flight(steady(20), [(LAP // 2, True), (8 * LAP, False)])
    assert fl.evaluate().handle_released_during_run


def test_missed_lap_reported_not_changed():
    passes = steady(6) + [8 * LAP + i * LAP for i in range(10)]  # pass 7 missing
    fl = Flight(passes, [(LAP // 2, True)])
    assert fl.suspected_missed_laps() == [7]
    before = fl.evaluate()
    assert before.time_s == pytest.approx(10 * LAP / 1e6)  # wrong until the judge decides
    fl.insert_missed_lap(7)
    after = fl.evaluate()
    assert after.result == 300.0
    assert after.inserted_laps_in_run == (7,)
    assert fl.passes_us == passes  # raw data untouched


def test_landing_laps_are_not_missed_laps():
    passes = steady(14) + [14 * LAP + int(LAP * f) for f in (1.4, 3.1, 5.6)]  # slowing down
    assert Flight(passes, [(LAP // 2, True)]).suspected_missed_laps() == []


def test_irregular_lap_is_not_split():
    passes = steady(5) + [5 * LAP + int(1.4 * LAP)] + [int(6.4 * LAP) + i * LAP for i in range(1, 6)]
    with pytest.raises(IrregularLapsError):
        Flight(passes, [(1, True)]).insert_missed_lap(6)


def test_auto_flight_starts_on_first_pass():
    assert Flight(steady(12), auto=True).evaluate().first_lap == 3


def test_course_speed_and_best_run():
    passes = steady(10) + [10 * LAP + int(i * LAP * 0.9) for i in range(1, 10)]
    fl = Flight(passes, [(1, True)])
    assert fl.course_speeds()[9] == pytest.approx(300, abs=0.01)
    first, speed = fl.best_run()
    assert first == 11 and speed == pytest.approx(300 / 0.9, abs=0.01)


# Manual timing, FAI 4.1.17


def test_three_watches_mean():
    mt = manual_time([12.00, 12.06, 12.03])
    assert mt.time_s == pytest.approx(12.03) and not mt.notify_competitor


def test_one_watch_out_of_tolerance_dropped():
    mt = manual_time([12.00, 12.04, 12.30])
    assert mt.time_s == pytest.approx(12.02) and mt.used == (1, 2)


def test_two_watches_out_middle_only():
    mt = manual_time([12.00, 12.20, 12.40])
    assert mt.time_s == 12.20 and mt.notify_competitor


def test_two_backup_watches_disagree_slower_used():
    mt = manual_time([12.00, None, 12.20])
    assert mt.time_s == 12.20 and mt.notify_competitor


def test_mean_not_rounded():
    assert manual_time([12.01, 12.02, None]).time_s == pytest.approx(12.015)
