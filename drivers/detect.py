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
        session = None
        try:
            progress(f"Probing {res}")
            session = session_factory(str(res), baud=SCAN_BAUD,
                                      timeout=SCAN_TIMEOUT)
            idn = str(session.query(IDN_COMMAND)).strip()
            key = identify(idn)
            if key and key not in found:
                found[key] = {"resource": str(res), "idn": idn}
                progress(f"Found {key}: {res} ({idn})")
            elif idn:
                progress(f"  {res}: unrecognized instrument ({idn})")
        except Exception as error:
            progress(f"  {res}: no answer ({error})")
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

    missing = [key for key in MODELS if key not in found]
    return found, missing
