"""HP 4284A Precision LCR meter driver (capacitance, CV mode).

Commands verified against the 4284A Operation Manual (04284-90040, included in
Instruments/HP4284A/manuals/9018-01389.pdf) and the sample BASIC programs in
Instruments/HP4284A/sample programs/.

Fixed configuration (README):
- parallel capacitance - conductance function (Cp-G, FUNC:IMP CPG)
- all corrections disabled (open / short / load)
- internal bias off; DC isolation on (the 2410 provides the sensor bias)
"""

from drivers.base import InstrumentBase, InstrumentError, scpi_number

APER_MAP = {"short": "SHOR", "medium": "MED", "long": "LONG"}


class HP4284A(InstrumentBase):

    @classmethod
    def connect(cls, resource: str, *, timeout: float = 10.0,
                session_factory=None):
        """Open a session (GPIB) and return a configured driver instance.

        The connected instrument is verified to be an HP 4284A via *IDN?.
        """
        if session_factory is None:
            from drivers.session import open_session as session_factory
        from drivers.base import InstrumentError
        from drivers.detect import identify

        session = session_factory(resource, timeout=timeout)
        idn = str(session.query("*IDN?")).strip()
        if identify(idn) != "lcr":
            session.close()
            raise InstrumentError(
                f"Expected an HP 4284A on '{resource}', got '{idn}'")
        driver = cls(session)
        driver._send("*RST")
        driver._send("*CLS")
        return driver

    def setup(self, frequency: float, aper: str, level: float):
        """Apply the LCR settings from the GUI panel."""
        self._send_checked(":FUNC:IMP CPG")
        self._send_checked(f":FREQ {scpi_number(frequency)}")
        self._send_checked(f":VOLT {scpi_number(level)}")
        self._send_checked(f":APER {APER_MAP[aper.lower()]}")
        self._send_checked(":TRIG:SOUR BUS")
        self._send_checked(":TRIG:DEL 0")
        # external HV bias comes from the Keithley 2410:
        self._send_checked(":BIAS:STAT OFF")       # internal bias off
        self._send_checked(":OUTP:DC:ISOL ON")     # DC isolation on
        # all corrections disabled
        self._send_checked(":CORR:OPEN:STAT OFF")
        self._send_checked(":CORR:SHOR:STAT OFF")
        self._send_checked(":CORR:LOAD:STAT OFF")

    def read(self):
        """Trigger one measurement and return (capacitance_F, conductance_S).

        A bus trigger followed by FETC? blocks until the measurement is done
        (see the programming chapter of the operation manual, p. 8-6/8-7).
        """
        response = self._ask(":TRIG:IMM;:FETC?")
        values = []
        for token in str(response).split(","):
            try:
                values.append(float(token))
            except ValueError:
                continue
        if len(values) < 2:
            raise InstrumentError(
                f"Unexpected LCR response (need Cp and G): {response!r}")
        return values[0], values[1]

    def close(self):
        super().close()
