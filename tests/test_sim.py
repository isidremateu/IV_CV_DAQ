"""Tests for the simulated instruments (used by main.py --sim)."""

from drivers.hp4284a import HP4284A
from drivers.keithley2410 import Keithley2410
from drivers.keithley6487 import Keithley6487
from drivers.sim import SimSession


def test_sim_cv_spans_decades_with_bias():
    """The LCR sim must see the voltage applied by the (separate) 2410 sim."""
    hvps_sim = SimSession("ke2410")
    hvps = Keithley2410(hvps_sim)
    lcr = HP4284A(SimSession("hp4284a", voltage_source=hvps_sim))

    hvps.setup(compliance=1e-6, autorange=True, autorange_llimit=1e-9,
               fixed_range=1e-6)
    hvps.output(True)

    c0, _ = lcr.read()
    hvps.set_voltage(100.0)
    c100, _ = lcr.read()
    hvps.set_voltage(200.0)
    c200, _ = lcr.read()

    assert c0 > 5e-10                    # ~1 nF at 0 V
    assert c100 < 5e-12                  # ~1 pF at 100 V
    assert c200 < 5e-13                  # ~0.1 pF at 200 V
    assert c0 / c200 > 1000              # spans several decades


def test_sim_iv_pad_current_follows_bias():
    hvps_sim = SimSession("ke2410", seed=11)
    hvps = Keithley2410(hvps_sim)
    pico = Keithley6487(SimSession("ke6487", seed=12, voltage_source=hvps_sim))

    hvps.set_voltage(50.0)
    i50 = pico.read_current()
    hvps.set_voltage(0.0)
    i0 = pico.read_current()

    assert i50 > 1e-8                    # ~0.9 nA/V * 50 V
    assert abs(i0) < 1e-11               # ~0 at 0 V
