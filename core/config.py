"""Configuration dataclasses shared by the GUI, the measurement engine and the data files."""

from dataclasses import dataclass, asdict

POLARITIES = ("positive", "negative")
RAMP_TYPES = ("linear", "logarithmic", "file")
FILTER_TYPES = ("moving", "repeating")
APERTURES = ("short", "medium", "long")
MODES = ("iv", "cv")

MAX_VOLTAGE = 1000.0  # V, the HVPS is always operated on the 1000 V range


@dataclass
class HVPSConfig:
    """Keithley 2410 settings: bias ramp and total-current measurement."""

    polarity: str = "positive"
    ramp_type: str = "linear"          # linear | logarithmic | file
    v_start: float = 0.0               # V (magnitude, polarity applied later)
    v_end: float = 100.0               # V
    n_steps: int = 11                  # start and end values included
    ramp_file: str = ""                # voltage list file (used when ramp_type == "file")
    ramp_rate: float = 10.0            # V/s, rate of voltage change between steps
    wait_time: float = 1.0             # s, wait after setting a voltage before the first measurement
    compliance: float = 1e-6           # A, maximum current allowed to be sourced
    autorange: bool = True
    autorange_llimit: float = 1e-6     # A, lowest range used in autorange (1 µA range)
    range: float = 1e-6                # A, fixed range when autorange is off (1 µA range)

    def as_dict(self):
        return asdict(self)


@dataclass
class PicoConfig:
    """Keithley 6487 settings (IV mode)."""

    autorange: bool = True
    autorange_llimit: float = 2e-9     # A
    range: float = 2e-6                # A, fixed range when autorange is off
    nplc: float = 1.0                  # integration time, 0.01 to 50 power line cycles
    damping: bool = False
    median_on: bool = False
    median_rank: int = 1               # 1..5 (window = 2*rank + 1)
    filter_on: bool = False            # digital (averaging) filter
    filter_type: str = "moving"        # moving | repeating
    filter_count: int = 10             # 2..100
    averaging: int = 1                 # software average per voltage step

    def as_dict(self):
        return asdict(self)


@dataclass
class LCRConfig:
    """HP 4284A settings (CV mode). Function is fixed to parallel Cp-G, corrections off."""

    frequency: float = 1e4             # Hz, 20 Hz to 1 MHz
    aper: str = "medium"               # short | medium | long
    level: float = 1.0                 # V, AC test level, 0 to 2 V
    averaging: int = 1                 # software average per voltage step

    def as_dict(self):
        return asdict(self)


@dataclass
class RunConfig:
    """Where and how to store the results."""

    mode: str = "iv"                   # iv | cv
    folder: str = ""
    identifier: str = ""

    def as_dict(self):
        return asdict(self)
