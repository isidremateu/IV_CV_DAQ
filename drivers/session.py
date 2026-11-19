"""VISA session handling."""

import sys


def open_session(resource: str, *, baud: int = 9600, timeout: float = 5.0):
    """Open a PyVISA session.

    Works for both RS-232 (ASRL, the two Keithleys) and GPIB (the HP 4284A).
    Tries the default VISA implementation first and falls back to the
    pure-python backend (pyvisa-py) if none is configured.
    """
    try:
        import pyvisa
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

    try:
        manager = pyvisa.ResourceManager()
        session = manager.open_resource(resource, **kwargs)
        if session is None:
            raise RuntimeError(f"Could not open resource '{resource}'")
        return session
    except Exception as first_error:
        try:
            manager = pyvisa.ResourceManager("@py")
            session = manager.open_resource(resource, **kwargs)
            if session is None:
                raise RuntimeError(f"Could not open resource '{resource}'")
            return session
        except Exception:
            raise RuntimeError(
                f"Could not connect to '{resource}'. "
                f"Default backend error: {first_error}"
            )
