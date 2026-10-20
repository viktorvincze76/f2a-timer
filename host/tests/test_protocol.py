from f2atimer.protocol import Edge, Heartbeat, Hello, parse_line, pulse_command


def test_parses_messages():
    assert parse_line("HELLO f2a-timer 0.1.0") == Hello("0.1.0")
    assert parse_line("E 7 S 1 12345678901") == Edge(7, "S", True, 12345678901)
    assert parse_line("E 8 H 0 5") == Edge(8, "H", False, 5)
    assert parse_line("B 1000000 3") == Heartbeat(1000000, 3)


def test_ignores_garbage():
    for line in ["", "E 1 X 1 5", "E one S 1 5", "B 1", "hello"]:
        assert parse_line(line) is None


def test_pulse_command_format():
    assert pulse_command(1333) == "T 1333 2000\n"
    assert pulse_command(0) == "T 0\n"
