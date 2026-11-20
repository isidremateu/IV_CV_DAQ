"""GUI panels for the HVPS, picoammeter, LCR, saving and connection settings.

The current-range settings are dropdowns restricted to the discrete ranges of
the instruments (from the manuals):
- Keithley 2410 measure ranges (Table 3-1): 1 µA ... 1 A; the autorange lower
  limit accepts values only up to ±105 µA (SCPI command reference), so only
  the 1 µA / 10 µA / 100 µA levels are offered there.
- Keithley 6487 ranges (Table 4-3): 2 nA ... 20 mA.
"""

import math
import os

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from core.config import (
    APERTURES, FILTER_TYPES, HVPSConfig, LCRConfig, PicoConfig, RunConfig,
    POLARITIES, RAMP_TYPES,
)

# (label, command value in A) - Keithley 2410, Table 3-1 of the user manual
HVPS_MEASURE_RANGES = [
    ("1 µA", 1e-6), ("10 µA", 1e-5), ("100 µA", 1e-4), ("1 mA", 1e-3),
    ("20 mA", 2e-2), ("100 mA", 1e-1), ("1 A", 1.0),
]
# the 2410 autorange lower limit command accepts only values up to ±105 µA
HVPS_AUTORANGE_LLIMITS = [
    ("1 µA", 1e-6), ("10 µA", 1e-5), ("100 µA", 1e-4),
]
# (label, command value in A) - Keithley 6487, Table 4-3 of the reference manual
PICO_RANGES = [
    ("2 nA", 2e-9), ("20 nA", 2e-8), ("200 nA", 2e-7), ("2 µA", 2e-6),
    ("20 µA", 2e-5), ("200 µA", 2e-4), ("2 mA", 2e-3), ("20 mA", 2e-2),
]
LCR_FREQUENCY_MIN = 20.0    # Hz, HP 4284A limits (FREQuency command)
LCR_FREQUENCY_MAX = 1e6     # Hz
LCR_COMMON_FREQUENCIES = ["20", "100", "1000", "10000", "100000", "1000000"]


def _range_combo(levels, current: float) -> QComboBox:
    """Dropdown of discrete instrument ranges (labels + values in amps)."""
    box = QComboBox()
    for label, value in levels:
        box.addItem(label, float(value))
    _select_nearest(box, current)
    return box


def _select_nearest(box: QComboBox, value: float):
    """Select the entry whose value is closest to `value` (log distance)."""
    if box.count() == 0:
        return
    value = max(float(value), 1e-30)
    best = min(range(box.count()),
               key=lambda i: abs(math.log10(max(box.itemData(i), 1e-30))
                                 - math.log10(value)))
    box.setCurrentIndex(best)


class FloatField(QLineEdit):
    """Line edit for scientific-notation float values (e.g. '1e-6')."""

    def __init__(self, value: float, parent=None):
        super().__init__(f"{value:g}", parent)

    def get(self, name: str) -> float:
        try:
            value = float(self.text().replace(",", "."))
        except ValueError:
            raise ValueError(f"{name}: '{self.text()}' is not a valid number")
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{name}: invalid number")
        return value


def _float_row(label: str, value: float, unit: str = ""):
    row = QHBoxLayout()
    row.addWidget(_label(label))
    field = FloatField(value)
    if unit:
        field.setPlaceholderText(unit)
    row.addWidget(field)
    return row, field


def _label(text):
    return QLabel(text)


def _double_spin(value, lo, hi, decimals, unit=""):
    box = QDoubleSpinBox()
    box.setRange(lo, hi)
    box.setDecimals(decimals)
    box.setValue(value)
    if unit:
        box.setSuffix(f" {unit}")
    return box


