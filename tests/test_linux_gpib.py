"""Tests for the direct Linux-GPIB session."""

import sys
import types

import pytest

from drivers.detect import candidate_resources  # noqa: E402
from drivers.linux_gpib import LinuxGpibSession, is_gpib_resource  # noqa: E402


class FakeGpibBindings(types.ModuleType):
    """Fake 'gpib' module (linux-gpib Python bindings)."""

    def __init__(self):
        super().__init__("gpib")
        self.written = []
        self.closed = []
        self.response = b"HEWLETT-PACKARD,4284A,0,A.01.13\r\n"

    def ibdev(self, board, pad, sad, tmo, eot, eos):
        return 7

    def ibwrt(self, handle, data):
        self.written.append(data)

    def ibrd(self, handle, count):
        return self.response

    def ibonl(self, handle, value):
        self.closed.append(handle)


@pytest.fixture
def fake_gpib(monkeypatch):
    fake = FakeGpibBindings()
    monkeypatch.setitem(sys.modules, "gpib", fake)
    return fake


def test_is_gpib_resource():
    assert is_gpib_resource("GPIB0::17::INSTR")
    assert is_gpib_resource("gpib1::5::instr")
    assert not is_gpib_resource("ASRL/dev/ttyS0::INSTR")
    assert not is_gpib_resource("GPIB::INSTR")


def test_session_write_query_close(fake_gpib):
    session = LinuxGpibSession("GPIB0::17::INSTR", timeout=5.0)
    assert session.handle == 7
    response = session.query("*IDN?")
    assert response == "HEWLETT-PACKARD,4284A,0,A.01.13"  # stripped of \r\n
    assert fake_gpib.written[-1] == b"*IDN?"
    session.close()
    assert fake_gpib.closed == [7]


def test_invalid_resource_raises():
    with pytest.raises(ValueError):
        LinuxGpibSession("ASRL/dev/ttyS0::INSTR")


def test_candidate_resources_probes_gpib_addresses(fake_gpib, monkeypatch):
    class FakeManager:
        def __init__(self, backend):
            pass

        def list_resources(self):
            return ["ASRL/dev/ttyUSB0::INSTR"]

    monkeypatch.setattr("pyvisa.ResourceManager", FakeManager)
    candidates = candidate_resources()
    # GPIB addresses 1..30 added for probing when the bindings are available
    assert "GPIB0::17::INSTR" in candidates
    assert "ASRL/dev/ttyUSB0::INSTR" in candidates
