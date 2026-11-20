"""Headless tests for saving/loading/defaulting of the GUI settings."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

import gui.settings_io as settings_io  # noqa: E402
from core.config import HVPSConfig, LCRConfig, PicoConfig  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from gui.panels import ConnectionsPanel, HVPSPanel  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    w = MainWindow(sim=True)
    w.show()
    yield w
    w.close()


def test_hvps_panel_roundtrip(app):
    panel = HVPSPanel()
    cfg = HVPSConfig(polarity="negative", ramp_type="logarithmic",
                     v_start=1.0, v_end=500.0, n_steps=25, ramp_rate=33.5,
                     wait_time=0.5, compliance=2.5e-6, autorange=False,
                     autorange_llimit=1e-5, range=1e-4)
    panel.set_config(cfg)
    assert panel.polarity.currentText() == "negative"
    assert panel.ramp_type.currentText() == "logarithmic"
    assert panel.n_steps.value() == 25
    assert not panel.autorange.isChecked()
    assert panel.fixed_range.isEnabled() and not panel.autorange_llimit.isEnabled()
    reloaded = panel.get_config()
    assert reloaded == cfg


def test_collect_and_apply_state(window):
    window.mode_combo.setCurrentText("cv")
    window.hvps_panel.set_config(HVPSConfig(polarity="negative", v_start=1.0,
                                            v_end=123.0, n_steps=7,
                                            ramp_rate=55.0, wait_time=2.0,
                                            compliance=8e-7))
    window.pico_panel.set_config(PicoConfig(nplc=3.0, averaging=5))
    window.lcr_panel.set_config(LCRConfig(frequency=2e4, aper="long",
                                          level=0.5, averaging=3))
    window.save_panel.identifier.setText("roundtrip")

    state, warnings = settings_io.collect_state(window)
    assert warnings == []
    assert state["mode"] == "cv"
    assert state["hvps"]["v_end"] == 123.0
    assert state["pico"]["averaging"] == 5
    assert state["lcr"]["frequency"] == 2e4
    assert state["connections"]["serial_probes"] == "19200/even/8"

    # change everything, then apply the state back
    window.mode_combo.setCurrentText("iv")
    window.hvps_panel.set_config(HVPSConfig())
    window.lcr_panel.set_config(LCRConfig())
    warnings = settings_io.apply_state(window, state)
    assert warnings == []
    assert window.mode_combo.currentText() == "cv"
    assert window.hvps_panel.get_config().v_end == 123.0
    assert window.hvps_panel.get_config().polarity == "negative"
    assert window.lcr_panel.get_config().averaging == 3
    assert window.save_panel.identifier.text() == "roundtrip"
    # both instrument panels stay available regardless of mode
    assert window.pico_panel.get_config().nplc == 3.0


def test_file_roundtrip(window, tmp_path):
    window.hvps_panel.set_config(HVPSConfig(v_end=77.0, n_steps=9,
                                            ramp_rate=12.0, wait_time=0.2,
                                            compliance=3e-6))
    state, _ = settings_io.collect_state(window)
    path = tmp_path / "settings.json"
    settings_io.save_settings_file(path, state)

    # fresh window, load the file into it
    window2 = MainWindow(sim=True)
    loaded = settings_io.load_settings_file(path)
    settings_io.apply_state(window2, loaded)
    assert window2.hvps_panel.get_config().v_end == 77.0
    assert window2.hvps_panel.get_config().n_steps == 9
    window2.close()


def test_apply_ignores_unknown_keys(window):
    state = settings_io.built_in_default_state()
    state["hvps"]["future_option"] = "whatever"
    warnings = settings_io.apply_state(window, state)
    assert warnings == []
    assert window.hvps_panel.get_config() == HVPSConfig()


def test_defaults_autoload_at_startup(app, tmp_path, monkeypatch):
    defaults_file = tmp_path / "default_settings.json"
    state = settings_io.built_in_default_state()
    state["hvps"]["v_end"] = 321.0
    state["mode"] = "cv"
    settings_io.save_settings_file(defaults_file, state)

    monkeypatch.setattr(settings_io, "DEFAULTS_PATH", defaults_file)
    window = MainWindow(sim=True)
    assert window.mode_combo.currentText() == "cv"
    assert window.hvps_panel.get_config().v_end == 321.0
    window.close()

    # no defaults file -> widgets keep their built-in values
    monkeypatch.setattr(settings_io, "DEFAULTS_PATH", tmp_path / "missing.json")
    window = MainWindow(sim=True)
    assert window.mode_combo.currentText() == "iv"
    assert window.hvps_panel.get_config() == HVPSConfig()
    window.close()


def test_connections_defaults_exposed():
    panel = ConnectionsPanel()
    assert panel.DEFAULTS["hvps"] == "/dev/ttyS0"
    panel.set_resource("lcr", "GPIB0::8::INSTR")
    assert panel.resources()["lcr"] == "GPIB0::8::INSTR"
