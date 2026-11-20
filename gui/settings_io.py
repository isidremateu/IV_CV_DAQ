"""Save / load / default handling of the GUI settings.

Settings are stored as JSON with this structure::

    {
        "version": 1,
        "mode": "iv",
        "hvps": {...HVPSConfig...},
        "pico": {...PicoConfig...},
        "lcr": {...LCRConfig...},
        "connections": {"hvps": "...", "pico": "...", "lcr": "..."},
        "run": {"folder": "...", "identifier": "..."}
    }

Default settings live in ~/.ivcv_daq/default_settings.json and are applied
automatically at startup when present.
"""

import json
from dataclasses import fields as dataclass_fields
from pathlib import Path

from core.config import HVPSConfig, LCRConfig, PicoConfig

SETTINGS_VERSION = 1
DEFAULTS_DIR = Path.home() / ".ivcv_daq"
DEFAULTS_PATH = DEFAULTS_DIR / "default_settings.json"


def load_settings_file(path) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Settings file does not contain a JSON object")
    return data


def save_settings_file(path, state: dict):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def collect_state(window):
    """Read the full state from the main window.

    Returns (state, warnings); sections whose fields hold invalid values are
    omitted from the state and reported in warnings (so saving is always
    possible).
    """
    state = {"version": SETTINGS_VERSION,
             "mode": window.mode_combo.currentText()}
    warnings = []
    for key, panel in (("hvps", window.hvps_panel),
                       ("pico", window.pico_panel),
                       ("lcr", window.lcr_panel)):
        try:
            state[key] = panel.get_config().as_dict()
        except ValueError as error:
            warnings.append(f"'{key}' section not saved: {error}")
    state["connections"] = window.connections.resources()
    state["connections"]["serial_probes"] = window.connections.probe_text()
    state["run"] = {"folder": window.save_panel.folder.text(),
                    "identifier": window.save_panel.identifier.text()}
    return state, warnings


def apply_state(window, state: dict):
    """Apply a state dict to the main window; returns a list of warnings."""
    warnings = []

    mode = state.get("mode")
    if mode in ("iv", "cv"):
        window.mode_combo.setCurrentText(mode)

    constructors = (("hvps", HVPSConfig, window.hvps_panel),
                    ("pico", PicoConfig, window.pico_panel),
                    ("lcr", LCRConfig, window.lcr_panel))
    for key, cls, panel in constructors:
        data = state.get(key)
        if not isinstance(data, dict):
            continue
        try:
            # ignore unknown keys so newer files still load
            names = {f.name for f in dataclass_fields(cls)}
            panel.set_config(cls(**{k: v for k, v in data.items() if k in names}))
        except Exception as error:
            warnings.append(f"Could not apply '{key}' settings: {error}")

    connections = state.get("connections")
    if isinstance(connections, dict):
        for key, value in connections.items():
            if key in window.connections.fields:
                window.connections.set_resource(key, str(value))
        if "serial_probes" in connections:
            window.connections.set_probe_text(connections["serial_probes"])

    run = state.get("run")
    if isinstance(run, dict):
        if "folder" in run:
            window.save_panel.folder.setText(str(run["folder"]))
        if "identifier" in run:
            window.save_panel.identifier.setText(str(run["identifier"]))

    return warnings


def built_in_default_state() -> dict:
    """The state matching the dataclass defaults (factory reset).

    Deliberately excludes 'run' (folder/identifier): the data folder is
    machine-specific and should survive a factory reset.
    """
    return {
        "version": SETTINGS_VERSION,
        "mode": "iv",
        "hvps": HVPSConfig().as_dict(),
        "pico": PicoConfig().as_dict(),
        "lcr": LCRConfig().as_dict(),
        "connections": {"hvps": "/dev/ttyS0",
                        "pico": "/dev/ttyS1",
                        "lcr": "GPIB0::17::INSTR"},
    }