class HVPSPanel(QGroupBox):
    """Keithley 2410: bias ramp and total-current measurement settings."""

    def __init__(self, parent=None):
        super().__init__("HVPS - Keithley 2410", parent)
        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(_label("Polarity"))
        self.polarity = QComboBox()
        self.polarity.addItems(POLARITIES)
        row.addWidget(self.polarity)
        lay.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(_label("Ramp type"))
        self.ramp_type = QComboBox()
        self.ramp_type.addItems(RAMP_TYPES)
        row.addWidget(self.ramp_type)
        lay.addLayout(row)

        row, self.v_start = _float_row("Voltage start [V]", 0.0)
        lay.addLayout(row)
        row, self.v_end = _float_row("Voltage end [V]", 100.0)
        lay.addLayout(row)
        lay.addWidget(_label("start and end are both included in the ramp"))

        row = QHBoxLayout()
        row.addWidget(_label("Number of steps"))
        self.n_steps = QSpinBox()
        self.n_steps.setRange(2, 100000)
        self.n_steps.setValue(11)
        row.addWidget(self.n_steps)
        lay.addLayout(row)

        # ramp file selection (from-file mode)
        row = QHBoxLayout()
        self.ramp_file = QLineEdit()
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_file)
        row.addWidget(self.ramp_file)
        row.addWidget(browse)
        self.file_row = row
        lay.addLayout(row)
        self.ramp_type.currentTextChanged.connect(self._update_enabled)
        self._update_enabled()

        row, self.ramp_rate = _float_row("Ramping speed [V/s]", 10.0)
        lay.addLayout(row)
        row, self.wait_time = _float_row("Wait time [s]", 1.0)
        lay.addLayout(row)
        row, self.compliance = _float_row("Current compliance [A]", 1e-6)
        lay.addLayout(row)

        self.autorange = QCheckBox("Current measurement autorange")
        self.autorange.setChecked(True)
        self.autorange.toggled.connect(self._update_enabled)
        lay.addWidget(self.autorange)
        row = QHBoxLayout()
        row.addWidget(_label("Autorange low limit [A]"))
        self.autorange_llimit = _range_combo(HVPS_AUTORANGE_LLIMITS, 1e-6)
        row.addWidget(self.autorange_llimit)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(_label("Range [A]"))
        self.fixed_range = _range_combo(HVPS_MEASURE_RANGES, 1e-6)
        row.addWidget(self.fixed_range)
        lay.addLayout(row)
        self._update_enabled()

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select voltage list file",
                                              "", "Text files (*.txt);;All files (*)")
        if path:
            self.ramp_file.setText(path)

    def _update_enabled(self):
        is_file = self.ramp_type.currentText() == "file"
        self.ramp_file.setEnabled(is_file)
        for w in (self.v_start, self.v_end, self.n_steps):
            w.setEnabled(not is_file)
        if not hasattr(self, "autorange"):
            return  # panel still being constructed
        auto = self.autorange.isChecked()
        self.autorange_llimit.setEnabled(auto)
        self.fixed_range.setEnabled(not auto)

    def get_config(self) -> HVPSConfig:
        cfg = HVPSConfig()
        cfg.polarity = self.polarity.currentText()
        cfg.ramp_type = self.ramp_type.currentText()
        cfg.v_start = self.v_start.get("Voltage start")
        cfg.v_end = self.v_end.get("Voltage end")
        cfg.n_steps = self.n_steps.value()
        cfg.ramp_file = self.ramp_file.text().strip()
        cfg.ramp_rate = self.ramp_rate.get("Ramping speed")
        cfg.wait_time = self.wait_time.get("Wait time")
        cfg.compliance = self.compliance.get("Current compliance")
        cfg.autorange = self.autorange.isChecked()
        cfg.autorange_llimit = float(self.autorange_llimit.currentData())
        cfg.range = float(self.fixed_range.currentData())
        return cfg

    def set_config(self, cfg: HVPSConfig):
        """Apply a configuration to the widgets."""
        self.polarity.setCurrentText(cfg.polarity)
        self.ramp_type.setCurrentText(cfg.ramp_type)
        self.v_start.setText(f"{cfg.v_start:g}")
        self.v_end.setText(f"{cfg.v_end:g}")
        self.n_steps.setValue(int(cfg.n_steps))
        self.ramp_file.setText(cfg.ramp_file)
        self.ramp_rate.setText(f"{cfg.ramp_rate:g}")
        self.wait_time.setText(f"{cfg.wait_time:g}")
        self.compliance.setText(f"{cfg.compliance:g}")
        self.autorange.setChecked(cfg.autorange)
        _select_nearest(self.autorange_llimit, cfg.autorange_llimit)
        _select_nearest(self.fixed_range, cfg.range)
        self._update_enabled()


