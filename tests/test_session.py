"""Tests for the adaptive-terminator serial session wrapper."""

import pytest

from drivers.session import _AdaptiveTerminationSession


class FakeTimeout(Exception):
    pass


class FakeTerminableSession:
    """Fake pyvisa session that only answers when read_termination matches."""

    def __init__(self, working_term, response="KEITHLEY INSTRUMENTS INC., MODEL 2410, 1, C33"):
        self.working_term = working_term
        self.read_termination = None
        self.commands = []
        self.response = response

    def write(self, command):
        self.commands.append(command)

    def query(self, command, delay=None):
        self.commands.append(command)
        if self.read_termination != self.working_term:
            raise FakeTimeout("timeout expired")
        return self.response

    def close(self):
        pass


def test_adapts_from_lf_to_cr():
    inner = FakeTerminableSession("\r")  # instrument transmits CR-terminated
    session = _AdaptiveTerminationSession(inner)
    assert session.query("*IDN?") == "KEITHLEY INSTRUMENTS INC., MODEL 2410, 1, C33"
    assert session._term == "\r"
    # subsequent queries keep the working terminator, no retries
    assert session.query(":READ?") == "KEITHLEY INSTRUMENTS INC., MODEL 2410, 1, C33"


def test_lf_terminating_instrument_works_first_try():
    inner = FakeTerminableSession("\n")
    session = _AdaptiveTerminationSession(inner)
    assert "MODEL 2410" in session.query("*IDN?")
    assert session._term == "\n"


def test_failure_with_both_terminators_is_raised():
    inner = FakeTerminableSession("\x03")  # nothing works
    session = _AdaptiveTerminationSession(inner)
    with pytest.raises(FakeTimeout):
        session.query("*IDN?")


def test_high_bits_are_masked():
    """Parity bits folded into the data (7E1 instrument, 8N1 reader) are stripped."""
    inner = FakeTerminableSession(
        "\n", response="KEITHLEY INSTRUMENTS INC., MO\xC5EL 2410, 1, C33")
    session = _AdaptiveTerminationSession(inner)
    # 0xC5 = 'E' (odd parity -> parity bit set): masking recovers the 'E'
    assert session.query("*IDN?") == "KEITHLEY INSTRUMENTS INC., MOEEL 2410, 1, C33"


def test_scan_connect_autodetects_data_bits():
    """The scan and connect fall through line settings until the IDN matches."""
    idn2410 = "KEITHLEY INSTRUMENTS INC., MODEL 2410, 1, C33"

    class FakeBaudSession:
        def __init__(self, baud, parity, data_bits):
            self.settings = (baud, parity, data_bits)
            self.commands = []

        def write(self, command):
            self.commands.append(command)

        def query(self, command):
            self.commands.append(command)
            if command == "*IDN?" and self.settings == (9600, "none", 8):
                return idn2410
            raise RuntimeError("timeout expired")

        def close(self):
            pass

    created = {}

    def factory(resource, baud=9600, timeout=5.0, parity="none", data_bits=8):
        session = FakeBaudSession(baud, parity, data_bits)
        created["session"] = session
        return session

    from drivers.keithley2410 import Keithley2410
    driver = Keithley2410.connect("ASRL/dev/ttyS3::INSTR",
                                  session_factory=factory)
    assert created["session"].settings == (9600, "none", 8)
    assert "*RST" in created["session"].commands
