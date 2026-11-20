"""Common helpers shared by all instrument drivers."""

import re


class InstrumentError(RuntimeError):
    """Raised on communication failures or unexpected instrument responses."""


def parse_scpi_float(response: str) -> float:
    """Extract the first parseable number from a SCPI response.

    Handles responses such as '+1.234E-06', 'N,+1.234E-06,+0.000E+00'
    (reading prefixed by a status letter) and comma-separated lists.
    """
    if response is None:
        raise InstrumentError("Empty instrument response")
    for token in str(response).strip().split(","):
        token = token.strip()
        if not token:
            continue
        try:
            return float(token)
        except ValueError:
            # strip a leading status letter, e.g. 'N' or 'O' in front of the number
            match = re.match(r"^[A-Za-z]+([+-]?\d.*)$", token)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    pass
    raise InstrumentError(f"Could not parse instrument response: {response!r}")


def scpi_number(value) -> str:
    """Format a float as a valid SCPI NR3 number.

    Keithley instruments reject NR3 numbers without a decimal point in the
    mantissa (e.g. '1e-06' -> syntax error -102), so always emit the full
    form ('1.000000e-06').
    """
    return f"{float(value):.6e}"


class InstrumentBase:
    """Thin wrapper around a VISA-like session (objects with write/query/close)."""

    def __init__(self, session):
        self.session = session

    def _send(self, command: str):
        self.session.write(command)

    def _ask(self, command: str) -> str:
        return self.session.query(command)

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass
