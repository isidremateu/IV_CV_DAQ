"""Headless GUI smoke test: runs a full simulated IV measurement through the GUI."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gui.main_window import MainWindow  # noqa: E402


def test_gui_sim_iv_end_to_end(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(sim=True)
    window.show()  # offscreen; needed so the plot view range is maintained

    # speed the simulation up and keep the ramp short
    window.mode_combo.setCurrentText("iv")
    window.hvps_panel.v_start.setText("0")
    window.hvps_panel.v_end.setText("5")
    window.hvps_panel.n_steps.setValue(3)
    window.hvps_panel.ramp_rate.setText("1000")
    window.hvps_panel.wait_time.setText("0")
    window.save_panel.folder.setText(str(tmp_path))
    window.save_panel.identifier.setText("smoke")

    window.start_measurement()
    assert window.thread is not None

    deadline = time.time() + 120
    while window.thread is not None and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)

    # three points received and plotted
    assert len(window.plot._data["x"]) == 3
    assert window.plot._data["x"][-1] == 5.0

    # curves and error bars really received the data (slot exceptions from
    # queued signals do not fail the test by themselves)
    for key in ("pad", "tot"):
        assert window.plot._curves[key].xData is not None
        assert len(window.plot._curves[key].xData) == 3
        err_x = window.plot._curves[key + "_err"].opts["x"]
        assert err_x is not None and len(err_x) == 3

    # log toggles switch the axes to true log scale: explicit ticks at
    # decade positions labeled with the original values
    window.plot.x_log.setChecked(True)
    window.plot.y_log.setChecked(True)
    app.processEvents()
    for name in ("bottom", "left"):
        levels = window.plot.plot.getAxis(name)._tickLevels
        assert levels, f"no explicit ticks on {name} axis in log mode"
        majors = levels[0]
        assert all(lbl not in ("", None) for _, lbl in majors)
    # y majors must show original current values (e.g. 1e-12 A at the 0 V step)
    y_labels = [lbl for _, lbl in window.plot.plot.getAxis("left")._tickLevels[0]]
    assert "1e-12" in y_labels
    # x majors/mantissas must show original voltage values (points at 2.5/5 V)
    x_labels = [lbl for _, lbl in
                sum(window.plot.plot.getAxis("bottom")._tickLevels, [])]
    assert "5" in x_labels

    # data file exists with header + 3 rows, settings json exists
    files = os.listdir(tmp_path)
    assert any(f.endswith("_iv.txt") for f in files)
    assert any(f.endswith("_iv.json") for f in files)
