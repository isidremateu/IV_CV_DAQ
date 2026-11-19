"""Tests for the discrete range dropdowns and the LCR frequency validation."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.config import HVPSConfig, LCRConfig, PicoConfig  # noqa: E402
from gui.panels import (  # noqa: E402
    HVPS_AUTORANGE_LLIMITS, HVPS_MEASURE_RANGES, HVPSPanel, LCRPanel,
    PICO_RANGES, PicoPanel,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_hvps_range_dropdowns():
    panel = HVPSPanel()
    # only the manual's discrete levels are offered
    assert [panel.fixed_range.itemData(i) for i in range(panel.fixed_range.count())] \
        == [v for _, v in HVPS_MEASURE_RANGES]
    assert [panel.autorange_llimit.itemData(i) for i in range(panel.autorange_llimit.count())] \
        == [v for _, v in HVPS_AUTORANGE_LLIMITS]

    # labels of the autorange low limit stay within the ±105 µA command limit
    assert panel.autorange_llimit.itemText(0) == "1 µA"
    assert panel.autorange_llimit.itemText(2) == "100 µA"

    cfg = HVPSConfig(autorange=False, range=2e-2, autorange_llimit=1e-4)
    panel.set_config(cfg)
    assert panel.fixed_range.currentText() == "20 mA"
    assert panel.autorange_llimit.currentText() == "100 µA"
    read_back = panel.get_config()
    assert read_back.range == 2e-2
    assert read_back.autorange_llimit == 1e-4


def test_pico_range_dropdowns():
    panel = PicoPanel()
    assert [panel.fixed_range.itemData(i) for i in range(panel.fixed_range.count())] \
        == [v for _, v in PICO_RANGES]

    cfg = PicoConfig(autorange=False, range=2e-8, autorange_llimit=2e-7)
    panel.set_config(cfg)
    assert panel.fixed_range.currentText() == "20 nA"
    assert panel.autorange_llimit.currentText() == "200 nA"
    read_back = panel.get_config()
    assert read_back.range == 2e-8
    assert read_back.autorange_llimit == 2e-7


def test_range_snap_to_nearest_for_old_settings_files():
    """Values from older settings files select the nearest discrete range."""
    panel = PicoPanel()
    panel.set_config(PicoConfig(autorange=False, range=3.7e-8,
                                autorange_llimit=1e-11))
    # 3.7e-8 -> 20 nA (2e-8); 1e-11 -> 2 nA (2e-9)
    assert panel.fixed_range.currentText() == "20 nA"
    assert panel.autorange_llimit.currentText() == "2 nA"


def test_lcr_frequency_validation():
    panel = LCRPanel()
    panel.frequency.setCurrentText("123456")
    assert panel.get_config().frequency == 123456.0

    for bad in ("5", "2000000", "abc"):
        panel.frequency.setCurrentText(bad)
        with pytest.raises(ValueError):
            panel.get_config()

    # limits themselves are accepted
    panel.frequency.setCurrentText("20")
    assert panel.get_config().frequency == 20.0
    panel.frequency.setCurrentText("1e6")
    assert panel.get_config().frequency == 1e6
