"""Direct Linux-GPIB session (uses the linux-gpib Python bindings directly).

This is the standard way to drive NI GPIB adapters (e.g. GPIB-USB-HS) on
Linux, where NI's own driver stack is outdated. It requires:
- the linux-gpib kernel module (e.g. ni_usb_gpib) loaded,
- the adapter initialized with `gpib_config`,
- the linux-gpib Python bindings (`import gpib`) built for the venv's Python.

No pyvisa backend is needed for GPIB resources.
"""

import re
import time

GPIB_RESOURCE_RE = re.compile(r"^GPIB(\d+)::(\d+)::INSTR$", re.I)

# linux-gpib ibdev timeout indices -> seconds (from the linux-gpib docs)
_TIMEOUTS = {11: 1.0, 12: 3.0, 13: 10.0, 14: 30.0}


def is_gpib_resource(resource) -> bool:
    return bool(GPIB_RESOURCE_RE.match(str(resource)))


class LinuxGpibSession:
    """GPIB session with the same write/query/close interface as pyvisa."""

    def __init__(self, resource, *, timeout: float = 5.0):
        match = GPIB_RESOURCE_RE.match(str(resource))
        if not match:
            raise ValueError(f"Not a GPIB resource string: {resource!r}")
        import gpib  # linux-gpib Python bindings

        self._gpib = gpib
        board, pad = int(match.group(1)), int(match.group(2))
        # the bindings expose either a high-level API (dev/write/read) or the
        # low-level ib* calls, depending on the linux-gpib version
        if hasattr(gpib, "dev"):
            self.handle = gpib.dev(board, pad)
        else:
            tmo_index = min(_TIMEOUTS, key=lambda i: abs(_TIMEOUTS[i] - timeout))
            self.handle = gpib.ibdev(board, pad, 0, tmo_index, 1, 0)

    def write(self, command):
        data = command if isinstance(command, bytes) else command.encode("ascii")
        if hasattr(self._gpib, "write"):
            self._gpib.write(self.handle, data)
        else:
            self._gpib.ibwrt(self.handle, data)

    def query(self, command, delay=None):
        self.write(command)
        if delay:
            time.sleep(delay)
        return self._read_response()

    def _read_response(self):
        if hasattr(self._gpib, "read"):
            data = self._gpib.read(self.handle, 1 << 20)
        else:
            # ibrd blocks until EOI (or the board timeout); some binding
            # versions return (data, status) instead of just data
            data = self._gpib.ibrd(self.handle, 1 << 20)
        if isinstance(data, tuple):
            data = data[0]
        if isinstance(data, bytes):
            data = data.decode("latin-1", "replace")
        # strip parity high-bits (all instrument traffic is ASCII)
        return "".join(chr(ord(ch) & 0x7F) for ch in str(data)).strip()

    def close(self):
        try:
            if hasattr(self._gpib, "close"):
                self._gpib.close(self.handle)
            else:
                self._gpib.ibonl(self.handle, 0)
        except Exception:
            pass
