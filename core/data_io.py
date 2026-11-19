"""Data-file naming, incremental CSV writing and settings JSON output.

File naming convention (README): YYMMDD_HHMMSS_identifier_[iv/cv].txt,
timestamped at the start of the acquisition.
"""

import csv
import json
import os
from datetime import datetime

IV_COLUMNS = [
    "voltage_V",
    "pad_current_A",
    "pad_current_std_A",
    "total_current_A",
    "total_current_std_A",
]

CV_COLUMNS = [
    "voltage_V",
    "capacitance_F",
    "capacitance_std_F",
    "conductance_S",
    "conductance_std_S",
    "total_current_A",
    "total_current_std_A",
]


def build_filename(timestamp: datetime, identifier: str, mode: str) -> str:
    """YYMMDD_HHMMSS_identifier_[iv/cv].txt, identifier omitted when empty."""
    parts = [timestamp.strftime("%y%m%d_%H%M%S")]
    if identifier:
        parts.append(identifier)
    parts.append(mode)
    return "_".join(parts) + ".txt"


def build_settings_filename(timestamp: datetime, identifier: str, mode: str) -> str:
    """JSON sidecar name matching the data file."""
    return build_filename(timestamp, identifier, mode).replace(".txt", ".json")


class MeasurementFile:
    """CSV file written incrementally: every completed voltage step is flushed to disk."""

    def __init__(self, path: str, columns):
        self.path = path
        self._handle = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._handle)
        self._writer.writerow(columns)
        self._flush()

    def write_row(self, values):
        self._writer.writerow(values)
        self._flush()

    def _flush(self):
        self._handle.flush()
        os.fsync(self._handle.fileno())

    def close(self):
        try:
            self._handle.close()
        except Exception:
            pass


def write_settings_json(path: str, settings: dict):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2, default=str)


def settings_dict(mode, hvps_cfg, meas_cfg, run_cfg, resources, data_file, settings_file,
                  timestamp):
    """Assemble the JSON content saved alongside each measurement."""
    return {
        "mode": mode,
        "timestamp": timestamp.isoformat(),
        "data_file": data_file,
        "settings_file": settings_file,
        "resources": resources,
        "hvps": hvps_cfg.as_dict(),
        "picoammeter": meas_cfg.as_dict() if mode == "iv" else None,
        "lcr": meas_cfg.as_dict() if mode == "cv" else None,
        "run": run_cfg.as_dict(),
    }
