"""Tests for the instrument auto-detection."""

import pytest

from drivers.detect import identify, scan_for_instruments
from drivers.hp4284a import HP4284A
from drivers.keithley2410 import Keithley2410
from drivers.keithley6487 import Keithley6487


class FakeScanSession:
    """Session that answers *IDN? from a per-resource table."""

    def __init__(self, idn):
        self._idn = idn

    def query(self, command):
        return self._idn if command == "*IDN?" else ""

    def close(self):
        pass


def test_identify_models():
    assert identify("KEITHLEY INSTRUMENTS INC., MODEL 2410, 123456, C33") == "hvps"
    assert identify("KEITHLEY INSTRUMENTS INC., MODEL 6487, 154987, B11") == "pico"
    assert identify("HEWLETT-PACKARD,4284A,0,A.01.13") == "lcr"
    assert identify("Prologix GPIB-USB Controller version 6.107") is None
    assert identify("") is None
    assert identify(None) is None


def test_scan_finds_and_maps_all_instruments():
    candidates = [
        "ASRL/dev/ttyS0::INSTR",
        "ASRL/dev/ttyS1::INSTR",
        "GPIB0::17::INSTR",
        "ASRL/dev/ttyUSB0::INSTR",  # no instrument here
    ]
    idns = {
        "ASRL/dev/ttyS0::INSTR": "KEITHLEY INSTRUMENTS INC., MODEL 2410, 1, C33",
        "ASRL/dev/ttyS1::INSTR": "KEITHLEY INSTRUMENTS INC., MODEL 6487, 2, B11",
        "GPIB0::17::INSTR": "HEWLETT-PACKARD,4284A,0,A.01.13",
        "ASRL/dev/ttyUSB0::INSTR": "",
    }

    def factory(resource, baud=9600, timeout=5.0, parity="none"):
        return FakeScanSession(idns[resource])

    found, missing = scan_for_instruments(candidates, session_factory=factory)

    assert found["hvps"]["resource"] == "ASRL/dev/ttyS0::INSTR"
    assert found["pico"]["resource"] == "ASRL/dev/ttyS1::INSTR"
    assert found["lcr"]["resource"] == "GPIB0::17::INSTR"
    assert missing == []


def test_scan_skips_unopenable_ports():
    candidates = ["ASRL/dev/ttyS0::INSTR", "ASRL/dev/ttyS1::INSTR"]
    idns = {
        "ASRL/dev/ttyS0::INSTR": "KEITHLEY INSTRUMENTS INC., MODEL 2410, 1, C33",
        "ASRL/dev/ttyS1::INSTR": "KEITHLEY INSTRUMENTS INC., MODEL 6487, 2, B11",
    }

    def factory(resource, baud=9600, timeout=5.0, parity="none"):
        if resource == "ASRL/dev/ttyS0::INSTR":
            raise RuntimeError("Permission denied")
        return FakeScanSession(idns[resource])

    found, missing = scan_for_instruments(candidates, session_factory=factory)

    assert "hvps" not in found            # unopenable port was skipped
    assert found["pico"]["resource"] == "ASRL/dev/ttyS1::INSTR"
    assert missing == ["hvps", "lcr"]


def test_scan_reports_unrecognized_instruments():
    candidates = ["GPIB0::5::INSTR"]

    def factory(resource, baud=9600, timeout=5.0, parity="none"):
        return FakeScanSession("KEITHLEY INSTRUMENTS INC., MODEL 6517, 3, A10")

    found, missing = scan_for_instruments(candidates, session_factory=factory)
    assert found == {}
    assert missing == ["hvps", "pico", "lcr"]


def test_connect_autodetects_baud_and_parity():
    """The 2410 may be configured away from 9600/none (e.g. 19200/even)."""
    idn2410 = "KEITHLEY INSTRUMENTS INC., MODEL 2410, 1, C33"

    class FakeBaudSession:
        def __init__(self, baud, parity):
            self.baud, self.parity = baud, parity
            self.commands = []

        def write(self, command):
            self.commands.append(command)

        def query(self, command):
            self.commands.append(command)
            if command == "*IDN?":
                if (self.baud, self.parity) == (19200, "even"):
                    return idn2410
                raise RuntimeError("timeout expired")
            return "1"

        def close(self):
            pass

    created = {}

    def factory(resource, baud=9600, timeout=5.0, parity="none"):
        session = FakeBaudSession(baud, parity)
        created["session"] = session
        return session

    driver = Keithley2410.connect("ASRL/dev/ttyUSB0::INSTR",
                                  session_factory=factory)
    assert created["session"].baud == 19200
    assert created["session"].parity == "even"
    assert "*RST" in created["session"].commands  # safety setup applied


def test_connect_rejects_wrong_instrument():
    class FakeSession:
        def write(self, command):
            pass

        def query(self, command):
            return "KEITHLEY INSTRUMENTS INC., MODEL 6487, 2, B11"

        def close(self):
            pass

    with pytest.raises(Exception, match="Model 2410"):
        Keithley2410.connect("ASRL/dev/ttyUSB1::INSTR",
                             session_factory=lambda r, **kw: FakeSession())

    with pytest.raises(Exception, match="4284A"):
        HP4284A.connect("GPIB0::17::INSTR",
                        session_factory=lambda r, **kw: FakeSession())
