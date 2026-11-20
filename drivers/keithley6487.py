"""Keithley 6487 Picoammeter driver (sensor pad current, IV mode).

Commands verified against the Model 6487 Picoammeter/Voltage Source Reference
Manual (6487-901-01 Rev. B) available in Instruments/Ke6487/manuals/.
The voltage source of the 6487 is NOT used; bias is provided by the 2410.
"""

from drivers.base import InstrumentBase, parse_scpi_float, scpi_number


class Keithley6487(InstrumentBase):

    @classmethod
    def connect(cls, resource: str, *, timeout: float = 5.0,
                session_factory=None, serial_probes=None):
        """Open a session (RS-232) and return a configured driver instance.

        The serial line settings (baud rate, parity, data bits) are
        auto-detected and the connected instrument is verified to be a Model
        6487 via *IDN?. `serial_probes` restricts the tried combinations
        (defaults to all supported ones).
        """
        if session_factory is None:
            from drivers.session import open_session as session_factory
        from drivers.detect import SERIAL_PROBES, identify
        from drivers.base import InstrumentError

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
        self._send_checked(":FORM:ELEM READ")
        self._send_checked(':SENS:FUNC "CURR"')
        self._send_checked(f":SENS:CURR:NPLC {scpi_number(nplc)}")

        self._send_checked(":SENS:CURR:DAMP {}".format("ON" if damping else "OFF"))

        self._send_checked(
            ":SENS:CURR:MED:STAT {}".format("ON" if median_on else "OFF"))
        if median_on:
            self._send_checked(f":SENS:CURR:MED:RANK {int(median_rank)}")

        self._send_checked(
            ":SENS:CURR:AVER:STAT {}".format("ON" if filter_on else "OFF"))
        if filter_on:
            tcon = "MOV" if filter_type == "moving" else "REP"
            self._send_checked(f":SENS:CURR:AVER:TCON {tcon}")
            self._send_checked(f":SENS:CURR:AVER:COUN {int(filter_count)}")

        if autorange:
            self._send_checked(":SENS:CURR:RANG:AUTO ON")
            self._send_checked(
                f":SENS:CURR:RANG:AUTO:LLIM {scpi_number(autorange_llimit)}")
        else:
            self._send_checked(":SENS:CURR:RANG:AUTO OFF")
            self._send_checked(f":SENS:CURR:RANG {scpi_number(fixed_range)}")

        # Zero check must be off while measuring (readings are suppressed otherwise)
        self._send_checked(":SYST:ZCH OFF")

    def read_current(self) -> float:
        """Read the sensor pad current."""
        return parse_scpi_float(self._ask(":READ?"))

    def close(self):
        try:
            self._send(":SYST:ZCH ON")
        except Exception:
            pass
        super().close()
