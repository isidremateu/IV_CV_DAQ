#!/usr/bin/env python3
"""Verbose instrument-scan diagnostics for the measurement PC.

Run from the project root with the virtual environment active:

    python tools/detect_debug.py

Prints the available VISA backends, every candidate resource, and the result
of probing each one. Serial ports are tried at several baud rates; if a
Prologix USB-GPIB adapter is found, its GPIB addresses are scanned.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyvisa

from drivers.detect import SERIAL_PROBES, candidate_resources, identify


def probe(resource, baud, parity="none", data_bits=8):
    """Query *IDN? on one resource; returns (idn, error_message)."""
    from drivers.session import open_session
    session = None
    try:
        session = open_session(resource, baud=baud, timeout=2.0,
                               parity=parity, data_bits=data_bits)
        idn = str(session.query("*IDN?")).strip()
        return idn, None
    except Exception as error:
        return None, f"{type(error).__name__}: {error}"
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def prologix_scan(resource):
    """Scan GPIB addresses 1-30 behind a Prologix USB-GPIB adapter."""
    from drivers.session import open_session
    session = None
    print(f"  {resource}: Prologix GPIB adapter detected -> "
          "scanning GPIB addresses 1..30")
    try:
        session = open_session(resource, baud=9600, timeout=2.0)
        session.write("++mode 1")        # controller mode
        session.write("++auto 1")        # read back after every instrument write
        session.write("++read_tmo_ms 300")
        for addr in range(1, 31):
            session.write(f"++addr {addr}")
            session.write("*IDN?")
            try:
                resp = str(session.read()).strip()
            except Exception:
                continue
            if resp:
                print(f"      GPIB {addr}: '{resp}' -> {identify(resp)}")
    except Exception as error:
        print(f"      Prologix scan failed: {type(error).__name__}: {error}")
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def main():
    print("== VISA backends ==")
    print("  linux-gpib bindings:", end=" ")
    try:
        import gpib
        print("available")
    except ImportError:
        print("NOT INSTALLED (needed for GPIB adapters)")
    for backend in ("", "@py", "@gpib"):
        try:
            rm = pyvisa.ResourceManager(backend)
            res = list(rm.list_resources())
            print(f"  {backend or 'default':8s}: {len(res)} resource(s): {res}")
        except Exception as error:
            print(f"  {backend or 'default':8s}: NOT AVAILABLE ({error})")

    resources = candidate_resources()
    print(f"\n== Scanning {len(resources)} candidate resource(s) ==")
    for res in resources:
        r = str(res)
        if r.upper().startswith("ASRL"):
            for baud, parity, data_bits in SERIAL_PROBES:
                idn, error = probe(r, baud, parity, data_bits)
                if error is None:
                    print(f"  {r} @ {baud}/{parity}/{data_bits}: "
                          f"'{idn}' -> {identify(idn)}")
                    if identify(idn):
                        break   # identified: no need for other line settings
                else:
                    print(f"  {r} @ {baud}/{parity}/{data_bits}: {error}")
        else:
            idn, error = probe(r, 9600)
            if error is None and idn and "PROLOGIX" in idn.upper():
                prologix_scan(r)
            elif error is None:
                print(f"  {r}: '{idn}' -> {identify(idn)}")
            else:
                print(f"  {r}: {error}")
    print("\ndone")


if __name__ == "__main__":
    main()
