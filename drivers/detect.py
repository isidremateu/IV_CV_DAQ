"""Automatic detection of the DAQ instruments on the connected buses.

Every candidate VISA resource (GPIB addresses first, then serial ports) is
opened with a short timeout and queried with *IDN?. The response identifies
the instrument model:

- Keithley 2410  -> HVPS      ("hvps")
- Keithley 6487  -> picoammeter ("pico")
- HP 4284A       -> LCR meter ("lcr")

The scan is best-effort: resources that cannot be opened (e.g. busy ports,
missing drivers) or that do not answer in time are skipped. Probing with
*IDN? is harmless for the instruments.

The serial line settings to probe can be restricted for faster scans:
`parse_serial_probes("19200/even/8")` etc.
"""

import re

MODELS = {
    "hvps": "2410",
    "pico": "6487",
    "lcr": "4284A",
}
IDN_COMMAND = "*IDN?"
SCAN_TIMEOUT = 1.0  # s, per-resource timeout during the scan
SCAN_BAUD = 9600    # RS-232 default of both Keithley instruments
# Serial line settings tried when probing a port and when connecting: both
# Keithleys support 9600-57600 baud, 7 or 8 data bits, and none/even parity.
# Defaults are 9600/none/8, but instruments are frequently configured
# differently (e.g. 19200/even, with either 7 or 8 data bits).
SERIAL_PROBES = [
    (19200, "even", 8), (19200, "even", 7),
    (9600, "none", 8), (9600, "even", 7),
    (19200, "none", 8), (9600, "even", 8), (9600, "none", 7),
    (19200, "none", 7), (9600, "even", 8),
    (38400, "none", 8), (38400, "even", 8),
    (57600, "none", 8), (57600, "even", 8),
]


def identify(idn):
    """Map an *IDN? response to an instrument key (or None)."""
    if not idn:
        return None
    s = str(idn).upper()
    for key, model in MODELS.items():
        if model in s:
            return key
    return None


def parse_serial_probes(text):
    """Parse user-supplied serial line settings.

    Accepts a string like "19200/even/8" or "19200/even/8, 9600/none/7"
    (separators: commas, semicolons and/or whitespace). Returns a list of
    (baud, parity, data_bits) tuples, or None for an empty string (meaning:
    probe all supported combinations).
    """
    text = (text or "").strip()
    if not text:
        return None
    probes = []
    for token in re.split(r"[,;\s]+", text):
        if not token:
            continue
        parts = token.lower().split("/")
        if len(parts) != 3:
            raise ValueError(
                f"Invalid serial settings '{token}' "
                "(expected baud/parity/data_bits, e.g. 19200/even/8)")
        try:
            baud, data_bits = int(parts[0]), int(parts[2])
        except ValueError:
            raise ValueError(f"Invalid number in serial settings '{token}'")
        parity = parts[1]
        if not 300 <= baud <= 115200:
            raise ValueError(f"Invalid baud rate '{parts[0]}' in '{token}'")
        if parity not in ("none", "even", "odd"):
            raise ValueError(
                f"Invalid parity '{parts[1]}' in '{token}' (none/even/odd)")
        if data_bits not in (7, 8):
            raise ValueError(
                f"Invalid data bits '{parts[2]}' in '{token}' (7 or 8)")
        probes.append((baud, parity, data_bits))
    return probes or None


def candidate_resources():
    """All VISA resources visible on this machine (GPIB first, serial last).

    Resources are merged from every available backend: the vendor VISA
    implementation (if any), the pure-python backend (pyvisa-py, serial etc.),
    and the Linux-GPIB backend (pyvisa-gpib, for NI GPIB adapters driven by
    linux-gpib). If a GPIB backend is available but lists no instruments, the
    GPIB addresses are probed explicitly (list_resources is unreliable there).
    """
    resources = []
    seen = set()
    gpib_bindings_available = True
    try:
        import gpib  # linux-gpib Python bindings
    except ImportError:
        gpib_bindings_available = False
    try:
        import pyvisa
    except ImportError:
        return resources

    for backend in ("", "@py", "@gpib"):
        try:
            manager = pyvisa.ResourceManager(backend)
            if backend == "@gpib":
                gpib_bindings_available = True
            for r in manager.list_resources():
                if str(r) not in seen:
                    seen.add(str(r))
                    resources.append(r)
        except Exception:
            continue

    as_upper = lambda r: str(r).upper()
    gpib = [r for r in resources if "GPIB" in as_upper(r)]
    serial = [r for r in resources if as_upper(r).startswith("ASRL")]
    result = gpib + serial
    if gpib_bindings_available and not gpib:
        # linux-gpib cannot list instruments reliably: probe all addresses
        result += [f"GPIB0::{addr}::INSTR" for addr in range(1, 31)]
    return result


def scan_for_instruments(candidates=None, *, progress=None, session_factory=None,
                         serial_probes=None):
    """Probe candidate resources and identify the DAQ instruments.

    Parameters
    ----------
    candidates : list of resource strings; enumerated automatically if None
    progress : callable(str) for progress messages
    session_factory : injectable session opener (for testing)
    serial_probes : list of (baud, parity, data_bits) line settings to try on
        serial ports; defaults to all supported combinations (SERIAL_PROBES)

    Returns
    -------
    (found, missing) where found maps instrument keys ("hvps", "pico", "lcr")
    to {"resource", "idn"} and missing lists the keys not detected.
    """
    if progress is None:
        progress = lambda msg: None
    if session_factory is None:
        from drivers.session import open_session as session_factory
    if candidates is None:
        candidates = candidate_resources()
    probes = list(serial_probes) if serial_probes else SERIAL_PROBES

    found = {}
    progress(f"Scanning {len(candidates)} resource(s)...")
    for res in candidates:
        r = str(res)
        resource_probes = probes if r.upper().startswith("ASRL") \
            else [(SCAN_BAUD, "none", 8)]
        found_idn = None
        for baud, parity, data_bits in resource_probes:
            session = None
            try:
                progress(f"Probing {r} @ {baud} baud, {parity} parity, "
                         f"{data_bits} data bits")
                session = session_factory(r, baud=baud, timeout=SCAN_TIMEOUT,
                                          parity=parity, data_bits=data_bits)
                found_idn = str(session.query(IDN_COMMAND)).strip()
                if identify(found_idn):
                    break
                # a response, but not one of our instruments: try the next
                # line settings (the instrument may use a different baud rate)
            except Exception as error:
                progress(f"  {r} @ {baud}/{parity}: no answer ({error})")
            finally:
                if session is not None:
                    try:
                        session.close()
                    except Exception:
                        pass

        key = identify(found_idn)
        if key and key not in found:
            found[key] = {"resource": r, "idn": found_idn}
            progress(f"Found {key}: {r} ({found_idn})")
        elif found_idn is not None:
            progress(f"  {r}: unrecognized instrument ({found_idn})")

    missing = [key for key in MODELS if key not in found]
    return found, missing
