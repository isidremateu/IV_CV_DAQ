"""Fakes for the driver and engine tests (no Qt, no pyvisa needed)."""


class FakeSession:
    """Fake VISA session: records commands, returns canned responses."""

    def __init__(self, kind="fake"):
        self.kind = kind
        self.commands = []
        self.responses = {}
        self.voltage = 0.0
        self.output_on = False

    def write(self, command: str):
        self.commands.append(command)
        cmd = command.strip().upper()
        if cmd.startswith(":SOUR:VOLT:LEV"):
            try:
                self.voltage = float(cmd.split()[-1])
            except ValueError:
                pass
        elif cmd == ":OUTP ON":
            self.output_on = True
        elif cmd == ":OUTP OFF":
            self.output_on = False

    def query(self, command: str, delay=None) -> str:
        self.commands.append(command)
        cmd = command.strip().upper()
        if cmd == "*OPC?":
            return "1"
        if cmd == ":SOUR:VOLT:LEV?":
            return f"{self.voltage:+.6E}"
        return self.responses.get(cmd, "1")

    def close(self):
        pass


# --------------------------------------------------------------------- engine


class FakeHVPS:
    """Driver-level fake for the 2410."""

    def __init__(self, seed=1):
        self.voltage = 0.0
        self.output_on = False
        self.setup_calls = []
        self.set_calls = []
        import random
        self.rng = random.Random(seed)

    def setup(self, compliance, autorange, autorange_llimit, fixed_range):
        self.setup_calls.append({
            "compliance": compliance, "autorange": autorange,
            "llimit": autorange_llimit, "range": fixed_range,
        })

    def output(self, on):
        self.output_on = on

    def set_voltage(self, v):
        self.voltage = v
        self.set_calls.append(v)

    def get_voltage(self):
        return self.voltage

    def read_current(self):
        if abs(self.voltage) > 90:
            i = 1e-6  # simulate compliance region
        else:
            i = 1e-9 * abs(self.voltage)
        return i + self.rng.gauss(0, 1e-11)


class FakePico:
    """Driver-level fake for the 6487; reads the shared voltage reference."""

    def __init__(self, hvps, seed=2):
        self.hvps = hvps
        import random
        self.rng = random.Random(seed)

    def setup(self, **kwargs):
        self.setup_kwargs = kwargs

    def read_current(self):
        return 0.9e-9 * abs(self.hvps.voltage) + self.rng.gauss(0, 1e-12)


class FakeLCR:
    """Driver-level fake for the 4284A; reads the shared voltage reference."""

    def __init__(self, hvps, seed=3):
        self.hvps = hvps
        import random
        self.rng = random.Random(seed)

    def setup(self, frequency, aper, level):
        self.frequency = frequency
        self.aper = aper
        self.level = level

    def read(self):
        import math
        c = 1e-9 / (1.0 + (abs(self.hvps.voltage) / 10.0) ** 3)
        g = c * 1e-3
        return c + self.rng.gauss(0, 1e-13), g
