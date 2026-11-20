"""Main application window: settings panels, live plot and run control."""

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from core.engine import MeasurementEngine
from gui import settings_io
from gui.panels import (
    ConnectionsPanel, HVPSPanel, LCRPanel, PicoPanel, SavePanel,
)
from gui.plot_widget import LivePlot


class MeasurementThread(QThread):
    """Runs the engine in the background: connect -> measure -> ramp down -> close."""

    point = Signal(dict)
    message = Signal(str)
    done = Signal(bool, str)

    def __init__(self, mode, hvps_cfg, meas_cfg, run_cfg, resources, sim=False,
                 serial_probes=None):
        super().__init__()
        self.mode = mode
        self.hvps_cfg = hvps_cfg
        self.meas_cfg = meas_cfg
        self.run_cfg = run_cfg
        self.resources = resources
        self.sim = sim
        self.serial_probes = serial_probes
        self._stop = False
        self._drivers = []

    def request_stop(self):
        self._stop = True

    # ------------------------------------------------------------------ run
    def run(self):
        try:
            hvps, meas = self._connect()
            self.message.emit("Instruments connected")
            engine = MeasurementEngine(
                mode=self.mode,
                hvps_cfg=self.hvps_cfg,
                meas_cfg=self.meas_cfg,
                hvps=hvps,
                meas_instrument=meas,
                run_cfg=self.run_cfg,
                resources=self.resources,
                on_point=self.point.emit,
                on_message=self.message.emit,
                should_stop=lambda: self._stop,
            )
            result = engine.run()
            self.done.emit(True, f"Measurement {result['status']}.")
        except Exception as error:  # surface any failure in the GUI
            self.done.emit(False, f"{type(error).__name__}: {error}")
        finally:
            for driver in self._drivers:
                try:
                    driver.close()
                except Exception:
                    pass

    def _connect(self):
        if self.sim:
            from drivers.keithley2410 import Keithley2410
            from drivers.keithley6487 import Keithley6487
            from drivers.hp4284a import HP4284A
            from drivers.sim import SimSession

            hvps_sim = SimSession("ke2410")
            hvps = Keithley2410(hvps_sim)
            self._drivers.append(hvps)
            if self.mode == "iv":
                meas = Keithley6487(SimSession("ke6487", voltage_source=hvps_sim))
            else:
                meas = HP4284A(SimSession("hp4284a", voltage_source=hvps_sim))
            self._drivers.append(meas)
            return hvps, meas

        from drivers.keithley2410 import Keithley2410
        from drivers.session import open_session

        hvps = Keithley2410.connect(self.resources["hvps"], timeout=5.0,
                                    serial_probes=self.serial_probes)
        self._drivers.append(hvps)
        if self.mode == "iv":
            from drivers.keithley6487 import Keithley6487
            meas = Keithley6487.connect(self.resources["pico"], timeout=5.0,
                                        serial_probes=self.serial_probes)
        else:
            from drivers.hp4284a import HP4284A
            meas = HP4284A.connect(self.resources["lcr"], timeout=10.0)
        self._drivers.append(meas)
        return hvps, meas


class DetectThread(QThread):
    """Scans the buses for the three instruments (runs in the background)."""

    progress = Signal(str)
    done = Signal(dict, str)  # found {key: {resource, idn}}, summary message

    def __init__(self, sim=False, serial_probes=None):
        super().__init__()
        self.sim = sim
        self.serial_probes = serial_probes

    def run(self):
        if self.sim:
            found = {key: {"resource": f"SIM::{key}", "idn": "SIMULATED"}
                     for key in ("hvps", "pico", "lcr")}
            self.done.emit(found, "Simulation mode: simulated instruments selected.")
            return
        from drivers.detect import scan_for_instruments
        try:
            found, missing = scan_for_instruments(
                progress=self.progress.emit, serial_probes=self.serial_probes)
        except Exception as error:
            self.done.emit({}, f"Instrument scan failed: {error}")
            return
        if found:
            lines = [f"Detected {key}: {info['resource']} ({info['idn']})"
                     for key, info in sorted(found.items())]
            if missing:
                lines.append("Not found: " + ", ".join(missing))
            message = "\n".join(lines)
        else:
            message = ("No instruments detected."
                       + (f" Missing: {', '.join(missing)}." if missing else ""))
        self.done.emit(found, message)