class PicoPanel(QGroupBox):
    """Keithley 6487 pad-current settings (IV mode)."""

    def __init__(self, parent=None):
        super().__init__("Picoammeter - Keithley 6487", parent)
        lay = QVBoxLayout(self)

        self.autorange = QCheckBox("Current measurement autorange")
        self.autorange.setChecked(True)
        self.autorange.toggled.connect(self._update_enabled)
        lay.addWidget(self.autorange)
        row = QHBoxLayout()
        row.addWidget(_label("Autorange low limit [A]"))
        self.autorange_llimit = _range_combo(PICO_RANGES, 2e-9)
        row.addWidget(self.autorange_llimit)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(_label("Range [A]"))
        self.fixed_range = _range_combo(PICO_RANGES, 2e-6)
        row.addWidget(self.fixed_range)
        lay.addLayout(row)
        self._llimit_row, self._range_row = row, row

        row = QHBoxLayout()
        row.addWidget(_label("Integration time [PLC]"))
        self.nplc = _double_spin(1.0, 0.01, 50.0, 2)
        row.addWidget(self.nplc)
        lay.addLayout(row)

        self.damping = QCheckBox("Damping")
        lay.addWidget(self.damping)

        self.median_on = QCheckBox("Median filter")
        self.median_on.toggled.connect(self._update_enabled)
        lay.addWidget(self.median_on)
        row = QHBoxLayout()
        row.addWidget(_label("Median rank (window = 2n+1)"))
        self.median_rank = QSpinBox()
        self.median_rank.setRange(1, 5)
        row.addWidget(self.median_rank)
        lay.addLayout(row)

        self.filter_on = QCheckBox("Digital filter")
        self.filter_on.toggled.connect(self._update_enabled)
        lay.addWidget(self.filter_on)
        row = QHBoxLayout()
        row.addWidget(_label("Filter type"))
        self.filter_type = QComboBox()
        self.filter_type.addItems(FILTER_TYPES)
        row.addWidget(self.filter_type)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(_label("Filter samples"))
        self.filter_count = QSpinBox()
        self.filter_count.setRange(2, 100)
        self.filter_count.setValue(10)
        row.addWidget(self.filter_count)
        lay.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(_label("Averaging (samples per step)"))
        self.averaging = QSpinBox()
        self.averaging.setRange(1, 1000)
        self.averaging.setValue(1)
        row.addWidget(self.averaging)
        lay.addLayout(row)

        self._update_enabled()

    def _update_enabled(self):
        auto = self.autorange.isChecked()
        self.autorange_llimit.setEnabled(auto)
        self.fixed_range.setEnabled(not auto)
        self.median_rank.setEnabled(self.median_on.isChecked())
        self.filter_type.setEnabled(self.filter_on.isChecked())
        self.filter_count.setEnabled(self.filter_on.isChecked())

    def get_config(self) -> PicoConfig:
        return PicoConfig(
            autorange=self.autorange.isChecked(),
            autorange_llimit=float(self.autorange_llimit.currentData()),
            range=float(self.fixed_range.currentData()),
            nplc=self.nplc.value(),
            damping=self.damping.isChecked(),
            median_on=self.median_on.isChecked(),
            median_rank=self.median_rank.value(),
            filter_on=self.filter_on.isChecked(),
            filter_type=self.filter_type.currentText(),
            filter_count=self.filter_count.value(),
            averaging=self.averaging.value(),
        )

    def set_config(self, cfg: PicoConfig):
        """Apply a configuration to the widgets."""
        self.autorange.setChecked(cfg.autorange)
        _select_nearest(self.autorange_llimit, cfg.autorange_llimit)
        _select_nearest(self.fixed_range, cfg.range)
        self.nplc.setValue(float(cfg.nplc))
        self.damping.setChecked(cfg.damping)
        self.median_on.setChecked(cfg.median_on)
        self.median_rank.setValue(int(cfg.median_rank))
        self.filter_on.setChecked(cfg.filter_on)
        self.filter_type.setCurrentText(cfg.filter_type)
        self.filter_count.setValue(int(cfg.filter_count))
        self.averaging.setValue(int(cfg.averaging))
        self._update_enabled()


