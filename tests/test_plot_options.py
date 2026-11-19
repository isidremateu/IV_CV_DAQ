"""Headless tests for the plot display options (abs, log, 1/C^2)."""

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gui.plot_widget import LivePlot  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_iv_point(v, pad, tot):
    return {"voltage": v, "pad_current": pad, "pad_current_std": 1e-12,
            "total_current": tot, "total_current_std": 1e-12}


def make_cv_point(v, c):
    return {"voltage": v, "capacitance": c, "capacitance_std": c * 0.01,
            "conductance": 1e-12, "conductance_std": 0.0,
            "total_current": 1e-9, "total_current_std": 0.0}


def test_abs_x_and_log_x(app):
    p = LivePlot()
    p.set_mode("iv")
    for v in (-100, -50, -10):
        p.add_point(make_iv_point(v, 1e-9, 2e-9))

    p.x_abs.setChecked(True)
    xd, yd = p._curves["pad"].getData()
    assert np.allclose(xd, [100.0, 50.0, 10.0])       # |V| displayed
    assert np.allclose(yd, [1e-9, 1e-9, 1e-9])        # y untouched

    p.x_log.setChecked(True)
    xd, _ = p._curves["pad"].getData()
    assert np.allclose(xd, [math.log10(100), math.log10(50), math.log10(10)])
    assert not np.any(np.isnan(xd))                   # negatives now visible


def test_abs_y_with_negative_currents(app):
    p = LivePlot()
    p.set_mode("iv")
    p.add_point(make_iv_point(-10.0, -5e-9, -6e-9))
    p.add_point(make_iv_point(-20.0, -7e-9, -8e-9))

    xd, yd = p._curves["pad"].getData()
    assert np.allclose(yd, [-5e-9, -7e-9])            # raw by default

    p.y_abs.setChecked(True)
    _, yd = p._curves["pad"].getData()
    assert np.allclose(yd, [5e-9, 7e-9])              # magnitude displayed

    p.y_log.setChecked(True)
    _, yd = p._curves["pad"].getData()
    assert np.allclose(yd, [math.log10(5e-9), math.log10(7e-9)])
    err = p._curves["pad_err"]
    expected = 1e-12 / (5e-9 * math.log(10))          # sigma_log propagation
    assert np.isclose(err.opts["top"][0], expected)


def test_inv_c2_option(app):
    p = LivePlot()
    p.set_mode("cv")
    assert not p.inv_c2.isVisible()
    p.inv_c2.setVisible(True)
    p.inv_c2.setChecked(True)

    c1, c2 = 1e-9, 2e-10
    p.add_point(make_cv_point(0.0, c1))
    p.add_point(make_cv_point(10.0, c2))

    xd, yd = p._curves["cap"].getData()
    assert np.allclose(yd, [1.0 / c1 ** 2, 1.0 / c2 ** 2])
    err = p._curves["cap_err"]
    expected = 2.0 * (c1 * 0.01) / c1 ** 3            # sigma = 2 sigma_C / C^3
    assert np.isclose(err.opts["top"][0], expected)
    assert p.plot.getAxis("left").label.toPlainText().strip() == "1/C² [1/F²]"

    p.inv_c2.setChecked(False)
    _, yd = p._curves["cap"].getData()
    assert np.allclose(yd, [c1, c2])
    assert p.plot.getAxis("left").label.toPlainText().strip() == "Capacitance [F]"


def legend_text(label_item):
    """Plain text of a pyqtgraph LegendItem entry (LabelItem wrapper)."""
    return label_item.item.toPlainText().strip()


def test_axis_and_legend_labels_have_units(app):
    p = LivePlot()
    p.set_mode("iv")
    assert p.plot.getAxis("bottom").label.toPlainText().strip() == "Bias voltage [V]"
    assert p.plot.getAxis("left").label.toPlainText().strip() == "Current [A]"
    assert legend_text(p.legend.items[0][1]) == "pad current [A]"
    assert legend_text(p.legend.items[1][1]) == "total current [A]"

    p.set_mode("cv")
    assert p.plot.getAxis("left").label.toPlainText().strip() == "Capacitance [F]"
    assert legend_text(p.legend.items[0][1]) == "capacitance [F]"


def test_inv_c2_with_log_y(app):
    p = LivePlot()
    p.set_mode("cv")
    p.inv_c2.setChecked(True)
    p.y_log.setChecked(True)
    c = 1e-10
    p.add_point(make_cv_point(50.0, c))
    _, yd = p._curves["cap"].getData()
    assert np.isclose(yd[0], math.log10(1.0 / c ** 2))
    # ticks show the displayed quantity (1/C^2 values), not log exponents
    levels = p.plot.getAxis("left")._tickLevels
    assert levels and all(lbl for _, lbl in levels[0])