class MainWindow(QMainWindow):
    def __init__(self, sim=False):
        super().__init__()
        self.sim = sim
        self.thread = None
        self.detector = None
        self.setWindowTitle("IV/CV DAQ - silicon sensor probe station"
                            + ("  [SIMULATION]" if sim else ""))

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        # ------------------------------------------------- left: settings
        # The settings column is wrapped in a scroll area so that every field
        # stays reachable regardless of the window size or the selected mode
        # (the picoammeter panel is taller than the LCR panel).
        left_container = QWidget()
        left = QVBoxLayout(left_container)
        left.setContentsMargins(0, 0, 0, 0)
        left_scroll = QScrollArea()
        left_scroll.setWidget(left_container)
        left_scroll.setWidgetResizable(True)
        root.addWidget(left_scroll, stretch=0)

        row = QHBoxLayout()
        row.addWidget(QLabel("Measurement mode"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["iv", "cv"])
        self.mode_combo.currentTextChanged.connect(self._mode_changed)
        row.addWidget(self.mode_combo)
        row.addStretch(1)
        left.addLayout(row)

        self.connections = ConnectionsPanel()
        self.hvps_panel = HVPSPanel()
        self.pico_panel = PicoPanel()
        self.lcr_panel = LCRPanel()
        self.save_panel = SavePanel()
        for panel in (self.connections, self.hvps_panel,
                      self.pico_panel, self.lcr_panel, self.save_panel):
            left.addWidget(panel)
        self.connections.detect_button.clicked.connect(self._detect)
        self._mode_changed(self.mode_combo.currentText())

        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start_measurement)
        self.stop_button = QPushButton("Abort")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._abort)
        left.addWidget(self.start_button)
        left.addWidget(self.stop_button)
        left.addStretch(1)

        self._build_settings_menu()

        # ------------------------------------------------- right: plot + log
        right = QVBoxLayout()
        root.addLayout(right, stretch=1)
        self.plot = LivePlot()
        right.addWidget(self.plot, stretch=3)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        right.addWidget(self.log, stretch=1)

        self._set_running(False)
        self._apply_default_settings_file()

    # ------------------------------------------------------------ UI state
    def _build_settings_menu(self):
        menu = self.menuBar().addMenu("&Settings")
        act_load = QAction("Load settings...", self)
        act_load.setShortcut("Ctrl+O")
        act_load.triggered.connect(self._load_settings_dialog)
        act_save = QAction("Save settings...", self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self._save_settings_dialog)
        act_setdef = QAction("Set current as defaults", self)
        act_setdef.triggered.connect(self._save_defaults)
        act_reset = QAction("Restore built-in defaults", self)
        act_reset.triggered.connect(self._reset_defaults)
        for action in (act_load, act_save, act_setdef, act_reset):
            menu.addAction(action)

    def _load_settings_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load settings", str(settings_io.DEFAULTS_DIR),
            "JSON (*.json);;All files (*)")
        if not path:
            return
        try:
            state = settings_io.load_settings_file(path)
        except Exception as error:
            QMessageBox.critical(self, "Load settings",
                                 f"Could not read '{path}':\n{error}")
            return
        warnings = settings_io.apply_state(self, state)
        self._log(f"Settings loaded from {path}")
        if warnings:
            QMessageBox.warning(self, "Load settings", "\n".join(warnings))

    def _save_settings_dialog(self):
        state, warnings = settings_io.collect_state(self)
        if warnings:
            QMessageBox.warning(self, "Save settings",
                                "Some sections hold invalid values and will "
                                "not be saved:\n" + "\n".join(warnings))
        path, _ = QFileDialog.getSaveFileName(
            self, "Save settings", str(settings_io.DEFAULTS_DIR / "ivcv_settings.json"),
            "JSON (*.json)")
        if not path:
            return
        try:
            settings_io.save_settings_file(path, state)
        except Exception as error:
            QMessageBox.critical(self, "Save settings",
                                 f"Could not write '{path}':\n{error}")
            return
        self._log(f"Settings saved to {path}")

    def _save_defaults(self):
        state, warnings = settings_io.collect_state(self)
        try:
            settings_io.DEFAULTS_DIR.mkdir(parents=True, exist_ok=True)
            settings_io.save_settings_file(settings_io.DEFAULTS_PATH, state)
        except Exception as error:
            QMessageBox.critical(self, "Default settings",
                                 f"Could not write defaults:\n{error}")
            return
        message = f"Current settings stored as defaults ({settings_io.DEFAULTS_PATH})."
        if warnings:
            message += "\nInvalid sections were not stored:\n" + "\n".join(warnings)
        QMessageBox.information(self, "Default settings", message)
        self._log(f"Default settings updated: {settings_io.DEFAULTS_PATH}")

    def _reset_defaults(self):
        warnings = settings_io.apply_state(self, settings_io.built_in_default_state())
        self._log("Built-in default settings restored.")
        if warnings:
            QMessageBox.warning(self, "Restore defaults", "\n".join(warnings))

    def _apply_default_settings_file(self):
        """Apply ~/.ivcv_daq/default_settings.json at startup, if present."""
        if not settings_io.DEFAULTS_PATH.exists():
            return
        try:
            state = settings_io.load_settings_file(settings_io.DEFAULTS_PATH)
        except Exception as error:
            self._log(f"Could not load default settings: {error}")
            return
        warnings = settings_io.apply_state(self, state)
        self._log(f"Default settings loaded from {settings_io.DEFAULTS_PATH}")
        for warning in warnings:
            self._log(f"  {warning}")

    def _mode_changed(self, mode):
        self.pico_panel.setVisible(mode == "iv")
        self.lcr_panel.setVisible(mode == "cv")
        if hasattr(self, "plot"):
            self.plot.set_mode(mode)
            # grow the window if the newly shown panel makes it too small
            hint = self.sizeHint()
            new_size = self.size().expandedTo(hint)
            if new_size != self.size():
                self.resize(new_size)

    def _set_running(self, running: bool):
        for widget in (self.hvps_panel, self.pico_panel, self.lcr_panel,
                       self.save_panel):
            widget.setEnabled(not running)
        self.mode_combo.setEnabled(not running)
        self.connections.set_enabled(not running)
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _log(self, text: str):
        self.log.appendPlainText(text)

    # ------------------------------------------------------------ run flow
    def _detect(self):
        """Scan the buses for the instruments and fill in the resource fields."""
        if self.detector is not None or self.thread is not None:
            return
        try:
            probes = self.connections.serial_probes()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid settings",
                                f"Serial probe settings: {error}")
            return
        self.connections.detect_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self._log("Scanning for instruments (GPIB + serial ports)...")
        self.detector = DetectThread(sim=self.sim, serial_probes=probes)
        self.detector.progress.connect(self._log)
        self.detector.done.connect(self._detect_done)
        self.detector.start()

    def _detect_done(self, found: dict, message: str):
        self._log(message)
        labels = {"hvps": "HVPS (Keithley 2410)",
                  "pico": "Picoammeter (Keithley 6487)",
                  "lcr": "LCR meter (HP 4284A)"}
        for key, info in found.items():
            self.connections.set_resource(key, info["resource"])
            self._log(f"  -> {labels.get(key, key)} set to {info['resource']}")
        self.connections.detect_button.setEnabled(True)
        self.start_button.setEnabled(True)
        self.detector = None

    def start_measurement(self):
        mode = self.mode_combo.currentText()
        try:
            hvps_cfg = self.hvps_panel.get_config()
            meas_cfg = self.pico_panel.get_config() if mode == "iv" \
                else self.lcr_panel.get_config()
            run_cfg = self.save_panel.get_config()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid settings", str(error))
            return

        resources = self.connections.resources()
        if not self.sim:
            missing = [k for k, v in resources.items()
                       if k in ("hvps", "pico" if mode == "iv" else "lcr")
                       and not v]
            if missing:
                QMessageBox.warning(self, "Invalid settings",
                                    f"Missing resource string(s): {missing}")
                return
        try:
            serial_probes = self.connections.serial_probes()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid settings",
                                f"Serial probe settings: {error}")
            return

        self.plot.set_mode(mode)
        self.log.clear()
        self._log(f"Starting {mode.upper()} measurement"
                  + (" (simulation)" if self.sim else ""))
        self._set_running(True)

        self.thread = MeasurementThread(mode, hvps_cfg, meas_cfg, run_cfg,
                                        resources, sim=self.sim,
                                        serial_probes=serial_probes)
        self.thread.point.connect(self.plot.add_point)
        self.thread.message.connect(self._log)
        self.thread.done.connect(self._finished)
        self.thread.start()

    def _abort(self):
        if self.thread is not None:
            self._log("Abort requested: ramping down...")
            self.thread.request_stop()

    def _finished(self, ok: bool, message: str):
        self._log(message)
        self._set_running(False)
        self.thread = None
        if not ok:
            QMessageBox.critical(self, "Measurement failed", message)

    def closeEvent(self, event):
        if self.thread is not None:
            self.thread.request_stop()
            self.thread.wait(120000)  # wait for a safe ramp-down
        if self.detector is not None:
            self.detector.wait(60000)
        super().closeEvent(event)


def run_app(sim=False):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(sim=sim)
    window.resize(1300, 950)
    window.show()
    return app.exec()
