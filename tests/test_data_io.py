import json
import os

from core.data_io import (
    CV_COLUMNS, IV_COLUMNS, MeasurementFile, build_filename,
    build_settings_filename, settings_dict, write_settings_json,
)
from core.config import HVPSConfig, PicoConfig, RunConfig
from datetime import datetime


def test_filename_format():
    ts = datetime(2026, 11, 18, 14, 30, 5)
    assert build_filename(ts, "dev1", "iv") == "261118_143005_dev1_iv.txt"
    assert build_filename(ts, "", "cv") == "261118_143005_cv.txt"
    assert build_settings_filename(ts, "dev1", "iv") == "261118_143005_dev1_iv.json"


def test_measurement_file_incremental(tmp_path):
    path = tmp_path / "data.txt"
    f = MeasurementFile(str(path), IV_COLUMNS)
    f.write_row([0.0, 1e-9, 0.0, 2e-9, 0.0])
    # file on disk already contains the row (flushed per row)
    with open(path) as handle:
        lines = handle.read().strip().splitlines()
    assert len(lines) == 2
    assert lines[0] == "voltage_V,pad_current_A,pad_current_std_A,total_current_A,total_current_std_A"
    assert lines[1] == "0.0,1e-09,0.0,2e-09,0.0"
    f.write_row([10.0, 1.1e-9, 1e-12, 2.1e-9, 1e-12])
    f.close()
    with open(path) as handle:
        assert len(handle.read().strip().splitlines()) == 3


def test_settings_json(tmp_path):
    ts = datetime(2026, 11, 18, 14, 30, 5)
    path = tmp_path / "settings.json"
    settings = settings_dict(
        "iv", HVPSConfig(), PicoConfig(), RunConfig(folder="/tmp", identifier="x"),
        {"hvps": "/dev/ttyS0", "pico": "/dev/ttyS1"}, "data_iv.txt",
        "data_iv.json", ts)
    write_settings_json(str(path), settings)
    loaded = json.loads(path.read_text())
    assert loaded["mode"] == "iv"
    assert loaded["hvps"]["polarity"] == "positive"
    assert loaded["lcr"] is None
    assert loaded["picoammeter"]["nplc"] == 1.0
    assert loaded["run"]["folder"] == "/tmp"


def test_columns():
    assert IV_COLUMNS[0] == "voltage_V" and IV_COLUMNS[-1] == "total_current_std_A"
    assert CV_COLUMNS[1] == "capacitance_F" and CV_COLUMNS[3] == "conductance_S"
