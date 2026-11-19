"""Simulated instrument sessions, allowing the full application to run without hardware.

Started with:  python main.py --sim

The sessions emulate the handful of commands the drivers actually use and
return plausible physics: diode-like IV curves and a depletion C(V) curve.
"""

import math
import random


class SimSession:
    """Fake VISA session for one instrument.

    kind: 'ke2410' | 'ke6487' | 'hp4284a'
    voltage_source: another SimSession whose applied voltage drives this
    instrument (the 6487/4284a do not set the bias themselves; in the real
    setup the 2410 sources it, so the simulated sessions must share it).
    """

    def __init__(self, kind: str, resource: str = "SIM", seed: int = 1234,
                 voltage_source: "SimSession | None" = None):
        self.kind = kind
        self.resource = resource
        self.voltage = 0.0
        self.voltage_source = voltage_source
        self.output_on = False
        self.frequency = 1e4
        self.log = None  # optional callable(str) to trace the raw I/O
        self._rng = random.Random(seed)

    @property
    def bias_voltage(self) -> float:
        """The bias voltage actually seen by this instrument."""
        if self.voltage_source is not None:
            return self.voltage_source.voltage
        return self.voltage

    # ------------------------------------------------------------------ I/O
    def write(self, command: str):
        self._trace(">>", command)
        cmd = command.strip().upper()

        if cmd.startswith(":SOUR:VOLT:LEV"):
            value = cmd.split()[-1].rstrip("V")
            if value not in ("MAX", "MIN"):
                self.voltage = float(value)
        elif cmd == ":OUTP ON":
            self.output_on = True
        elif cmd == ":OUTP OFF":
            self.output_on = False
        elif cmd.startswith(":FREQ"):
            self.frequency = float(cmd.split()[-1].rstrip("HZ"))
        # every other command is accepted silently

    def query(self, command: str, delay=None) -> str:
        self._trace(">>", command)
        cmd = command.strip().upper()
        response = self._respond(cmd)
        self._trace("<<", response)
        return response

    def close(self):
        pass

    # ------------------------------------------------------------- internals
    def _respond(self, cmd: str) -> str:
        if cmd in ("*OPC?", "*ESR?", "*IDN?"):
            if cmd == "*IDN?":
                return f"SIMULATED,{self.kind},0,1.0"
            return "1"
        if cmd == ":SOUR:VOLT:LEV?":
            return f"{self.voltage:+.6E}"
        if cmd == ":READ?":
            return self._reading()
        if cmd == ":FETC?" or cmd == ":TRIG:IMM;:FETC?":
            return self._lcr_reading()
        return "1"

    def _sensor_current(self) -> float:
        """Diode-like sensor current for the current bias voltage."""
        v = self.bias_voltage
        bulk = 1e-9 * abs(v)                      # ohmic leakage
        breakdown = 1e-8 * math.exp(abs(v) / 40.0) if abs(v) > 60 else 0.0
        noise = self._rng.gauss(0, 0.02 * max(bulk, 1e-12))
        return math.copysign(bulk + breakdown, v if v != 0 else 1) + noise

    def _reading(self) -> str:
        if self.kind == "ke2410":
            return f"{self._sensor_current():+.6E}"
        if self.kind == "ke6487":
            pad = self._sensor_current() * 0.9    # guard ring splits the current
            return f"{pad:+.6E}"
        return "0"

    def _lcr_reading(self) -> str:
        """Depletion-region C(V) spanning several decades for easy log-scale checks."""
        v = abs(self.bias_voltage)
        c = 1e-9 / (1.0 + (v / 10.0) ** 3)      # ~1 nF at 0 V down to ~0.1 pF at 200 V
        c *= 1.0 + self._rng.gauss(0, 0.003)
        g = 2.0 * math.pi * self.frequency * c * 0.001
        return f"{c:.6E},{g:.6E},0"

    def _trace(self, direction: str, text: str):
        if self.log is not None:
            try:
                self.log(f"[{self.kind} {direction}] {text}")
            except Exception:
                pass


def sim_session_factory(resource: str, *, kind: str, baud: int = 9600,
                        timeout: float = 5.0):
    """Drop-in replacement for instruments.session.open_session used in --sim mode."""
    return SimSession(kind, resource=resource)
