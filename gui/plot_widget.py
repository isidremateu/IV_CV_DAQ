"""Live plot widget (pyqtgraph) with per-axis linear/log/abs options.

IV mode shows the pad current and the total (HVPS) current; CV mode shows the
capacitance (optionally as 1/C^2). All axis and legend labels carry the
physical units between brackets.

Display pipeline per axis: raw measured value -> absolute value (optional)
-> log10 (optional, only for the display; zero/negative values become NaN and
are hidden). Error bars are propagated through every step:
- absolute value: sigma unchanged
- 1/C^2:          sigma = 2 * sigma_C / |C|^3
- log10:          sigma_log = sigma / (|y| * ln10)

In log mode the axes receive explicit ticks: majors at the decades labeled
with the original values of the displayed quantity (10, 100, 1e-10, ...),
minors at the 2..9 mantissa positions, so equal distances correspond to equal
multiplication factors.
"""

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QVBoxLayout, QWidget

pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")

PAD_COLOR = (31, 119, 180)     # blue
TOT_COLOR = (255, 127, 14)     # orange
CAP_COLOR = (44, 160, 44)      # green


def _fmt_value(value: float) -> str:
    """Format an axis tick label showing the original (untransformed) value."""
    if 1e-3 <= value < 1e4:
        return f"{value:g}"
    return f"{value:.0e}"


def _log_tick_levels(lo: float, hi: float):
    """Explicit tick levels for a log-scale axis over the view range [lo, hi]
    (both in log10 space).

    Returns [[(pos, label), ...] majors, [(pos, label), ...] minors] where
    positions are log10 values and labels are the original values. Majors sit
    at the integer exponents; minors at the 2..9 mantissas. When the view is
    zoomed inside a single decade (no major tick visible), the mantissa ticks
    are labeled instead.
    """
    if not np.isfinite(lo) or not np.isfinite(hi) or lo >= hi:
        return []
    major, minor = [], []
    for e in range(int(np.floor(lo)) - 1, int(np.ceil(hi)) + 1):
        if lo <= e <= hi:
            major.append((float(e), _fmt_value(10.0 ** e)))
        for m in range(2, 10):
            pos = e + math.log10(m)
            if lo <= pos <= hi:
                minor.append((pos, ""))
    if major:
        levels = [major]
        if minor:
            levels.append(minor)
        return levels
    # zoomed inside one decade: label the mantissa ticks with their values
    labeled = [(pos, _fmt_value(10.0 ** pos)) for pos, _ in minor]
    return [labeled] if labeled else []