class LCRPanel(QGroupBox):
    """HP 4284A capacitance settings (CV mode)."""

    def __init__(self, parent=None):
        super().__init__("LCR meter - HP 4284A", parent)
        lay = QVBoxLayout(self)
        lay.addWidget(_label("Mode: parallel Cp-G, corrections disabled"))

        row = QHBoxLayout()
        row.addWidget(_label("Frequency [Hz] (20 Hz – 1 MHz)"))
        self.frequency = QComboBox()
        self.frequency.setEditable(True)
        for f in LCR_COMMON_FREQUENCIES:
            self.frequency.addItem(f)
        self.frequency.setCurrentText("10000")
        self.frequency.setInsertPolicy(QComboBox.InsertAtTop)
        row.addWidget(self.frequency)
        lay.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(_label("Integration time"))
        self.aper = QComboBox()
        self.aper.addItems(APERTURES)
        row.addWidget(self.aper)
        lay.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(_label("Voltage level [V]"))
        self.level = _double_spin(1.0, 0.0, 2.0, 3)
        row.addWidget(self.level)
        lay.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(_label("Averaging (samples per step)"))
        self.averaging = QSpinBox()
        self.averaging.setRange(1, 1000)
        self.averaging.setValue(1)
        row.addWidget(self.averaging)
        lay.addLayout(row)

    def get_config(self) -> LCRConfig:
        text = self.frequency.currentText().replace(",", ".")
        try:
            frequency = float(text)
        except ValueError:
            raise ValueError(f"Frequency: '{text}' is not a valid number")
        if not (LCR_FREQUENCY_MIN <= frequency <= LCR_FREQUENCY_MAX):
            raise ValueError(
                f"Frequency [Hz] must be between {LCR_FREQUENCY_MIN:g} Hz and "
                f"{LCR_FREQUENCY_MAX:g} Hz (HP 4284A limit)")
        return LCRConfig(
            frequency=frequency,
            aper=self.aper.currentText(),
            level=self.level.value(),
            averaging=self.averaging.value(),
        )

    def set_config(self, cfg: LCRConfig):
        """Apply a configuration to the widgets."""
        self.frequency.setCurrentText(f"{cfg.frequency:g}")
        self.aper.setCurrentText(cfg.aper)
        self.level.setValue(float(cfg.level))
        self.averaging.setValue(int(cfg.averaging))


class SavePanel(QGroupBox):
    """Output folder and identifier."""

    def __init__(self, parent=None):
        super().__init__("Data saving", parent)
        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        self.folder = QLineEdit(os.path.expanduser("~"))
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        row.addWidget(self.folder)
        row.addWidget(browse)
        lay.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(_label("Identifier"))
        self.identifier = QLineEdit()
        row.addWidget(self.identifier)
        lay.addLayout(row)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select data folder",
                                                self.folder.text())
        if path:
            self.folder.setText(path)

    def get_config(self) -> RunConfig:
        folder = self.folder.text().strip()
        if not folder:
            raise ValueError("Please select a data folder")
        return RunConfig(folder=folder, identifier=self.identifier.text().strip())


class ConnectionsPanel(QGroupBox):
    """Instrument resource strings (editable) plus automatic detection."""

    DEFAULTS = {
        "hvps": "/dev/ttyS0",       # Keithley 2410, RS-232
        "pico": "/dev/ttyS1",       # Keithley 6487, RS-232
        "lcr": "GPIB0::17::INSTR",  # HP 4284A (sample programs use address 717 -> 17)
    }

    def __init__(self, parent=None):
        super().__init__("Connections", parent)
        lay = QVBoxLayout(self)
        self.fields = {}
        for key, label in (("hvps", "Keithley 2410"),
                           ("pico", "Keithley 6487"),
                           ("lcr", "HP 4284A")):
            row = QHBoxLayout()
            row.addWidget(_label(label))
            field = QLineEdit(self.DEFAULTS[key])
            row.addWidget(field)
            lay.addLayout(row)
            self.fields[key] = field

        self.detect_button = QPushButton("Detect instruments")
        self.detect_button.setToolTip(
            "Scan all GPIB addresses and serial ports for the instruments "
            "(each is briefly queried with *IDN?)")
        lay.addWidget(self.detect_button)

        row = QHBoxLayout()
        row.addWidget(_label("Serial line settings to probe"))
        self.serial_probes_field = QLineEdit("19200/even/8")
        self.serial_probes_field.setToolTip(
            "Line settings tried on each serial port during detection and "
            "when connecting: baud/parity/data_bits, several combinations "
            "separated by commas (e.g. '19200/even/8, 9600/none/8'). "
            "Leave empty to probe all combinations supported by the "
            "instruments.")
        row.addWidget(self.serial_probes_field)
        lay.addLayout(row)

    def resources(self) -> dict:
        return {key: field.text().strip() for key, field in self.fields.items()}

    def serial_probes(self):
        """Parsed probe settings; None means 'probe all supported ones'."""
        from drivers.detect import parse_serial_probes
        return parse_serial_probes(self.serial_probes_field.text())

    def probe_text(self) -> str:
        return self.serial_probes_field.text()

    def set_probe_text(self, value):
        self.serial_probes_field.setText(str(value))

    def set_resource(self, key: str, value: str):
        self.fields[key].setText(value)

    def set_enabled(self, enabled: bool):
        for field in self.fields.values():
            field.setEnabled(enabled)
        self.serial_probes_field.setEnabled(enabled)
        self.detect_button.setEnabled(enabled)
