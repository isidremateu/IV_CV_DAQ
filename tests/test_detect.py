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

    def factory(resource, **kwargs):
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

    def factory(resource, **kwargs):
        if resource == "ASRL/dev/ttyS0::INSTR":
            raise RuntimeError("Permission denied")
        return FakeScanSession(idns[resource])

    found, missing = scan_for_instruments(candidates, session_factory=factory)

    assert "hvps" not in found            # unopenable port was skipped
    assert found["pico"]["resource"] == "ASRL/dev/ttyS1::INSTR"
    assert missing == ["hvps", "lcr"]


def test_scan_reports_unrecognized_instruments():
    candidates = ["GPIB0::5::INSTR"]

    def factory(resource, **kwargs):
        return FakeScanSession("KEITHLEY INSTRUMENTS INC., MODEL 6517, 3, A10")

    found, missing = scan_for_instruments(candidates, session_factory=factory)
    assert found == {}
    assert missing == ["hvps", "pico", "lcr"]


def test_parse_serial_probes():
    from drivers.detect import parse_serial_probes
    assert parse_serial_probes("") is None
    assert parse_serial_probes(None) is None
    assert parse_serial_probes("19200/even/8") == [(19200, "even", 8)]
    assert parse_serial_probes("19200/even/8, 9600/none/7") == [
        (19200, "even", 8), (9600, "none", 7)]
    with pytest.raises(ValueError):
        parse_serial_probes("123456/even/8")          # invalid baud
    with pytest.raises(ValueError):
        parse_serial_probes("9600/weird/8")           # invalid parity
    with pytest.raises(ValueError):
        parse_serial_probes("9600/even/9")            # invalid data bits
    with pytest.raises(ValueError):
        parse_serial_probes("9600-even-8")            # wrong format


def test_scan_uses_configured_probes():
    candidates = ["ASRL/dev/ttyS0::INSTR"]
    used = []

    def factory(resource, **kwargs):
        used.append(kwargs)
        return FakeScanSession("KEITHLEY INSTRUMENTS INC., MODEL 2410, 1, C33")

    scan_for_instruments(candidates, session_factory=factory,
                         serial_probes=[(19200, "even", 8)])
    assert len(used) == 1
    assert used[0]["baud"] == 19200
    assert used[0]["parity"] == "even"
    assert used[0]["data_bits"] == 8


def test_connect_uses_configured_probes():
    idn2410 = "KEITHLEY INSTRUMENTS INC., MODEL 2410, 1, C33"

    class FakeBaudSession:
        def __init__(self, baud, parity, data_bits):
            self.settings = (baud, parity, data_bits)
            self.commands = []

        def write(self, command):
            self.commands.append(command)

        def query(self, command):
            self.commands.append(command)
            if command == "*IDN?" and self.settings == (19200, "even", 8):
                return idn2410
            raise RuntimeError("timeout expired")

        def close(self):
            pass

    created = {}

    def factory(resource, baud=9600, timeout=5.0, parity="none", data_bits=8):
        session = FakeBaudSession(baud, parity, data_bits)
        created["session"] = session
        return session

    driver = Keithley2410.connect("ASRL/dev/ttyS0::INSTR", session_factory=factory,
                                  serial_probes=[(19200, "even", 8)])
    assert created["session"].settings == (19200, "even", 8)
    assert driver is not None


def test_connect_autodetects_baud_and_parity():
    """The 2410 may be configured away from 9600/none (e.g. 19200/even)."""
    idn2410 = "KEITHLEY INSTRUMENTS INC., MODEL 2410, 1, C33"

    class FakeBaudSession:
        def __init__(self, baud, parity, data_bits):
            self.settings = (baud, parity, data_bits)
            self.commands = []

        def write(self, command):
            self.commands.append(command)

        def query(self, command):
            self.commands.append(command)
            if command == "*IDN?" and self.settings == (19200, "even", 8):
                return idn2410
            raise RuntimeError("timeout expired")

        def close(self):
            pass

    created = {}

    def factory(resource, baud=9600, timeout=5.0, parity="none", data_bits=8):
        session = FakeBaudSession(baud, parity, data_bits)
        created["session"] = session
        return session

    driver = Keithley2410.connect("ASRL/dev/ttyUSB0::INSTR",
                                  session_factory=factory)
    assert created["session"].settings == (19200, "even", 8)
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
