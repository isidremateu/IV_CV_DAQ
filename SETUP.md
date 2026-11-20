# Setup and Usage

This document describes how to install and run the IV/CV DAQ application on
the measurement PC (AlmaLinux 9.8). For the measurement functionality, see the
main `README.md`.

## Installation

```bash
cd IV_CV_DAQ
python3 -m venv .venv          # if that fails: pip install virtualenv && python3 -m virtualenv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Serial port access (Keithley 2410 and 6487, RS-232)

Add your user to the `dialout` group so the RS-232 ports are accessible, then
log out and back in:

```bash
sudo usermod -aG dialout $USER
```

Identify the serial ports of the instruments (e.g. `/dev/ttyS0`, or
`/dev/ttyUSB0` for USB-serial adapters) and enter them in the *Connections*
panel of the application. The Keithleys use 9600 baud, 8N1, LF terminator
(instrument default).

### GPIB access (HP 4284A)

The LCR meter is connected through a GPIB-USB adapter. Depending on the
adapter:

- **NI GPIB-USB-HS**: install [NI-488.2](https://www.ni.com/en/support/downloads/drivers.html)
  for Linux, then use e.g. `GPIB0::17::INSTR` (the sample programs in
  `Instruments/HP4284A/sample programs/` use primary address 17).
- **Prologix USB-GPIB**: the adapter exposes itself as a serial port and is
  not auto-detected as a GPIB resource; configure its address mode manually
  (see the Prologix manual) and enter the resource string by hand.

If the default VISA backend is not found, the application automatically falls
back to `pyvisa-py`.

### Instrument detection

Instead of typing resource strings manually, press **Detect instruments** in
the *Connections* panel. The application enumerates all visible VISA
resources (GPIB addresses first, then serial ports) and briefly queries each
with `*IDN?` (1.5 s timeout, harmless for the instruments):

- `KEITHLEY ... MODEL 2410 ...` -> HVPS
- `KEITHLEY ... MODEL 6487 ...` -> picoammeter
- `HEWLETT-PACKARD ... 4284A ...` -> LCR meter

Detected resources are filled into the fields automatically; ports that are
busy or do not answer are skipped and reported. Notes:

- The Keithleys are probed at their default 9600 baud. If you changed the
  instrument's baud rate, enter the resource string manually.
- The scan runs in the background and can take tens of seconds when many
  serial ports are present.

### Settings files

The *Settings* menu manages the full configuration (mode, HVPS, picoammeter,
LCR, connections, data folder and identifier):

- **Load settings...** / **Save settings...** (Ctrl+O / Ctrl+S): read/write a
  JSON settings file of your choice.
- **Set current as defaults**: stores the current configuration in
  `~/.ivcv_daq/default_settings.json`; this file is applied automatically at
  every startup.
- **Restore built-in defaults**: resets all panels to the factory values
  (the data folder is kept).

Unknown keys in settings files are ignored, so files written by newer
versions still load.

## Running

```bash
source .venv/bin/activate
python main.py
```

A **simulation mode** with simulated instruments is available for testing
without hardware:

```bash
python main.py --sim
```

The window layout:

- **Measurement mode**: `iv` (pad + total current vs voltage) or `cv`
  (capacitance vs voltage).
- **HVPS panel**: polarity, ramp type (linear / logarithmic / from file),
  start/end voltage and number of steps (start and end included), ramping
  speed, wait time, current compliance, current autorange settings.
  The current ranges are dropdowns restricted to the discrete instrument
  levels (2410: 1 µA … 1 A, autorange low limit up to 100 µA; 6487:
  2 nA … 20 mA).
- **Picoammeter panel** (IV) or **LCR panel** (CV): instrument settings as
  described in the README. The LCR frequency accepts any value between
  20 Hz and 1 MHz (the 4284A limit); common values are offered as
  suggestions.
- **Data saving**: output folder and identifier.
- **Connections**: resource strings of the three instruments.
- **Start / Abort**: abort triggers a safe ramp-down to 0 V and output off.
- **Plot**: refreshed after every voltage step, with mean+-std error bars and
  independent log/linear X and Y axes plus absolute-value toggles for each
  axis. In CV mode the capacitance can be displayed as 1/C² (useful for
  junction/doping analysis). All axis and legend labels carry the physical
  units between brackets, e.g. `Current [A]`, `1/C² [1/F²]`.

The HP 4284A is always configured in parallel Cp-G mode with all corrections
disabled; its internal bias is off and DC isolation is on, since the sensor
bias is provided by the Keithley 2410.

## Data files

Files are written incrementally (every completed voltage step is flushed):

- `YYMMDD_HHMMSS_identifier_iv.txt` / `..._cv.txt`: CSV data, with mean and
  std columns (std is 0 when averaging is off):
  - IV: `voltage_V, pad_current_A, pad_current_std_A, total_current_A, total_current_std_A`
  - CV: `voltage_V, capacitance_F, capacitance_std_F, conductance_S, conductance_std_S, total_current_A, total_current_std_A`
- `YYMMDD_HHMMSS_identifier_iv.json` / `..._cv.json`: all instrument settings
  used for the measurement.

## Tests

Unit and GUI smoke tests (the GUI test runs headless against simulated
instruments):

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## Troubleshooting

**`xkbcommon: ERROR: failed to add default include path .../anaconda3/share/X11/xkb`**
followed by `qt.qpa.wayland: failed to create xkb context` — the GUI is
running with Anaconda's libraries, whose `libxkbcommon` looks for the X
keyboard data inside the Anaconda prefix (where it does not exist). Fixes:

1. Recommended: recreate the virtual environment with the system Python so
   no Anaconda libraries are used:
   ```bash
   conda deactivate
   rm -rf .venv
   /usr/bin/python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ldd .venv/bin/python | grep conda   # should print nothing
   ```
2. Or link the system keyboard data into the Anaconda prefix:
   ```bash
   mkdir -p ~/anaconda3/share/X11
   ln -s /usr/share/X11/xkb ~/anaconda3/share/X11/xkb
   ```
3. Or point libxkbcommon at the system data:
   `export XKB_CONFIG_ROOT=/usr/share/X11/xkb`

When launching from an X11-forwarded SSH session, try
`QT_QPA_PLATFORM=xcb python main.py`.

## Project structure

```
main.py               entry point (--sim for simulated instruments)
core/
  config.py           configuration dataclasses (GUI <-> engine <-> files)
  ramps.py            linear / logarithmic / from-file voltage arrays
  engine.py           measurement controller (ramping, sampling, safety)
  data_io.py          CSV writer, settings JSON, file naming
drivers/
  keithley2410.py     HVPS driver (commands from Instruments/Ke2410/manuals)
  keithley6487.py     picoammeter driver (Instruments/Ke6487/manuals)
  hp4284a.py          LCR driver (Instruments/HP4284A/manuals)
  session.py          PyVISA session handling (RS-232 + GPIB)
  sim.py              simulated instruments for --sim mode
gui/
  main_window.py      main window and background measurement thread
  panels.py           settings panels
  plot_widget.py      live error-bar plot with log/linear toggles
tests/                unit tests (no hardware required)
```
