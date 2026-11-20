"""Tests for the adaptive-terminator serial session wrapper."""

import pytest

from drivers.session import _AdaptiveTerminationSession


class FakeTimeout(Exception):
    pass


class FakeTerminableSession:
    """Fake pyvisa session that only answers when read_termination matches."""

    def __init__(self, working_term):
        self.working_term = working_term
        self.read_termination = None
        self.commands = []

    def write(self, command):
        self.commands.append(command)

    def query(self, command, delay=None):
        self.commands.append(command)
        if self.read_termination != self.working_term:
            raise FakeTimeout("timeout expired")
        return "KEITHLEY INSTRUMENTS INC., MODEL 2410, 1, C33"

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
