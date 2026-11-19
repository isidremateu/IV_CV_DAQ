#!/usr/bin/env python3
"""Entry point of the IV/CV DAQ application.

Usage:
    python main.py            # normal operation (real instruments)
    python main.py --sim      # simulated instruments, no hardware needed
"""

import argparse


def main():
    parser = argparse.ArgumentParser(description="CV/IV silicon sensor DAQ")
    parser.add_argument("--sim", action="store_true",
                        help="run with simulated instruments (no hardware)")
    args = parser.parse_args()

    from gui.main_window import run_app
    raise SystemExit(run_app(sim=args.sim))


if __name__ == "__main__":
    main()
