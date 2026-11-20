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
"""

MODELS = {
    "hvps": "2410",
    "pico": "6487",
    "lcr": "4284A",
}
IDN_COMMAND = "*IDN?"
SCAN_TIMEOUT = 1.5  # s, per-resource timeout during the scan
SCAN_BAUD = 9600    # RS-232 default of both Keithley instruments
# Serial line settings tried when probing a port and when connecting: both
# Keithleys support 9600-57600 baud, 8 data bits, and none/even parity
# (defaults are 9600/none; instruments may be configured differently, e.g.
# 19200/even).
SERIAL_PROBES = [
    (9600, "none"), (19200, "even"), (19200, "none"), (9600, "even"),
    (38400, "none"), (38400, "even"), (57600, "none"), (57600, "even"),
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


def scan_for_instruments(candidates=None, *, progress=None, session_factory=None):
    """Probe candidate resources and identify the DAQ instruments.

    Parameters
    ----------
    candidates : list of resource strings; enumerated automatically if None
    progress : callable(str) for progress messages
    session_factory : injectable session opener (for testing)

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

    found = {}
    progress(f"Scanning {len(candidates)} resource(s)...")
    for res in candidates:
        r = str(res)
        probes = SERIAL_PROBES if r.upper().startswith("ASRL") \
            else [(SCAN_BAUD, "none")]
        found_idn = None
        for baud, parity in probes:
            session = None
            try:
                progress(f"Probing {r} @ {baud} baud, {parity} parity")
                session = session_factory(r, baud=baud, timeout=SCAN_TIMEOUT,
                                          parity=parity)
                found_idn = str(session.query(IDN_COMMAND)).strip()
                break
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
