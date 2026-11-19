import numpy as np
import pytest

from core.config import HVPSConfig
from core.ramps import ConfigError, build_voltages, load_voltages_from_file


def test_linear_ramp_includes_start_and_end():
    cfg = HVPSConfig(ramp_type="linear", v_start=0, v_end=100, n_steps=11)
    v = build_voltages(cfg)
    assert len(v) == 11
    assert v[0] == 0 and v[-1] == 100
    assert np.allclose(np.diff(v), 10.0)


def test_log_ramp_equally_spaced_in_log10():
    cfg = HVPSConfig(ramp_type="logarithmic", v_start=1, v_end=1000, n_steps=4)
    v = build_voltages(cfg)
    assert np.allclose(v, [1, 10, 100, 1000])
    logs = np.diff(np.log10(v))
    assert np.allclose(logs, logs[0])


def test_file_ramp_takes_absolute_values(tmp_path):
    path = tmp_path / "ramp.txt"
    path.write_text("-5\n10\n# comment\n-20\n")
    cfg = HVPSConfig(ramp_type="file", ramp_file=str(path))
    assert build_voltages(cfg) == [5.0, 10.0, 20.0]


def test_file_ramp_missing_file():
    cfg = HVPSConfig(ramp_type="file", ramp_file="/nonexistent/ramp.txt")
    with pytest.raises((ConfigError, OSError)):
        build_voltages(cfg)


def test_log_ramp_rejects_zero_start():
    cfg = HVPSConfig(ramp_type="logarithmic", v_start=0, v_end=100)
    with pytest.raises(ConfigError):
        build_voltages(cfg)


def test_rejects_too_few_steps():
    cfg = HVPSConfig(v_start=0, v_end=100, n_steps=1)
    with pytest.raises(ConfigError):
        build_voltages(cfg)


def test_rejects_voltage_over_range():
    cfg = HVPSConfig(v_start=0, v_end=1500, n_steps=10)
    with pytest.raises(ConfigError):
        build_voltages(cfg)


def test_load_file_empty(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("")
    with pytest.raises(ConfigError):
        load_voltages_from_file(path)