class LivePlot(QWidget):
    """Error-bar plot refreshed after every completed voltage step."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.plot = pg.PlotWidget()
        self.legend = self.plot.addLegend(offset=(10, 10))
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        # keep the axis labels exactly as defined (no automatic "(x1e+18)"
        # SI-prefix suffixes appended by pyqtgraph)
        for name in ("bottom", "left"):
            self.plot.getAxis(name).enableAutoSIPrefix(False)
        layout.addWidget(self.plot)

        toggles = QHBoxLayout()
        self.x_log = QCheckBox("Log X")
        self.y_log = QCheckBox("Log Y")
        self.x_abs = QCheckBox("Abs X")
        self.y_abs = QCheckBox("Abs Y")
        self.inv_c2 = QCheckBox("1/C²")   # CV mode only
        for box in (self.x_log, self.y_log, self.x_abs, self.y_abs):
            box.toggled.connect(self._redraw)
            toggles.addWidget(box)
        self.inv_c2.toggled.connect(self._on_inv_c2_changed)
        self.inv_c2.setVisible(False)
        toggles.addWidget(self.inv_c2)
        toggles.addStretch(1)
        layout.addLayout(toggles)

        # regenerate explicit log ticks whenever the view range changes (zoom)
        self.plot.plotItem.vb.sigRangeChanged.connect(self._update_ticks)

        self.mode = "iv"
        self._reset_data()
        self._curves = {}
        self.set_mode("iv")

    # ------------------------------------------------------------------ API
    def set_mode(self, mode: str):
        self.mode = mode
        self.plot.setLabel("bottom", "Bias voltage [V]")
        self._update_y_label()
        self.inv_c2.setVisible(mode == "cv")
        self.clear()

    def clear(self):
        self._curves = {}
        self.plot.clear()
        self._reset_data()
        self._build_curves()
        self._redraw()

    def add_point(self, point: dict):
        d = self._data
        d["x"].append(point["voltage"])
        d["tot"].append(point["total_current"])
        d["tot_std"].append(point["total_current_std"])
        if self.mode == "iv":
            d["pad"].append(point["pad_current"])
            d["pad_std"].append(point["pad_current_std"])
        else:
            d["cap"].append(point["capacitance"])
            d["cap_std"].append(point["capacitance_std"])
        self._redraw()

    # -------------------------------------------------------------- internals
    def _reset_data(self):
        self._data = {"x": [], "pad": [], "pad_std": [],
                      "tot": [], "tot_std": [], "cap": [], "cap_std": []}

    def _update_y_label(self):
        if self.mode == "iv":
            self.plot.setLabel("left", "Current [A]")
        elif self.inv_c2.isChecked():
            self.plot.setLabel("left", "1/C² [1/F²]")
        else:
            self.plot.setLabel("left", "Capacitance [F]")

    def _build_curves(self):
        # remove any previous curve/error-bar items (e.g. when toggling 1/C²
        # during a measurement, only one set of curves must stay visible)
        for item in self._curves.values():
            try:
                self.plot.removeItem(item)
            except Exception:
                pass
        self._curves = {}
        self.legend.clear()
        if self.mode == "iv":
            self._curves = {
                "pad": self.plot.plot(pen=pg.mkPen(PAD_COLOR, width=2),
                                      symbol="o", symbolSize=6,
                                      symbolBrush=PAD_COLOR),
                "tot": self.plot.plot(pen=pg.mkPen(TOT_COLOR, width=2,
                                                   style=Qt.PenStyle.DashLine),
                                      symbol="s", symbolSize=6,
                                      symbolBrush=TOT_COLOR),
                "pad_err": pg.ErrorBarItem(pen=pg.mkPen(PAD_COLOR), beam=0.02),
                "tot_err": pg.ErrorBarItem(pen=pg.mkPen(TOT_COLOR), beam=0.02),
            }
            self.plot.addItem(self._curves["pad_err"])
            self.plot.addItem(self._curves["tot_err"])
            self.legend.addItem(self._curves["pad"], "pad current [A]")
            self.legend.addItem(self._curves["tot"], "total current [A]")
        else:
            name = "1/C² [1/F²]" if self.inv_c2.isChecked() \
                else "capacitance [F]"
            self._curves = {
                "cap": self.plot.plot(pen=pg.mkPen(CAP_COLOR, width=2),
                                      symbol="o", symbolSize=6,
                                      symbolBrush=CAP_COLOR),
                "cap_err": pg.ErrorBarItem(pen=pg.mkPen(CAP_COLOR), beam=0.02),
            }
            self.plot.addItem(self._curves["cap_err"])
            self.legend.addItem(self._curves["cap"], name)

    def _on_inv_c2_changed(self):
        self._update_y_label()
        self._build_curves()  # legend label depends on the option
        self._redraw()

    def _map_axis(self, values, log_on: bool, abs_on: bool):
        """Display transform for one axis: abs (optional) then log10."""
        out = np.asarray(values, dtype=float)
        if abs_on:
            out = np.abs(out)
        if log_on:
            logged = np.full(out.shape, np.nan)
            positive = out > 0
            logged[positive] = np.log10(out[positive])
            out = logged
        return out

    def _y_display(self, y, e):
        """Display transform for the y axis, propagating the errors.

        Returns (y_display, e_display).
        """
        y = np.asarray(y, dtype=float)
        e = np.asarray(e, dtype=float)

        if self.mode == "cv" and self.inv_c2.isChecked():
            good = np.abs(y) > 0
            new_y = np.full(y.shape, np.nan)
            new_e = np.full(y.shape, np.nan)
            new_y[good] = 1.0 / (y[good] ** 2)
            new_e[good] = 2.0 * e[good] / (np.abs(y[good]) ** 3)
            y, e = new_y, new_e

        if self.y_abs.isChecked():
            y = np.abs(y)

        if self.y_log.isChecked():
            good = np.isfinite(y) & (y != 0)
            new_y = np.full(y.shape, np.nan)
            new_e = np.full(y.shape, np.nan)
            new_y[good] = np.log10(y[good])
            new_e[good] = e[good] / (y[good] * math.log(10.0))
            y, e = new_y, new_e

        return y, e

    def _update_ticks(self, *args):
        """(Re)build the explicit axis ticks for the current view range.

        Accepts (and ignores) the (viewbox, range) arguments emitted by
        sigRangeChanged, to which this method is connected.
        """
        for name, log_on in (("bottom", self.x_log.isChecked()),
                             ("left", self.y_log.isChecked())):
            axis = self.plot.getAxis(name)
            if not log_on:
                axis.setTicks(None)
                continue
            lo, hi = self.plot.plotItem.vb.viewRange()[
                0 if name == "bottom" else 1]
            axis.setTicks(_log_tick_levels(lo, hi))

    def _redraw(self):
        self._update_ticks()

        d = self._data
        x = np.asarray(d["x"], dtype=float)
        if x.size == 0:
            return

        xd = self._map_axis(x, self.x_log.isChecked(), self.x_abs.isChecked())

        if self.mode == "iv":
            series = (("pad", "pad", "pad_std"), ("tot", "tot", "tot_std"))
        else:
            series = (("cap", "cap", "cap_std"),)

        for key, yname, ename in series:
            yd, ed = self._y_display(d[yname], d[ename])
            self._curves[key].setData(xd, yd)
            err = self._curves.get(key + "_err")
            if err is not None:
                finite = np.isfinite(xd) & np.isfinite(yd)
                err.setData(x=xd[finite], y=yd[finite],
                            top=ed[finite], bottom=ed[finite])

        # recompute the view range immediately (pyqtgraph otherwise defers
        # autorange to the next paint, which stalls the tick regeneration)
        vb = self.plot.plotItem.vb
        if any(vb.autoRangeEnabled()):
            vb.updateAutoRange()
