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
# the Keithleys may be configured with a non-default baud rate, so the scan
# tries the rates supported by both instruments before giving up on a port
SERIAL_BAUDS = (9600, 19200, 38400, 57600)


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
    """All VISA resources visible on this machine (GPIB first, serial last)."""
    resources = []
    try:
        import pyvisa
    except ImportError:
        return resources

    # default VISA implementation first, pure-python backend as fallback
    for backend in ("", "@py"):
        try:
            resources = list(pyvisa.ResourceManager(backend).list_resources())
            if resources:
                break
        except Exception:
            continue

    as_upper = lambda r: str(r).upper()
    gpib = [r for r in resources if "GPIB" in as_upper(r)]
    serial = [r for r in resources if as_upper(r).startswith("ASRL")]
    return gpib + serial


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
        bauds = SERIAL_BAUDS if r.upper().startswith("ASRL") else (SCAN_BAUD,)
        found_idn = None
        for baud in bauds:
            session = None
            try:
                progress(f"Probing {r} @ {baud} baud")
                session = session_factory(r, baud=baud, timeout=SCAN_TIMEOUT)
                found_idn = str(session.query(IDN_COMMAND)).strip()
                break
            except Exception as error:
                progress(f"  {r} @ {baud}: no answer ({error})")
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
