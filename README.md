# Introduction
This Data Acquisition (DAQ) code enables the measurement of current versus voltage (IV) and capacitance versus voltage (CV) characteristics of silicon sensors in a probe station.

# Hardware
The DAQ controls 3 instruments:

- Keithley 2410 source-meter: Used as High-Voltage Power Supply (HVPS) to provide bias voltage to the sensor and measure total sourced current to the sensor. The same unit is used for CV and IV.
- Keithly 6487 picoammeter: Used to measure the sensor's pad current in IV mode.
- HP4284a LCR meter (old version): Used to measure capacitance in CV mode.

The DAQ runs on a Linux PC (AlmaLinux 9.8). The two Keithley devices are connected via RS-232, while the LCR meter is connected with a GPIB-USB adaptor. The GUI also runs on other platforms (e.g. Windows), where the simulation mode can be used without any hardware.

# Installation
The application is written in Python 3.9+ and uses PyVISA (instrument communication), PySide6 + pyqtgraph (GUI) and numpy.

```bash
git clone https://github.com/isidremateu/IV_CV_DAQ.git
cd IV_CV_DAQ
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Notes for the measurement PC:

- Serial port access (both Keithleys): add your user to the `dialout` group
  (`sudo usermod -aG dialout $USER`, then log in again).
- GPIB: for an NI GPIB-USB adapter install the NI-488.2 driver; a Prologix
  adapter works with the pure-python backend (`pyvisa-py`, included in
  `requirements.txt`).
- If no VISA backend is configured, the application automatically falls back
  to `pyvisa-py`.

See `SETUP.md` for detailed instructions (GPIB adapter options, instrument
auto-detection, settings files).

# Functionality
The DAQ allows the user to:

- Select between IV and CV measurements.
- Configure HVPS voltage ramping profile.
- Configure measurement parameters.
- Automatically detect the connected instruments (queries every GPIB address
  and serial port with `*IDN?` and fills in the resource strings).
- Visualise the IV or CV curve during acquisition.
- Save the measurement data.
- Save, load and store as defaults the full set of GUI settings.

## HVPS settings

The HVPS is configured to use always the 1000 V voltage range.

The user is able to configure the following settings regarding the bias voltage ramping and the measurement of the sourced current:

- Voltage polarity.
- Ramp type:
    - Linear: equi-spaced voltage points.
    - Logarithmic: base-10 logarithms of the voltage values are equi-spaced.
    - From file: the list of voltages is taken from a .txt file (single column). The absolute value of the file content is taken. The polarity is decided by the voltage polarity setting.
- Voltage start [V], Voltage end [V], number of steps: applicable only for the linear and logarithmic modes. Both the start and end values are included in the resulting voltage array.
- Ramping speed [V/s]: rate of voltage change between steps.
- Wait time [s]: time to wait after a new voltage value is set, before taking the first measurement.
- Current compliance [A]: maximum current allowed to be sourced by the HVPS.
- Current measurement autorange on/off.
- autorange low limit: when in autorange, sets the lowest range the HVPS is allowed to use. The list of range levels is specified in the HVPS manual. The GUI offers only the values accepted by the instrument (1 µA, 10 µA, 100 µA).
- range: when not in autorange, sets the range to be used for the current measurement. The GUI offers the discrete range levels of the instrument (1 µA, 10 µA, 100 µA, 1 mA, 20 mA, 100 mA, 1 A).

## Picoammeter settings

The picoammeter is used in IV mode to obtain a measurement of the sensor pad current.

The following settings can be configured:

- Current measurement autorange on/off.
- autorange low limit: when in autorange, sets the lowest range the picoammeter is allowed to use. The list of range levels is specified in the picoammeter manual. The GUI offers the discrete range levels of the instrument (2 nA to 20 mA).
- range: when not in autorange, sets the range to be used for the current measurement (2 nA to 20 mA).
- Integration time: from 0.01 power line cycles (PLC) to 50 PLC.
- Damping on/off.
- Median filter on/off and rank.
- Digital filter: moving/repeating/off and number of samples.
- Averaging: number of acquired samples to average in software for each voltage step.

## LCR meter settings

The LCR meter is used in CV mode to obtain a measurement of the sensor capacitance. It operates in parallel capacitance - conductance mode, and with all corrections disabled. The following parameters are configurable:

- Frequency: any value between 20 Hz and 1 MHz (common values offered as suggestions).
- Integration time [SHORT, MEDIUM, LONG].
- Voltage level [0 to 2 V].
- Averaging: number of acquired samples to average in software for each voltage step.

The internal bias of the LCR meter is switched off and its DC isolation is switched on, since the sensor bias is provided by the HVPS.

## Display.

When an IV or CV measurement starts, the measurement data is visualised in a current versus voltage or capacitance versus voltage graph. Mean and std are used to show an error bar plot, and the plot refreshes as soon as a new voltage step is completed. The user can switch between linear and log axis independently for the x and y axis, and can additionally plot the absolute value of each axis. In CV mode, the capacitance can be displayed as 1/C² (e.g. for junction/doping analysis). All axis and legend labels carry the physical units between brackets (e.g. `Current [A]`). On a log scale, ticks are placed at the decades and labeled with the original values, and zero/negative values are not visible. The values shown are always the measured quantities (a 10 pF reading is displayed as 10 pF, or 10⁻¹¹ F); the data files always store the raw values.

## Data saving

The user selects a folder where to store the data files as well as an identifier. All saved files are of the form YYMMDD_HHMMSS_identifier_[iv/cv].txt, using the timestamp at the start of the acquisition to construct the file name.

The files are saved as CSV files, with mean and std values for wherever quantities averaging is possible (even in the case no averaging is selected, to keep the same file structure). The data is written to disk after every voltage step, so a partially completed measurement is still usable.

For IV files, the bias voltage, the pad current and the total current (from the HVPS) are saved:

```
voltage_V,pad_current_A,pad_current_std_A,total_current_A,total_current_std_A
```

For CV, the bias voltage, the capacitance, the conductance and the total current (from the HVPS) are saved:

```
voltage_V,capacitance_F,capacitance_std_F,conductance_S,conductance_std_S,total_current_A,total_current_std_A
```

A separate json file is saved for each measurement with the instruments settings.

# Usage

```bash
source .venv/bin/activate
python main.py            # real instruments
python main.py --sim      # simulated instruments (no hardware needed)
```

- **Connections panel**: enter the resource strings manually or press
  *Detect instruments* to scan the buses automatically.
- **Start / Abort**: aborting triggers a safe ramp-down of the bias voltage
  to 0 V and switches the HV output off.
- **Settings menu**: load/save the configuration as JSON and store the
  current settings as automatic defaults (`~/.ivcv_daq/default_settings.json`).

# Testing

Unit tests (instrument drivers, ramps, data files, GUI) run without any hardware:

```bash
python -m pytest tests/ -v
```

# Project structure

```
main.py               entry point (--sim for simulated instruments)
core/                 configuration, ramps, measurement engine, data files
drivers/              instrument drivers (2410, 6487, 4284A), VISA session,
                      auto-detection, simulator
gui/                  main window, settings panels, plot widget, settings files
tests/                unit and GUI smoke tests (no hardware required)
Instruments/          instrument manuals and vendor sample programs
```
