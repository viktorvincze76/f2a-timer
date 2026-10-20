"""Connections that yield protocol lines: the real device over USB, or a simulator."""

from __future__ import annotations

from collections.abc import Iterator

PICO_USB_VID = 0x2E8A  # Raspberry Pi


def find_port() -> str:
    from serial.tools import list_ports

    ports = [p.device for p in list_ports.comports() if p.vid == PICO_USB_VID]
    if not ports:
        raise RuntimeError("No Pico found on USB. Is it plugged in and running the firmware?")
    if len(ports) > 1:
        raise RuntimeError(f"Several Picos found ({', '.join(ports)}); pick one with --port")
    return ports[0]


class SerialDevice:
    def __init__(self, port: str | None = None):
        import serial

        self.port = port or find_port()
        # The Pico ignores the baud rate on USB; timeout keeps reads interruptible.
        self._serial = serial.Serial(self.port, 115200, timeout=0.5)
        self.send("?\n")

    def send(self, command: str) -> None:
        self._serial.write(command.encode("ascii"))

    def lines(self) -> Iterator[str]:
        while True:
            raw = self._serial.readline()
            if raw:
                yield raw.decode("ascii", errors="replace").strip()

    def close(self) -> None:
        self._serial.close()
