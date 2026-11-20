"""Keithley 2410 SourceMeter driver, used as HVPS.

Commands verified against the Series 2400 SourceMeter User's Manual
(2400S-900-01 Rev. K) available in Instruments/Ke2410/manuals/.
The unit is always operated on the 1000 V voltage range, sourcing DC voltage
and measuring the total sourced current.
"""

from drivers.base import InstrumentBase, InstrumentError, parse_scpi_float


class Keithley2410(InstrumentBase):
    RANGE = 1000.0  # V, fixed operating range

    @classmethod
    def connect(cls, resource: str, *, timeout: float = 5.0,
                session_factory=None):
        """Open a session (RS-232) and return a configured driver instance.

        The serial line settings (baud rate, parity) are auto-detected and the
        connected instrument is verified to be a Model 2410 via *IDN?.
        """
        if session_factory is None:
            from drivers.session import open_session as session_factory
        from drivers.detect import SERIAL_PROBES, identify

        last_error = None
        for baud, parity in SERIAL_PROBES:
            session = None
            try:
                session = session_factory(resource, baud=baud, timeout=timeout,
                                          parity=parity)
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
        self._send(":SOUR:FUNC VOLT")
        self._send(":SOUR:VOLT:MODE FIXED")
        self._send(f":SOUR:VOLT:RANG {self.RANGE:g}")
        self._send(':SENS:FUNC "CURR"')
        self._send(":FORM:ELEM READ")
        self._send(f":SENS:CURR:PROT:LEV {compliance:g}")
        if autorange:
            self._send(":SENS:CURR:RANG:AUTO ON")
            self._send(f":SENS:CURR:RANG:AUTO:LLIM {autorange_llimit:g}")
        else:
            self._send(":SENS:CURR:RANG:AUTO OFF")
            self._send(f":SENS:CURR:RANG {fixed_range:g}")
        self._send(":OUTP OFF")

    def output(self, on: bool):
        self._send(":OUTP {}".format("ON" if on else "OFF"))

    def set_voltage(self, voltage: float):
        """Set the bias voltage (signed, polarity applied by the caller)."""
        self._send(f":SOUR:VOLT:LEV {voltage:.8g}")
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
