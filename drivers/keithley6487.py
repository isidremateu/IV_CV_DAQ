"""Keithley 6487 Picoammeter driver (sensor pad current, IV mode).

Commands verified against the Model 6487 Picoammeter/Voltage Source Reference
Manual (6487-901-01 Rev. B) available in Instruments/Ke6487/manuals/.
The voltage source of the 6487 is NOT used; bias is provided by the 2410.
"""

from drivers.base import InstrumentBase, parse_scpi_float


class Keithley6487(InstrumentBase):

    @classmethod
    def connect(cls, resource: str, *, timeout: float = 5.0,
                session_factory=None):
        """Open a session (RS-232) and return a configured driver instance.

        The serial line settings (baud rate, parity) are auto-detected and the
        connected instrument is verified to be a Model 6487 via *IDN?.
        """
        if session_factory is None:
            from drivers.session import open_session as session_factory
        from drivers.detect import SERIAL_PROBES, identify
        from drivers.base import InstrumentError

        last_error = None
        for baud, parity, data_bits in SERIAL_PROBES:
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
            if identify(idn) != "pico":
                last_error = (f"expected a Model 6487 on '{resource}' at "
                              f"{baud} baud/{parity} parity, got '{idn}'")
                session.close()
                continue
            driver = cls(session)
            driver._send("*RST")
            driver._send("*CLS")
            return driver
        raise InstrumentError(
            f"Could not connect to a Keithley 6487 on '{resource}': {last_error}")

    def setup(self, autorange: bool, autorange_llimit: float, fixed_range: float,
              nplc: float, damping: bool, median_on: bool, median_rank: int,
              filter_on: bool, filter_type: str, filter_count: int):
        """Apply all picoammeter settings from the GUI panel."""
        self._send(":FORM:ELEM READ")
        self._send(':SENS:FUNC "CURR"')
        self._send(f":SENS:CURR:NPLC {nplc:g}")

        self._send(":SENS:CURR:DAMP {}".format("ON" if damping else "OFF"))

        self._send(":SENS:CURR:MED:STAT {}".format("ON" if median_on else "OFF"))
        if median_on:
            self._send(f":SENS:CURR:MED:RANK {int(median_rank)}")

        self._send(":SENS:CURR:AVER:STAT {}".format("ON" if filter_on else "OFF"))
        if filter_on:
            tcon = "MOV" if filter_type == "moving" else "REP"
            self._send(f":SENS:CURR:AVER:TCON {tcon}")
            self._send(f":SENS:CURR:AVER:COUN {int(filter_count)}")

        if autorange:
            self._send(":SENS:CURR:RANG:AUTO ON")
            self._send(f":SENS:CURR:RANG:AUTO:LLIM {autorange_llimit:g}")
        else:
            self._send(":SENS:CURR:RANG:AUTO OFF")
            self._send(f":SENS:CURR:RANG {fixed_range:g}")

        # Zero check must be off while measuring (readings are suppressed otherwise)
        self._send(":SYST:ZCH OFF")

    def read_current(self) -> float:
        """Read the sensor pad current."""
        return parse_scpi_float(self._ask(":READ?"))

    def close(self):
        try:
            self._send(":SYST:ZCH ON")
        except Exception:
            pass
        super().close()
