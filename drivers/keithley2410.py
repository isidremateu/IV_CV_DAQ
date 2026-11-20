"""Keithley 2410 SourceMeter driver, used as HVPS.

Commands verified against the Series 2400 SourceMeter User's Manual
(2400S-900-01 Rev. K) available in Instruments/Ke2410/manuals/.
The unit is always operated on the 1000 V voltage range, sourcing DC voltage
and measuring the total sourced current.
"""

from drivers.base import InstrumentBase, InstrumentError, parse_scpi_float, scpi_number


class Keithley2410(InstrumentBase):
    RANGE = 1000.0  # V, fixed operating range

    @classmethod
    def connect(cls, resource: str, *, timeout: float = 5.0,
                session_factory=None, serial_probes=None):
        """Open a session (RS-232) and return a configured driver instance.

        The serial line settings (baud rate, parity, data bits) are
        auto-detected and the connected instrument is verified to be a Model
        2410 via *IDN?. `serial_probes` restricts the tried combinations
        (defaults to all supported ones).
        """
        if session_factory is None:
            from drivers.session import open_session as session_factory
        from drivers.detect import SERIAL_PROBES, identify

        probes = list(serial_probes) if serial_probes else SERIAL_PROBES
        last_error = None
        for baud, parity, data_bits in probes:
            session = None
            try:
                session = session_factory(resource, baud=baud, timeout=timeout,
                                          parity=parity, data_bits=data_bits)
                idn = str(session.query("*IDN?")).strip()
            except Exception as error:
                last_error = error
                if session is not None:
                    session.close()
                continue
            if identify(idn) != "hvps":
                last_error = (f"expected a Model 2410 on '{resource}' at "
                              f"{baud} baud/{parity} parity, got '{idn}'")
                session.close()
                continue
            driver = cls(session)
            driver._send("*RST")
            driver._send("*CLS")
            driver.output(False)
            return driver
        raise InstrumentError(
            f"Could not connect to a Keithley 2410 on '{resource}': {last_error}")

    def setup(self, compliance: float, autorange: bool, autorange_llimit: float,
              fixed_range: float):
        """Apply the HVPS configuration shared by IV and CV modes."""
        self._send_checked(":SOUR:FUNC VOLT")
        self._send_checked(":SOUR:VOLT:MODE FIXED")
        self._send_checked(f":SOUR:VOLT:RANG {self.RANGE:g}")
        # NOTE: the 2400's response elements are CURR/VOLT/RES/TIME/STAT -
        # 'READ' is the 6487's nomenclature and is rejected with error -102
        self._send_checked(':SENS:FUNC "CURR"')
        self._send_checked(":FORM:ELEM CURR")
        self._send_checked(f":SENS:CURR:PROT:LEV {scpi_number(compliance)}")
        if autorange:
            self._send_checked(":SENS:CURR:RANG:AUTO ON")
            self._send_checked(
                f":SENS:CURR:RANG:AUTO:LLIM {scpi_number(autorange_llimit)}")
        else:
            self._send_checked(":SENS:CURR:RANG:AUTO OFF")
            self._send_checked(f":SENS:CURR:RANG {scpi_number(fixed_range)}")
        self._send_checked(":OUTP OFF")

    def output(self, on: bool):
        self._send(":OUTP {}".format("ON" if on else "OFF"))

    def set_voltage(self, voltage: float):
        """Set the bias voltage (signed, polarity applied by the caller)."""
        self._send(f":SOUR:VOLT:LEV {scpi_number(voltage)}")
        # *OPC? synchronizes: returns only after the command has completed
        self._ask("*OPC?")

    def get_voltage(self) -> float:
        return parse_scpi_float(self._ask(":SOUR:VOLT:LEV?"))

    def read_current(self) -> float:
        """Read the total current sourced to the sensor."""
        return parse_scpi_float(self._ask(":READ?"))

    def close(self):
        try:
            self.output(False)
        except Exception:
            pass
        super().close()
