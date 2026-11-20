"""Measurement engine: ramps the bias voltage, acquires samples, averages and saves.

The engine is plain Python (no Qt) so it can be unit-tested without a GUI.
A GUI worker thread drives it through callbacks and the `should_stop` flag.
"""

import os
import re
import time
from datetime import datetime

import numpy as np

from core.config import MAX_VOLTAGE
from core.data_io import (
    IV_COLUMNS,
    CV_COLUMNS,
    MeasurementFile,
    build_filename,
    build_settings_filename,
    settings_dict,
    write_settings_json,
)
from core.ramps import build_voltages


class SafetyError(RuntimeError):
    """Raised when a safety condition (e.g. compliance) is violated."""


class MeasurementEngine:
    """Runs one IV or CV acquisition.

    Parameters
    ----------
    mode : 'iv' or 'cv'
    hvps_cfg : core.config.HVPSConfig
    meas_cfg : PicoConfig (iv) or LCRConfig (cv)
    hvps : Keithley2410 (or any object with setup/output/set_voltage/
        get_voltage/read_current)
    meas_instrument : Keithley6487 (iv) or HP4284A (cv); objects exposing
        setup(...) and read_current() / read()
    run_cfg : core.config.RunConfig
    resources : dict of resource strings, stored in the settings JSON
    on_point : callback(dict) called after every completed voltage step
    on_message : callback(str) for progress/status messages
    should_stop : callback() -> bool, polled between and within steps
    """

    RAMP_DOWN_STEPS = 10  # number of intermediate points when ramping down

    def __init__(self, mode, hvps_cfg, meas_cfg, hvps, meas_instrument, run_cfg,
                 resources, on_point=None, on_message=None, should_stop=None):
        self.mode = mode
        self.hvps_cfg = hvps_cfg
        self.meas_cfg = meas_cfg
        self.hvps = hvps
        self.meas_instrument = meas_instrument
        self.run_cfg = run_cfg
        self.resources = resources
        self.on_point = on_point or (lambda point: None)
        self.on_message = on_message or (lambda msg: None)
        self.should_stop = should_stop or (lambda: False)

    # ------------------------------------------------------------------ run
    def run(self):
        """Execute the full measurement; returns a result dict."""
        timestamp = datetime.now()
        voltages = build_voltages(self.hvps_cfg)
        polarity = -1.0 if self.hvps_cfg.polarity == "negative" else 1.0

        file_name = build_filename(timestamp, self.run_cfg.identifier, self.mode)
        folder = self.run_cfg.folder
        os.makedirs(folder, exist_ok=True)
        data_path = os.path.join(folder, file_name)
        settings_path = os.path.join(
            folder, build_settings_filename(timestamp, self.run_cfg.identifier, self.mode))

        self._message(f"Saving data to {data_path}")
        write_settings_json(
            settings_path,
            settings_dict(self.mode, self.hvps_cfg, self.meas_cfg, self.run_cfg,
                          self.resources, file_name,
                          os.path.basename(settings_path),
                          timestamp))

        self._message("Configuring instruments")
        compliance = self.hvps_cfg.compliance
        self.hvps.setup(compliance=compliance,
                        autorange=self.hvps_cfg.autorange,
                        autorange_llimit=self.hvps_cfg.autorange_llimit,
                        fixed_range=self.hvps_cfg.range)
        if self.mode == "iv":
            self.meas_instrument.setup(
                autorange=self.meas_cfg.autorange,
                autorange_llimit=self.meas_cfg.autorange_llimit,
                fixed_range=self.meas_cfg.range,
                nplc=self.meas_cfg.nplc,
                damping=self.meas_cfg.damping,
                median_on=self.meas_cfg.median_on,
                median_rank=self.meas_cfg.median_rank,
                filter_on=self.meas_cfg.filter_on,
                filter_type=self.meas_cfg.filter_type,
                filter_count=self.meas_cfg.filter_count)
        else:
            self.meas_instrument.setup(frequency=self.meas_cfg.frequency,
                                       aper=self.meas_cfg.aper,
                                       level=self.meas_cfg.level)

        # report (and clear) instrument-side errors right after configuration,
        # e.g. rejected commands the instruments show on their displays
        for name, instr in (("HVPS", self.hvps),
                            (self.mode.upper(), self.meas_instrument)):
            try:
                err = str(instr.session.query(":SYST:ERR?")).strip()
                if not re.match(r"\s*\+?0\b", err):
                    self._message(f"WARNING {name}: {err}")
            except Exception:
                pass

        columns = IV_COLUMNS if self.mode == "iv" else CV_COLUMNS
        data_file = MeasurementFile(data_path, columns)

        aborted = False
        try:
            self.hvps.output(True)
            self._message("HV output ON")

            previous = 0.0
            for index, v_mag in enumerate(voltages):
                if self.should_stop():
                    aborted = True
                    self._message("Stop requested")
                    break

                target = polarity * v_mag
                self._move(previous, target)
                previous = target

                if self.hvps_cfg.wait_time > 0:
                    time.sleep(self.hvps_cfg.wait_time)

                point = self._measure_at(target)
                data_file.write_row(point_to_row(point, self.mode))
                self.on_point(point)
                self._message(f"Step {index + 1}/{len(voltages)}: "
                              f"V = {target:g} V")

            if not aborted and self.should_stop():
                aborted = True
        finally:
            self._shutdown()
            data_file.close()

        status = "aborted" if aborted else "completed"
        self._message(f"Measurement {status}, file saved: {data_path}")
        return {"aborted": aborted, "data_file": data_path, "status": status}

    # ------------------------------------------------------------- internals
    def _measure_at(self, v_signed) -> dict:
        """Acquire and average one voltage step; returns a point dict."""
        n = max(1, int(self.meas_cfg.averaging))
        pad, cap, cond, tot = [], [], [], []

        for _ in range(n):
            if self.should_stop():
                break
            if self.mode == "iv":
                pad.append(self.meas_instrument.read_current())
            else:
                c, g = self.meas_instrument.read()
                cap.append(c)
                cond.append(g)
            tot.append(self.hvps.read_current())

        if not tot:
            raise SafetyError("Measurement interrupted before any sample")

        point = {
            "voltage": v_signed,
            "voltage_std": 0.0,
            "total_current": float(np.mean(tot)),
            "total_current_std": float(np.std(tot)),
        }
        if self.mode == "iv":
            point["pad_current"] = float(np.mean(pad))
            point["pad_current_std"] = float(np.std(pad))
        else:
            point["capacitance"] = float(np.mean(cap))
            point["capacitance_std"] = float(np.std(cap))
            point["conductance"] = float(np.mean(cond))
            point["conductance_std"] = float(np.std(cond))

        # software compliance supervision (in addition to the 2410 hardware limit)
        if abs(point["total_current"]) > self.hvps_cfg.compliance * 1.05:
            raise SafetyError(
                f"Compliance exceeded at {v_signed:g} V: "
                f"|I| = {abs(point['total_current']):g} A > "
                f"{self.hvps_cfg.compliance:g} A. Ramp-down and abort.")
        return point

    def _move(self, current: float, target: float):
        """Set a new voltage, respecting the configured ramping speed."""
        self.hvps.set_voltage(target)
        dt = abs(target - current) / self.hvps_cfg.ramp_rate
        if dt > 0:
            self._message(f"Ramping {current:g} -> {target:g} V "
                          f"({dt:.1f} s)")
            time.sleep(dt)

    def _shutdown(self):
        """Ramp down to 0 V and switch the output off. Best effort."""
        self._message("Ramping down to 0 V")
        try:
            try:
                current = self.hvps.get_voltage()
            except Exception:
                current = 0.0
            if abs(current) > 1e-9:
                step = current / self.RAMP_DOWN_STEPS
                for i in range(1, self.RAMP_DOWN_STEPS + 1):
                    self.hvps.set_voltage(current - i * step)
                    time.sleep(abs(step) / self.hvps_cfg.ramp_rate)
            self.hvps.output(False)
            self._message("HV output OFF")
        except Exception as error:  # never mask the original error
            self._message(f"WARNING: ramp-down problem: {error}")

    def _message(self, text: str):
        self.on_message(text)


def point_to_row(point: dict, mode: str):
    """Flatten a point dict into the CSV column order."""
    if mode == "iv":
        return [point["voltage"],
                point["pad_current"], point["pad_current_std"],
                point["total_current"], point["total_current_std"]]
    return [point["voltage"],
            point["capacitance"], point["capacitance_std"],
            point["conductance"], point["conductance_std"],
            point["total_current"], point["total_current_std"]]
