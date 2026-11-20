"""VISA session handling."""

import sys


class _AdaptiveTerminationSession:
    """Wraps an ASRL session and adapts to the instrument's transmit terminator.

    Instruments may terminate their responses with LF, CR or CR+LF (selectable
    in the instrument's RS-232 menu). This wrapper starts reading with LF and,
    if a read times out, switches to CR and retries once; the working
    terminator is then kept for the rest of the session.
    """

    def __init__(self, inner):
        self._inner = inner
        self._term = "\n"

    def write(self, command):
        return self._inner.write(command)

    def query(self, command, delay=None):
        self._inner.read_termination = self._term
        try:
            return self._inner.query(command, delay)
        except Exception:
            if self._term == "\n":
                # the instrument may transmit CR-terminated messages
                self._term = "\r"
                return self.query(command, delay)
            raise

    def close(self):
        self._inner.close()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def open_session(resource: str, *, baud: int = 9600, timeout: float = 5.0,
                 parity: str = "none", data_bits: int = 8, stop_bits: int = 1):
    """Open a PyVISA session.

    Works for both RS-232 (ASRL, the two Keithleys) and GPIB (the HP 4284A).
    Serial sessions automatically adapt to the instrument's transmit
    terminator (LF or CR). Tries the default VISA implementation first and
    falls back to the pure-python backend (pyvisa-py) if none is configured.
    """
    try:
        import pyvisa
        from pyvisa.constants import Parity, StopBits
    except ImportError:
        raise ImportError(
            "pyvisa is not installed. Activate the virtual environment and run: "
            "pip install -r requirements.txt"
        )

    kwargs = {
        "read_termination": "\n",
        "write_termination": "\n",
        "timeout": timeout * 1000.0,  # pyvisa expects ms
    }
    if resource.upper().startswith("ASRL"):
        kwargs["baud_rate"] = baud
        kwargs["parity"] = {"none": Parity.none,
                            "even": Parity.even,
                            "odd": Parity.odd}[parity]
        kwargs["data_bits"] = int(data_bits)
        kwargs["stop_bits"] = {1: StopBits.one, 2: StopBits.two}[int(stop_bits)]

    # backend order: vendor VISA (NI-VISA), pure-python (serial/USB/TCP), and
    # Linux-GPIB (needed for NI GPIB adapters on Linux where NI-VISA cannot
    # drive them). The first backend that can open the resource wins.
    last_error = None
    for backend in ("", "@py", "@gpib"):
        try:
            manager = pyvisa.ResourceManager(backend)
            session = manager.open_resource(resource, **kwargs)
            if session is None:
                raise RuntimeError(f"Could not open resource '{resource}'")
        except Exception as error:
            last_error = error
            continue
        if resource.upper().startswith("ASRL"):
            return _AdaptiveTerminationSession(session)
        return session
    raise RuntimeError(f"Could not connect to '{resource}': {last_error}")

