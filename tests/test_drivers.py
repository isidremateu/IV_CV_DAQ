import pytest

from tests.fakes import FakeSession

from drivers.base import InstrumentError, parse_scpi_float
from drivers.hp4284a import HP4284A
from drivers.keithley2410 import Keithley2410
from drivers.keithley6487 import Keithley6487


def test_setup_rejected_command_is_reported():
    """A command rejected by the instrument raises, naming the command."""
    s = FakeSession("ke2410")
    s.responses[":SYST:ERR?"] = '-102,"Syntax error"'
    d = Keithley2410(s)
    with pytest.raises(InstrumentError, match=":SOUR:FUNC VOLT"):
        d.setup(compliance=1e-6, autorange=True, autorange_llimit=1e-6,
                fixed_range=1e-6)


def test_parse_scpi_float_variants():
    assert parse_scpi_float("+1.23E-06") == 1.23e-6
    assert parse_scpi_float("N,+1.23E-06,+0.000E+00") == 1.23e-6
    assert parse_scpi_float("  0.5 , 3 ") == 0.5


def test_2410_setup_and_voltage():
    s = FakeSession("ke2410")
    d = Keithley2410(s)
    d.setup(compliance=5e-7, autorange=True, autorange_llimit=1e-9,
            fixed_range=2e-6)
    joined = ";".join(s.commands)
    assert ":SOUR:FUNC VOLT" in joined
    assert ":SOUR:VOLT:RANG 1000" in joined
    assert ':SENS:FUNC "CURR"' in joined
    # the 2400 response elements are CURR/VOLT/RES/... ('READ' is the 6487's
    # nomenclature and triggers a -102 syntax error)
    assert ":FORM:ELEM CURR" in joined
    assert ":SENS:CURR:PROT:LEV 5.000000e-07" in joined
    assert ":SENS:CURR:RANG:AUTO ON" in joined
    assert ":SENS:CURR:RANG:AUTO:LLIM 1.000000e-09" in joined
    assert ":OUTP OFF" in joined

    d.set_voltage(-42.5)
    assert ":SOUR:VOLT:LEV -4.250000e+01" in s.commands
    assert "*OPC?" in s.commands  # synchronization query after set
    assert d.get_voltage() == -42.5


def test_2410_fixed_range_when_not_autorange():
    s = FakeSession("ke2410")
    d = Keithley2410(s)
    d.setup(compliance=1e-6, autorange=False, autorange_llimit=1e-9,
            fixed_range=2e-6)
    joined = ";".join(s.commands)
    assert ":SENS:CURR:RANG:AUTO OFF" in joined
    assert ":SENS:CURR:RANG 2.000000e-06" in joined


def test_6487_setup_full():
    s = FakeSession("ke6487")
    d = Keithley6487(s)
    d.setup(autorange=True, autorange_llimit=2e-9, fixed_range=2e-6,
            nplc=5.0, damping=True, median_on=True, median_rank=3,
            filter_on=True, filter_type="repeating", filter_count=20)
    joined = ";".join(s.commands)
    assert ":SENS:CURR:NPLC 5" in joined
    assert ":SENS:CURR:DAMP ON" in joined
    assert ":SENS:CURR:MED:STAT ON" in joined
    assert ":SENS:CURR:MED:RANK 3" in joined
    assert ":SENS:CURR:AVER:STAT ON" in joined
    assert ":SENS:CURR:AVER:TCON REP" in joined
    assert ":SENS:CURR:AVER:COUN 20" in joined
    assert ":SENS:CURR:RANG:AUTO:LLIM 2.000000e-09" in joined
    assert ":SYST:ZCH OFF" in joined  # zero check off while measuring


def test_6487_read():
    s = FakeSession("ke6487")
    d = Keithley6487(s)
    s.responses[":READ?"] = "+1.2345E-09"
    assert d.read_current() == 1.2345e-9


def test_4284a_setup_fixed_configuration():
    s = FakeSession("hp4284a")
    d = HP4284A(s)
    d.setup(frequency=1e4, aper="medium", level=1.0)
    joined = ";".join(s.commands)
    assert ":FUNC:IMP CPG" in joined          # parallel Cp-G
    assert ":FREQ 1.000000e+04" in joined
    assert ":VOLT 1.000000e+00" in joined
    assert ":APER MED" in joined
    assert ":TRIG:SOUR BUS" in joined
    assert ":BIAS:STAT OFF" in joined         # internal bias off (2410 biases)
    assert ":OUTP:DC:ISOL ON" in joined
    for corr in (":CORR:OPEN:STAT OFF", ":CORR:SHOR:STAT OFF",
                 ":CORR:LOAD:STAT OFF"):
        assert corr in joined


def test_4284a_read_cp_g():
    s = FakeSession("hp4284a")
    d = HP4284A(s)
    s.responses[":TRIG:IMM;:FETC?"] = "1.0500E-09,2.1000E-12,0"
    c, g = d.read()
    assert c == 1.05e-9 and g == 2.1e-12
