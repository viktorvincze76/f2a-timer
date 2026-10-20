"""Line protocol spoken by the sensor interface firmware (docs/protocol.md)."""

from __future__ import annotations

from dataclasses import dataclass

SENSOR = "S"
HANDLE = "H"


@dataclass(frozen=True)
class Hello:
    version: str


@dataclass(frozen=True)
class Edge:
    seq: int
    channel: str  # SENSOR or HANDLE
    active: bool  # True when a pass starts / the handle is engaged
    t_us: int  # device clock, microseconds since power-up


@dataclass(frozen=True)
class Heartbeat:
    t_us: int
    dropped: int  # events lost because the device queue was full


Message = Hello | Edge | Heartbeat


def parse_line(line: str) -> Message | None:
    """Parse one line from the device. Returns None for anything unrecognised."""
    parts = line.split()
    if not parts:
        return None
    try:
        match parts[0]:
            case "HELLO" if len(parts) == 3:
                return Hello(parts[2])
            case "E" if len(parts) == 5 and parts[2] in (SENSOR, HANDLE):
                return Edge(int(parts[1]), parts[2], parts[3] == "1", int(parts[4]))
            case "B" if len(parts) == 3:
                return Heartbeat(int(parts[1]), int(parts[2]))
    except ValueError:
        pass
    return None


def pulse_command(period_ms: int, width_us: int = 2000) -> str:
    return f"T {period_ms} {width_us}\n" if period_ms else "T 0\n"
