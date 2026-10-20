import pytest

from f2atimer.simulator import SimulatedDevice
from f2atimer.protocol import Edge, parse_line
from f2atimer.timing import F2A_LAP_M, LapTimer

LAP = 1_333_333  # ~300 km/h


def feed(timer, times):
    for t in times:
        timer.add_pass(t)


def test_speed_of_one_lap():
    timer = LapTimer()
    feed(timer, [0, LAP])
    assert timer.laps[0].speed_kmh(F2A_LAP_M) == pytest.approx(300, abs=0.001)


def test_nine_laps_one_km():
    timer = LapTimer()
    feed(timer, [i * LAP for i in range(10)])
    assert timer.speed_over(1, 9) == pytest.approx(300, abs=0.001)
    assert timer.speed_over(2, 9) is None


def test_stray_pulse_rejected():
    timer = LapTimer()
    feed(timer, [0, LAP, LAP + 400_000, 2 * LAP])
    assert [lap.time_us for lap in timer.laps] == [LAP, LAP]
    assert timer.rejected_us == [LAP + 400_000]


def test_missed_pass_split_keeps_total():
    timer = LapTimer()
    feed(timer, [0, LAP, 2 * LAP, 4 * LAP + 1])
    assert len(timer.laps) == 4
    assert [lap.interpolated for lap in timer.laps] == [False, False, True, True]
    assert sum(lap.time_us for lap in timer.laps) == 4 * LAP + 1


@pytest.mark.parametrize("seed", range(20))
def test_simulated_flight(seed):
    dev = SimulatedDevice(laps=14, realtime=False, seed=seed)
    timer = LapTimer()
    for line in dev.lines():
        msg = parse_line(line)
        if isinstance(msg, Edge) and msg.channel == "S" and msg.active:
            timer.add_pass(msg.t_us)
    assert len(timer.laps) == 14
    assert len(timer.rejected_us) == 1
    assert sum(lap.interpolated for lap in timer.laps) == 2
    assert timer.speed_over(1, 9) == pytest.approx(300, rel=0.01)
