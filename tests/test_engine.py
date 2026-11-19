import csv
import json
import os

from core.config import HVPSConfig, LCRConfig, PicoConfig, RunConfig
from core.engine import MeasurementEngine, SafetyError
from tests.fakes import FakeHVPS, FakeLCR, FakePico


def make_engine(mode, tmp_path, hvps_cfg=None, meas_cfg=None, **kwargs):
    hvps = FakeHVPS()
    if mode == "iv":
        meas_cfg = meas_cfg or PicoConfig(averaging=3)
        meas = FakePico(hvps)
    else:
        meas_cfg = meas_cfg or LCRConfig(averaging=2)
        meas = FakeLCR(hvps)
    hvps_cfg = hvps_cfg or HVPSConfig(v_start=0, v_end=10, n_steps=3,
                                      ramp_rate=1000, wait_time=0)
    engine = MeasurementEngine(
        mode=mode,
        hvps_cfg=hvps_cfg,
        meas_cfg=meas_cfg,
        hvps=hvps,
        meas_instrument=meas,
        run_cfg=RunConfig(folder=str(tmp_path), identifier="test"),
        resources={"hvps": "fake", "pico": "fake", "lcr": "fake"},
        **kwargs)
    return engine, hvps, meas


def test_iv_measurement_runs_and_saves(tmp_path):
    engine, hvps, meas = make_engine("iv", tmp_path)
    points = []
    engine.on_point = points.append
    result = engine.run()

    assert not result["aborted"]
    assert len(points) == 3
    assert points[-1]["voltage"] == 10.0
    assert hvps.output_on is False          # ramped down and off at the end
    assert hvps.get_voltage() == 0.0

    files = os.listdir(tmp_path)
    assert any(f.endswith("_iv.txt") for f in files)
    assert any(f.endswith(".json") for f in files)

    data_file = next(f for f in files if f.endswith("_iv.txt"))
    with open(tmp_path / data_file) as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["voltage_V", "pad_current_A", "pad_current_std_A",
                       "total_current_A", "total_current_std_A"]
    assert len(rows) == 4  # header + 3 steps
    assert float(rows[1][0]) == 0.0
    assert float(rows[-1][0]) == 10.0

    settings = json.loads((tmp_path / next(
        f for f in files if f.endswith(".json"))).read_text())
    assert settings["mode"] == "iv"
    assert settings["picoammeter"]["averaging"] == 3


def test_cv_measurement_runs_and_saves(tmp_path):
    engine, hvps, meas = make_engine("cv", tmp_path,
                                     meas_cfg=LCRConfig(frequency=2e4,
                                                        aper="long",
                                                        level=0.5,
                                                        averaging=2))
    result = engine.run()
    assert not result["aborted"]
    files = os.listdir(tmp_path)
    data_file = next(f for f in files if f.endswith("_cv.txt"))
    with open(tmp_path / data_file) as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["voltage_V", "capacitance_F", "capacitance_std_F",
                       "conductance_S", "conductance_std_S",
                       "total_current_A", "total_current_std_A"]
    assert len(rows) == 4
    # capacitance decreases with bias (depletion)
    assert float(rows[2][1]) > float(rows[-1][1])
    settings = json.loads((tmp_path / next(
        f for f in files if f.endswith(".json"))).read_text())
    assert settings["lcr"]["frequency"] == 2e4
    assert settings["picoammeter"] is None


def test_negative_polarity_applies_sign(tmp_path):
    cfg = HVPSConfig(polarity="negative", v_start=0, v_end=10, n_steps=2,
                     ramp_rate=1000, wait_time=0)
    engine, hvps, _ = make_engine("iv", tmp_path, hvps_cfg=cfg)
    points = []
    engine.on_point = points.append
    engine.run()
    assert points[-1]["voltage"] == -10.0
    assert hvps.get_voltage() == 0.0


def test_abort_ramps_down_and_marks_result(tmp_path):
    engine, hvps, _ = make_engine("iv", tmp_path)
    # request stop after the second point
    count = {"n": 0}

    def should_stop():
        count["n"] += 1
        return count["n"] > 4  # ~2 steps x 2 checks

    engine.should_stop = should_stop
    result = engine.run()
    assert result["aborted"]
    assert hvps.get_voltage() == 0.0
    assert hvps.output_on is False


def test_compliance_violation_raises_and_shuts_down(tmp_path):
    cfg = HVPSConfig(v_start=0, v_end=200, n_steps=3, compliance=1e-8,
                     ramp_rate=1000, wait_time=0)
    engine, hvps, _ = make_engine("iv", tmp_path, hvps_cfg=cfg)
    try:
        engine.run()
        raised = False
    except SafetyError:
        raised = True
    assert raised
    assert hvps.get_voltage() == 0.0   # safe ramp-down happened
    assert hvps.output_on is False
